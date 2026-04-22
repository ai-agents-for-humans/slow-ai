---
layout: default
title: Architecture
nav_order: 3
---

# Architecture
{: .no_toc }

A design-first walkthrough of the system. Not a reference manual — a narrative. Each section explains the *why* before the *what*, built through a conversation with the system's architect.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## The bird's eye view

Before anything else — the complete picture in one diagram.

```
┌───────────────────────────────────────────────────────────────────┐
│                        APPLICATION LAYER                          │
│                        Streamlit → React                          │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│                          AGENTIC LAYER                            │
│                                                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────────────┐ │
│  │    AGENTS    │   │    BYOFM     │   │    SKILLS & TOOLS     │ │
│  │  Planner     │◀─▶│  task-type   │◀─▶│  Registry ·           │ │
│  │  Orchestrator│   │  → model     │   │  perplexity · browse  │ │
│  │  Specialists │   │  any provider│   │  code · prior evidence│ │
│  │  Interviewer │   └──────────────┘   └───────────────────────┘ │
│  │  Synthesiser │                                                 │
│  └──────┬───────┘                                                 │
│         │                                                         │
│    ① Planner generates                                            │
│         ▼                                                         │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   CONTEXT GRAPH  (artifact)                 │ │
│  │   phases · work items · dependencies · viability gate       │ │
│  └─────────────────────────────┬───────────────────────────────┘ │
│                                │                                  │
│    ② Orchestrator reads + drives swarm                           │
│                                ▼                                  │
│              ┌─────────────────────────────┐                     │
│              │      SPECIALIST SWARM        │                     │
│              │  parallel work items ·       │                     │
│              │  wave loop · synthesis ·     │                     │
│              │  phase assessment            │                     │
│              └─────────────────────────────┘                     │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│                       PROCESSING LAYER                            │
│              Sandboxed subprocess · uv venv per run               │
└───────────────────────────────────────────────────────────────────┘

┌────────────────────────────────┐  ┌────────────────────────────┐
│          MEMORY LAYER          │  │   CONTEXT GRAPH STORAGE    │
│  Runs · Artefacts · Envelopes  │  │  versions · refinements ·  │
│  HITL · conversation history   │  │  approved snapshots        │
└────────────────────────────────┘  └────────────────────────────┘
                     └──────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │     GIT LAYER      │
                    │  milestone commits │
                    │  full audit trail  │
                    │  artefact history  │
                    └─────────┬──────────┘
                              │  feeds
                    ┌─────────▼──────────┐
                    │     RL LAYER       │  ← sidecar
                    │  envelopes · HITL  │
                    │  graphs · outcomes │
                    │  → fine-tuned      │
                    │    models + skills │
                    └────────────────────┘
```

The key insight sits inside the agentic layer: **an agent designs the workflow, then a swarm executes it.**

The workflow — the context graph — is not configured by a human. It emerges from a conversation between the human and a planning agent, is reviewed and approved by the human, and only then does an orchestrator read it and drive a swarm through it. The human approves the *shape of the work*, not the implementation details.

Everything that runs is committed to git. Every envelope, artefact, phase summary, approved graph. Git is not a backup. It is the system of record. The RL layer sits as a sidecar, reading from that record to fine-tune models and update the skill registry over time.

> *An agent designs the workflow. The workflow becomes the contract. A swarm executes against it. Everything is committed to git. The RL layer learns from what happened.*

---

## The agentic layer

Three things collaborate at runtime: **agents**, the **model registry (BYOFM)**, and the **skills and tools registry**. None of the three is useful without the other two.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          AGENTIC LAYER                              │
│                                                                     │
│  ┌───────────────────┐    ┌─────────────────┐    ┌───────────────┐ │
│  │      AGENTS       │    │   MODEL REGISTRY │    │ SKILLS &     │ │
│  │                   │    │     (BYOFM)      │    │ TOOLS        │ │
│  │  Interviewer      │    │                  │    │              │ │
│  │  Planner    ──────┼───▶│  reasoning slot  │    │  perplexity  │ │
│  │  Orchestrator     │    │  fast slot       │    │  web_browse  │ │
│  │  Specialist ──────┼───▶│  code slot  ─────┼───▶│  code_exec   │ │
│  │  Synthesiser      │    │  specialist slot │    │  prior_evid. │ │
│  │  Assessor   ──────┼───▶│                  │    │              │ │
│  └───────────────────┘    │  Google · OpenAI │    └───────────────┘ │
│                           │  Anthropic · any │                     │
│                           │  OpenAI-compat.  │                     │
│                           └─────────────────┘                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Five agent roles

| Agent | What it does | Model slot |
|---|---|---|
| **Interviewer** | Elicits a structured research brief from free-form conversation | `fast` |
| **Planner** | Generates the context graph from the approved brief | `reasoning` |
| **Orchestrator** | Drives the swarm through the approved graph | `reasoning` |
| **Specialist** | Executes one work item using tools, produces an evidence envelope | `specialist` |
| **Synthesiser / Assessor** | Consolidates phase output, assesses confidence, advises next phase | `fast` / `reasoning` |

### BYOFM — bring your own foundational model

Every model slot lives in a single JSON file:

```json
{ "name": "reasoning",  "model_id": "google-gla:gemini-2.5-pro",
  "use_for": ["context_planning", "orchestration", "assessment"] }

{ "name": "fast",       "model_id": "google-gla:gemini-2.5-flash",
  "use_for": ["skill_synthesis", "report_synthesis", "interview"] }

{ "name": "code",       "model_id": "google-gla:gemini-2.5-pro",
  "use_for": ["code_generation"] }

{ "name": "specialist", "model_id": "google-gla:gemini-2.5-pro",
  "use_for": ["specialist_research"] }
```

Agents declare what *kind of reasoning* they need. The registry resolves which model does that best today.

This is a deliberate design choice: **the model leaderboard moves faster than agent code should.** When a better reasoning model appears, one entry changes. Every agent using that slot benefits immediately. No code touched.

The slot abstraction also manages cost by design. Fast, well-defined tasks go to flash models. High-stakes decisions go to the most capable model available. The routing is automatic.

The longer vision: domain-specialist slots. A geospatial reasoning model. A biomedical literature model. A legal reasoning model. Add a slot, point it at a specialist model, and any agent can declare it. The architecture does not need to change.

### The bootstrap inside the agentic layer

The agentic layer runs in two distinct phases separated by human approval:

```
  ① DESIGN PHASE
  ──────────────
  Interviewer ──▶ ProblemBrief ──▶ Planner ──▶ ContextGraph
                                                     │
                                              human reviews
                                              refines in chat
                                              approves

  ② EXECUTION PHASE
  ─────────────────
                                        ContextGraph (approved)
                                                     │
                                         Orchestrator reads + drives
                                                     │
                                              Specialist swarm
                                              (wave loop)
                                                     │
                                         Synthesiser · Assessor
```

The context graph is not configured. It is generated, reviewed, and approved. The human reviews the shape of the work, not the implementation. This is the right level of abstraction for expert oversight.

---

## Skills and tools

Tools are primitives. Skills are compositions.

A tool is a concrete callable — a function that does one atomic thing. A skill is a named combination of tools applied in a specific way to solve a specific class of problem.

```
  TOOLS  (atomic, built-in)          SKILLS  (composed, grow over time)
  ─────────────────────────          ──────────────────────────────────
  perplexity_search                  web_search          (1 tool)
  web_browse                         document_parsing    (code_execution)
  code_execution                     geospatial_proc.    (code_execution)
  url_fetch                          statistical_analysis (code_execution)
                                     image_analysis      (code_execution)
                                             │
                                             │ compose
                                             ▼
                                     remote_sensing_analysis
                                       (geospatial + image + api)
                                             │
                                             │ compose further
                                             ▼
                                     environmental_data_analysis
                                       (code + geospatial + statistical)
```

Skills compose other skills. The registry is not flat — it is a graph. Everything ultimately bottoms out at four atomic tools.

### The gap detection loop

The system cannot synthesize a skill it has no tools for. This constraint is productive: when a specialist agent needs a capability that is not in the registry, the system does not silently fail. It surfaces the gap.

```
  Context graph declares work item needs skill X
              │
              ▼
  Viability gate checks registry
              │
         ┌────┴────┐
         │         │
       found    not found
         │         │
         ▼         ▼
      proceed   synthesiser attempts to map
                gap → existing tools
                    │
               ┌────┴────┐
               │         │
           mapped      unmapped
               │         │
               ▼         ▼
          new skill   gap record written
          written     → capability backlog
          to registry   (concrete steps to close it)
```

The gap record accumulates across runs. Over time, the backlog shows exactly which tools to add next, ranked by how often they've been needed. The system tells you what to build.

### Alignment with the Anthropic Agent Skills standard

Anthropic published Agent Skills in December 2025 — a standard format for composable, portable agent capabilities: a `SKILL.md` file plus a scripts directory per skill.

The mental model is identical to what Slow AI built independently. Skills in the Slow AI catalog follow this format:

```
src/slow_ai/skills/catalog/
  web_search/
    SKILL.md      ← name, description, tools, source, tags
  medical_literature_research/
    SKILL.md
  remote_sensing_analysis/
    SKILL.md
  ...             ← 37 skills and growing
```

Each `SKILL.md` is importable from any Agent Skills-compatible system. Skills built elsewhere can be dropped into the catalog and loaded automatically.

---

## The workflow layer

### The context graph

Most workflow tools ask you to draw the workflow. Slow AI asks you to describe the problem — and proposes the workflow for you.

The context graph represents how a human expert thinks about decomposing a big problem: overarching topics first, without diving into the specifics of every activity. A compass, not a map.

```
  ProblemBrief
       │
       ▼
  ┌─────────────────────────────────────────────────────────┐
  │                    CONTEXT GRAPH                        │
  │                                                         │
  │  Phase 1: Market landscape                              │
  │    ├── work item: size and segments         (no deps)   │
  │    └── work item: regulatory environment   (no deps)   │
  │                                                         │
  │  Phase 2: Competitive dynamics              (needs P1)  │
  │    ├── work item: direct competitors                    │
  │    └── work item: adjacent players                      │
  │                                                         │
  │  Phase 3: Viability synthesis               (needs P2)  │
  │    └── work item: go/no-go assessment                   │
  │                                                         │
  └─────────────────────────────────────────────────────────┘
```

The graph captures three things:
- **What** needs to be investigated
- **When** — dependency ordering between phases
- **Why this structure** — a 300-500 word narrative the planner generates after every plan or refinement, explaining the logic of the breakdown

> *"If the direction is not clear, there is no point running hundreds of agents on it."*

### The viability gate

Between graph approval and execution sits the viability gate. Two checks, in sequence:

```
  VIABILITY GATE
  ══════════════

  Stage 1 — Shape assessment
  ──────────────────────────
  Read the approved graph.
  Are the phases coherent? Are dependencies sane?
  Is there enough directional clarity to execute?

  Stage 2 — Capability assessment
  ────────────────────────────────
  For each work item in the graph:

  ┌──────────────────────────────────────────────────────┐
  │ skill exists in registry?               → proceed    │
  │ no skill, but tools can be composed?    → synthesise │
  │                                           + proceed  │
  │ no skill, no tools to compose from?     → FLAG       │
  └──────────────────────────────────────────────────────┘

  Flagged gaps → written to capability backlog
               → surfaced to human before any agent fires
               → not resolved autonomously
```

Tools are added by humans, not discovered by agents. The system knows what it cannot do, says so clearly, and waits. The capability backlog is the output of that decision.

### The wave loop

Once the viability gate passes, the orchestrator begins the wave loop. Phases execute sequentially — output from one informs the next. Work items within a phase execute in parallel.

```
  Approved graph
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │               WAVE LOOP                     │
  │                                             │
  │  Phase 1  ──────────────────────────────┐  │
  │  │  work item A  ──▶ envelope A         │  │
  │  │  work item B  ──▶ envelope B  (par.) │  │
  │  │  work item C  ──▶ envelope C         │  │
  │  └──────────────────────────────────────┘  │
  │       │                                     │
  │       ▼                                     │
  │  Phase synthesis  ──▶ phase summary         │
  │  Phase assessment ──▶ confidence score      │
  │       │                                     │
  │       ▼                                     │
  │  Phase 2  (receives Phase 1 summaries) ...  │
  │       │                                     │
  │       ▼                                     │
  │  Final synthesis ──▶ run summary            │
  └─────────────────────────────────────────────┘
```

Every phase boundary is a consolidation checkpoint. The system cannot skip ahead — it must consolidate what it knows before opening new lines of inquiry.

---

## The processing layer

The processing layer exists because of a principle borrowed from distributed systems: **blast radius**.

Before granting any process permissions, answer one question: *if this goes wrong, what is the worst it can do?* For an agent swarm running arbitrary Python code against the web, without isolation the answer is: *everything*. With isolation: *only itself.*

This principle — and four others — were the founding design constraints of Slow AI, articulated in [Agents Are Just Distributed Systems](https://nischalhp.substack.com/p/agents-are-just-distributed-systems) before a line of code was written.

### Sandboxed subprocess per run

Every run executes in its own subprocess, with its own `uv` virtual environment:

```
  runs/
    {run_id}/
      artefacts/       ← subprocess cwd
        .venv/         ← uv venv, created fresh per run
        *.py           ← agent-generated code
        *.csv / *.json ← agent-generated data
      live/            ← written by runner, read by UI
      envelopes/       ← evidence from each specialist
      runner.log       ← structured log for this run
```

Three things this gives you:

**Parallel runs without interference.** Multiple runs execute simultaneously. Subprocess isolation means no shared state, no lock contention, no run affecting another's output.

**Blast radius containment.** If a run hangs, consumes excessive memory, or hits an unexpected error, the damage is contained to that subprocess. The rest of the system is unaffected.

**Dependency hygiene.** Each venv is created fresh from the run's requirements. Different runs can use different library versions. The global environment stays clean. Dependency hell is not managed — it is structurally prevented.

### Security scanning

Before any agent-generated code executes, `bandit` scans it for Python security issues:

```
  HIGH severity   → BLOCK  (run halts)
  MEDIUM severity → WARN   (logged, execution continues)
  LOW severity    → silent
```

This is Byzantine Fault Tolerance in practice. The system does not trust its own agents' output. Generated code is treated as untrusted until it passes inspection.

### The five distributed systems principles

| Principle | What it means here |
|---|---|
| **Blast radius** | Sandbox every run. Scope permissions to the minimum needed. |
| **Circuit breakers** | Isolate failures. One run cannot cascade into another. |
| **Byzantine fault tolerance** | Do not trust agent output. Require evidence envelopes. Scan generated code. |
| **Idempotency** | Runs can be repeated. Envelopes are replayable. Git preserves every state. |
| **MAPE-K** | Separate observation from execution. Live files are the observable state. UI reads them; runner writes them. |

These are not abstractions layered on top of an existing design. They are the design.

---

## The memory layer

> *"How do you trust what an agent did if you cannot verify it?"*

In a system where agents generate code, make tool calls, and synthesise evidence across dozens of concurrent processes — trust requires a verifiable record of everything that happened. Not a summary. Not a log file. Every intermediate state, every decision, every artefact, versioned and inspectable.

Git provides this. Not as an afterthought — as the design.

### What gets versioned

For every run, the following are committed to git at defined milestone points:

| File | What it records |
|---|---|
| `input_brief.json` | The contract that started the run |
| `input_graph.json` | The approved context graph |
| `envelopes/{agent_id}.json` | Evidence, confidence, verdict, tool calls, reasoning |
| `artefacts/*.py` | Generated code, committed before execution |
| `conversation.jsonl` | Full HITL history: interview, graph review, post-run |
| `runner.log` | Every milestone, every error, with timestamps |

### Forking for experimentation

The most powerful property of a versioned run is not the audit trail — it is the ability to branch.

```
  run A  ────────────────────────────────────────▶  outcome A
    │
    │  fork at Phase 2
    │  (change: swap reasoning model)
    │
  run B  ────────────────────────────────────────▶  outcome B
    │
    │  fork at Phase 2
    │  (change: split a work item into two)
    │
  run C  ────────────────────────────────────────▶  outcome C
```

For any run, at any milestone commit, you can fork: change the model, adjust the prompt, refine the graph — and observe what changes. The `(brief, graph, model, prompts, tools, envelopes, outcome)` tuple, fully versioned and reproducible, is the training datum for the RL layer.

**The git history is not a log. It is the dataset.**

### The two-plane architecture

```
  EXECUTION PLANE                     UI PLANE
  ───────────────                     ────────
  runner.py                           Streamlit / React
  orchestrator                        reads live/ via polling or SSE
  specialist agents                   reads envelopes/ on demand
        │                             reads conversation.jsonl
        │ writes
        ▼
  runs/{run_id}/live/
  runs/{run_id}/envelopes/
  runs/{run_id}/conversation.jsonl
        │
        ▼
  git commit  (at every milestone)
```

The UI never calls an agent. The execution plane never calls the UI. The filesystem — versioned by git — is the interface between them. Any future rendering layer plugs in without touching the execution plane.

---

## The RL layer

The RL layer does not run during a research session. It watches, accumulates, and learns. Its job is to make the system measurably better at planning and execution with every run that completes.

### Three trajectory types

Every run produces a trajectory. Over time, three types accumulate:

```
  TYPE 1 — Original agent path
    Agent planned → swarm executed → human reviewed
    No intervention. Outcome: continued (success) or abandoned.

  TYPE 2 — Human-augmented path
    Agent planned → human refined → swarm executed
    Human corrections are part of the trajectory.
    Outcome: success (human participation made it better)

  TYPE 3 — Abandoned path
    Agent planned → swarm executed → human could not recover it
    Signal of fundamentally bad planning.
```

All three are training data. Type 1 shows what works without help. Type 2 shows exactly where agent judgment diverged from expert judgment — and what correction looked like. Type 3 shows the failure modes to avoid entirely.

### The sidecar model

The goal of RL is not to replace the foundational LLM. It is to produce a **policy model** — a critic that runs alongside the foundational LLM, observing every planning and execution decision and providing corrective signal.

```
  FOUNDATIONAL LLM  ─────▶  proposed action
                                  │
                                  ▼
                        POLICY MODEL (sidecar)
                        observes · critiques · guides
                                  │
                         ┌────────┴────────┐
                         │                 │
                       good             adjust
                         │                 │
                         ▼                 ▼
                    proceed          corrected action
```

The sidecar catches bad planning at the planning stage — where intervention is cheap — not at the synthesis stage where damage has already been done.

### The RL formulation

The graph and sequence of agent actions is a delayed reward problem. The signal arrives at the end — when a human continues with the output or abandons it. This maps to the Bellman equation:

```
  V(s) = R(s) + γ · max_a V(s')

  State s:    current graph + completed actions + evidence so far
  Action a:   next agent decision (plan step, tool call, synthesis)
  Reward R:   delayed — human continuation is the signal
```

The algorithm being considered: **GRPO** — Group Relative Policy Optimization. Rather than computing absolute rewards per trajectory, GRPO compares groups of trajectories relative to each other. Which planning approach, across comparable briefs, produced better outcomes? The policy learns from the delta.

This fits naturally with the forking design. Every experimental branch is a new trajectory variant. The more variants you accumulate across comparable briefs, the sharper the policy becomes.

---

## Human-in-the-loop by design

The goal of Slow AI is not automation. It is **augmentation**.

Automation replaces human judgment. Augmentation extends it. These produce different systems. A system built for automation removes the human from the loop as quickly as possible. A system built for augmentation keeps the human at every moment where their judgment cannot be replicated by a model.

There are three such moments.

```
  ┌─────────────────────────────────────────────────────────────────┐
  │  1. INTERVIEW                                                   │
  │     Kind of judgment: foundational                              │
  │     "Did the agent understand what I actually need?"            │
  │     The brief is the cornerstone. Wrong brief, wrong everything.│
  └─────────────────────────────────────────────────────────────────┘
                              │ ProblemBrief (committed)
  ┌─────────────────────────────────────────────────────────────────┐
  │  2. CONTEXT GRAPH REVIEW                                        │
  │     Kind of judgment: directional                               │
  │     "Does this breakdown match how an expert would approach it?"│
  │     Human approves the shape, not the implementation.           │
  └─────────────────────────────────────────────────────────────────┘
                              │ Approved graph → swarm executes
  ┌─────────────────────────────────────────────────────────────────┐
  │  3. POST-RUN CONVERSATION                                       │
  │     Kind of judgment: evaluative                                │
  │     "Did this output actually extend my thinking?"              │
  │     Engagement is the signal. Abandonment is its opposite.      │
  └─────────────────────────────────────────────────────────────────┘
```

### Why LLM-as-judge is not enough

An LLM can evaluate whether an output is well-structured and internally consistent. It cannot evaluate whether a hard problem was actually solved in a way that is useful to a specific expert in a specific context.

For the kinds of problems Slow AI is designed for — due diligence, regulatory analysis, strategic research, scientific synthesis — the quality of the output determines the quality of everything built on top of it. Only the domain expert can provide ground truth on whether the output is actually useful.

Human feedback is not a feature of the system. It is the source of the signal that makes the system improve.

---

## Run chaining and the learning flywheel

> *"When you know something, you want to know more — because you feel you know less."*

Every research run converts **unknown unknowns into known unknowns**, and **known unknowns into known knowns**. The natural response is to go deeper. A system that makes you start from zero every time is fighting human nature.

### What the second run inherits

```
  Run 1: "What is protein folding and why does it matter?"
    └── envelopes: basic mechanisms, AlphaFold overview, key researchers
    └── gaps identified: misfolding diseases, therapeutic implications

              │
              │  generate_follow_on_brief()
              │  reads: phase summaries + identified gaps
              ▼

  Run 2: "What are the therapeutic implications of protein misfolding?"
    └── prior_run_ids: [run_1]
    └── specialists pull specific envelopes from run_1 when needed
    └── context graph shaped by what run_1 already covered — no duplication
```

Prior evidence is **pull, not push**. The second run's specialists know prior runs exist. They retrieve specific findings when their work item needs them — not a broadcast of everything. Memory is scoped to what the current task actually requires.

### The compounding trajectory

```
  Run 1  →  "I know the basics. I now know what I don't know."

  Run 2  →  "I understand misfolding. I now know what I still don't know."

  Run 3  →  "I understand the clinical landscape. I'm building real expertise."

  Run N  →  Expert-level synthesis, built incrementally.
             Each run standing on the shoulders of the last.
```

Every run is a training episode for the RL layer. Every follow-on brief is a labeled example of what a good next question looks like. Every human approval is a reward signal. The more the system is used, the better it gets at knowing which threads are worth following.

**The system learns. The expert deepens. The two compound together.**
