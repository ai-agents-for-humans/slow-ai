# Slow AI — Project State

This document captures the full design, architecture, decisions, and current state of the
Slow AI project. It is intended to be read at the start of a new conversation to restore
full context without needing to re-read the codebase from scratch.

---

## What Slow AI Is

A deliberate, inspectable multi-agent research system. The name means **provenance over
pace** — every agent decision, every path taken or skipped, every piece of evidence is
recorded, versioned, and auditable. Domain-agnostic by design: the same system runs data
research, due diligence, competitive analysis, literature surveys, or any structured
multi-step investigation. The process templates change; the principles do not.

The system is built on distributed systems principles: blast radius, circuit breakers,
Byzantine fault tolerance (agents return evidence envelopes, not verdicts), idempotency,
and MAPE-K. Human-in-the-loop is a first-class primitive, not an exception handler.

---

## High-Level Architecture

Two completely independent planes, sharing nothing except files on disk:

```
┌─────────────────────────┐        live/ files (JSON)       ┌──────────────────────────┐
│   UI Plane (Streamlit)  │ ◄──────────────────────────────  │ Execution Plane          │
│   main.py               │                                  │ slow_ai/research/runner  │
│   polls every 5s        │                                  │ subprocess per run       │
│   renders DAG, graphs   │                                  │ own event loop, no ST    │
└─────────────────────────┘                                  └──────────────────────────┘
                                                                        │
                                                               git commits at milestones
                                                               runs/{run_id}/ (bare repo)
```

**Key contract:** the execution plane writes plain JSON files to `runs/{run_id}/live/`.
Streamlit polls those files via `@st.fragment(run_every="5s")`. No shared state, no
threading, no asyncio coupling. This means any future UI (React, CLI) can replace
Streamlit without touching the execution plane.

---

## Execution Flow (Runner Loop)

```
Brief confirmed
  │
  ▼
run_context_planner(brief)          ← LLM call #1, generic, domain-agnostic
  │  produces ContextGraph
  │  committed as M-1-context
  ▼
run_orchestrator(brief, context_graph, ready_work_items)   ← LLM call #2
  │  produces ResearchPlan (specialists for wave 1 only)
  │  ready_work_items = items with no upstream dependencies
  │  committed as M0-plan
  ▼
┌─────────────────────────────────────────────────────┐
│  ORCHESTRATOR LOOP (max 5 waves, circuit breaker)   │
│                                                     │
│  Register Wave N node → run specialists in parallel │
│    each specialist: search + browse tools           │
│    may spawn sub-workers via SpawnRequest           │
│  Mark Wave N completed                              │
│  Commit M{N}-wave (envelopes + artefact files)      │
│                                                     │
│  Recompute ready_work_items from covered set        │
│  orchestrator_assess(brief, graph, envelopes,       │
│                       ready_items, wave)            │
│  Register Assessment node                           │
│  Commit M{N}-assessment (coverage state + decision) │
│  write assessment.json to live/                     │
│                                                     │
│  decision.action ==                                 │
│    "synthesize"         → exit loop                 │
│    "spawn_specialists"  → register Wave N+1 node    │
│                           (child of Assessment N)   │
│                           loop                      │
│    "escalate_to_human"  → write human_checkpoint    │
│                           status = waiting_for_human│
│                           exit loop (Phase 3: block)│
└─────────────────────────────────────────────────────┘
  │
  ▼
Synthesizer node → ResearchReport
Committed as M-final-report
status.json = "completed"
```

---

## Context Graph

The orchestrator's first act is producing a **context graph** — a static blueprint of
all work items needed to meet the goal, with dependency edges. This is committed to git
before any agent runs.

**Key properties:**
- Created by `run_context_planner`, a separate LLM call with a generic (domain-agnostic)
  prompt
- Nodes are `WorkItem` objects: id, name, description, success_criteria, depends_on
- Edges encode dependency: "this item needs that item's results before it can proceed"
- **Static** — never changes during execution, only agents are assigned to it
- The runner enforces dependency ordering via `_ready_work_items(graph, covered_ids)`:
  only work items whose full `depends_on` set is satisfied are dispatched each wave
- The UI shows it as a separate graph above the Agent DAG

**Coverage overlay (UI):**
- Uncovered: grey
- In-progress: blue
- Covered (confidence ≥ 0.6): green
- Partial (confidence 0.3–0.59): orange
- Coverage is computed by reading `work_item_id` from DAG nodes and matching to artefact
  envelopes

---

## Agent DAG

The DAG is built incrementally as agents spawn. Node types and their visual styles:

| Node type     | Style                        | Meaning                              |
|---------------|------------------------------|--------------------------------------|
| `orchestrator`| status-based (blue/green)    | Root control plane node              |
| `wave_N`      | Indigo/purple, bold          | Milestone: groups specialists in wave N |
| specialist    | status-based                 | Actual research agent                |
| `assessment`  | Dark, dashed border          | Orchestrator coverage decision       |
| `synthesizer` | status-based                 | Final report generator               |

**Lineage chain:**
```
Orchestrator
  └── Wave 1 (wave_1)
        ├── copernicus_specialist
        ├── nasa_specialist
        └── Assessment (assessment)
              └── Wave 2 (wave_2)
                    ├── open_data_specialist
                    └── Assessment
                          └── Synthesizer
```

Workers spawned by specialists mid-execution are parented to their spawning specialist.

Each DAG node carries: `id`, `type`, `status`, `tokens`, `spawned_at`, `completed_at`,
`work_item_id` (links back to ContextGraph).

---

## Git Structure per Run

```
runs/{run_id}/                    ← bare git repo (Repo.init)
  problem_brief.json              ← [init] commit
  context_graph.json              ← [M-1-context] commit
  research_plan.json              ← [M0-plan] commit
  envelopes/
    wave1/{agent_id}.json         ← full EvidenceEnvelope per agent
    wave2/{agent_id}.json
  artefacts/
    wave1/{agent_id}/{filename}   ← proof data, named as agent declared
    wave2/{agent_id}/{filename}
  assessments/
    wave1.json                    ← OrchestratorDecision after wave 1
    wave2.json
  report.json                     ← [M-final-report] commit
  registry.json                   ← agent registry snapshot at each milestone
  paths/not_taken/{id}.json       ← skipped paths, stop verdicts, failures
  live/
    status.json                   ← "initializing" | "running" | "completed" | "failed" | "waiting_for_human"
    dag.json                      ← live AgentRegistry DAG (polled by UI)
    artefacts.json                ← live envelope+memory per agent (polled by UI)
    context_graph.json            ← written once after M-1-context
    assessment.json               ← latest OrchestratorDecision (updated each wave)
    log.jsonl                     ← append-only progress log (one JSON per line)
    human_checkpoint.json         ← written when escalate_to_human decision is made
```

---

## Project ↔ Run Association

Projects (confirmed briefs) are stored in `output/{project_id}/problem_brief.json`.
When a research run starts, `output/{project_id}/runs.jsonl` is appended with:
```json
{"run_id": "20240408-143022-abc123", "started_at": "2024-04-08T14:30:22Z"}
```

The sidebar lists all projects, and for each project shows all its runs with live status,
timestamp, and a "View" button to load historical run data into the main view.

---

## Key Models (`src/slow_ai/models.py`)

```python
ProblemBrief          # goal, domain, constraints, unknowns, success_criteria, ...
WorkItem              # id, name, description, success_criteria, depends_on
ContextGraph          # goal, nodes: list[WorkItem], edges: list[dict]
AgentTask             # task_id, goal, context_budget, status
AgentMemory           # entries: list[MemoryEntry], total_tokens, context_budget
AgentContext          # agent_id, role, task, memory, work_item_id, ...
AgentRegistration     # agent_id, agent_type, parent_agent_id, status, work_item_id, ...
ResearchPlan          # run_id, context_graph, specialists: list[AgentContext]
SpecialistAssignment  # role, work_item_id, goal, context_budget (lightweight, for assess output)
OrchestratorDecision  # action, wave, work_items_covered/pending/escalated, next_wave, reasoning
EvidenceEnvelope      # agent_id, role, status, proof, verdict, confidence, artefacts
ResearchReport        # run_id, datasets: list[DatasetCandidate], summary, ...
```

---

## Key Source Files

| File | Purpose |
|------|---------|
| `main.py` | Streamlit UI — interview, DAG viz, context graph viz, run history |
| `src/slow_ai/models.py` | All Pydantic models |
| `src/slow_ai/agents/orchestrator.py` | `run_context_planner`, `run_orchestrator`, `orchestrator_assess` |
| `src/slow_ai/agents/specialist.py` | `run_specialist` — search+browse agent |
| `src/slow_ai/agents/interviewer.py` | Interview agent that produces ProblemBrief |
| `src/slow_ai/research/runner.py` | Full orchestrator loop, wave management, artefact commits |
| `src/slow_ai/research/__main__.py` | Subprocess entry point: reads input_brief.json, calls runner |
| `src/slow_ai/execution/registry.py` | AgentRegistry — control plane, DAG generation |
| `src/slow_ai/execution/git_store.py` | Git commits, live file read/write |
| `src/slow_ai/tools/perplexity.py` | Perplexity search tool |
| `src/slow_ai/tools/web_browse.py` | Web browse tool |

---

## What Is Working

- Full end-to-end run: interview → context graph → wave loop → synthesis → report
- Context graph dependency enforcement (topological wave ordering)
- Agent DAG with wave/assessment/specialist nodes visible in UI
- Live polling of DAG and context graph during execution
- Coverage overlay on context graph (which work items are addressed)
- Click-to-inspect agent nodes (envelope, memory, raw tabs)
- Click-to-inspect context graph nodes (description, success criteria, covering agents)
- Orchestrator assessment after each wave (covered/pending/escalated + reasoning)
- Artefact files committed to git under `artefacts/wave{N}/{agent_id}/`
- Previous runs listed in sidebar per project, click to view historical runs
- Git log visible in report view
- Subprocess isolation (no Streamlit/asyncio coupling)

---

## Known Gaps / Next Items

### 1. Tooling is very limited
Specialists only have `perplexity_search` and `web_browse`. The user wants access to the
full range of tools that ecosystems like Claude have — including browser use (Playwright,
Puppeteer-style), file operations, APIs, etc. The design question is whether to integrate
Claude's native tool use or build a tool registry the orchestrator can draw from.

### 2. Specialist prompt is domain-specific
`orchestrator.py` has a hardcoded earth-observation specialist prompt (TODO comment in
code). The system should derive the specialist types and their prompts from the problem
brief and context graph dynamically. This is the most important pending architectural
change for making the system truly domain-agnostic.

### 3. Human-in-the-loop is a placeholder
When `decision.action == "escalate_to_human"`, the system writes `human_checkpoint.json`
and flips status to `waiting_for_human`, but then immediately synthesizes with available
evidence. Full blocking pause (Phase 3) requires: UI surfaces the checkpoint with an
input form, user responds, runner resumes. The file-based contract is already in place;
the blocking mechanism is not.

### 4. Context graph coverage is static during live view
The context graph state is built once when it first appears and not rebuilt during polling
(to avoid layout thrash). Coverage only reflects the moment the graph first renders.
Final coverage in the report view is always correct. Fixing live coverage updates requires
preserving node positions from the component's return value and rebuilding only styles.

### 5. Workers spawned mid-execution
The `SpawnRequest` mechanism exists and works, but the specialist prompt doesn't
consistently use it. Workers are children of their spawning specialist in the DAG.

### 6. No observer / circuit breaker beyond wave count
The MAPE-K observer (watches for runaway spawning, cost ceiling breaches, confidence
dropping across subtrees) is described in the philosophy but not implemented. Phase 3.

---

## Design Decisions Worth Remembering

**Why subprocess per run:** Streamlit has its own asyncio event loop via `nest_asyncio`.
Google's GenAI SDK uses `anyio`, which creates `asyncio.Event` objects bound to the outer
loop. Running research in a thread (even with a new event loop) caused
`RuntimeError: asyncio.locks.Event bound to different event loop`. Subprocess is the
clean solution — completely separate Python process, own unpatched event loop.

**Why context graph before agent assignment:** The orchestrator previously conflated
"what needs to be done" with "who will do it" in a single one-shot plan. The context
graph separates these: the graph is the blueprint (static), agents are the execution
layer (pluggable). This enables: completeness checks, replayability, gap detection,
and retrospective clarity via the two-graph UI.

**Why dependency-aware waves:** The orchestrator previously launched all specialists in
parallel regardless of the context graph's dependency edges. The runner now computes
`_ready_work_items(context_graph, covered_ids)` and only passes those to the orchestrator
per wave. Dependency ordering is enforced in code (deterministic), not left to the LLM.

**Why artefacts are committed per wave:** `EvidenceEnvelope.artefacts` is a list of
filenames the agent declares it produced. The runner writes `envelope.proof` to each
declared path under `artefacts/wave{N}/{agent_id}/` and includes them in the milestone
commit. This gives you versioned output files traceable to the agent, envelope, and
registry snapshot that produced them — the whole point of having git as the execution
record.

**Why two graphs in UI:** Context graph (what needed to happen) and Agent DAG (what
actually ran). Neither alone tells the full story. The overlay — `work_item_id` on each
DAG node linking back to a context graph node — shows which agents covered which work
items.
