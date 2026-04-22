# Slow AI — Design Decisions Log

This document records the architectural decisions, the reasoning behind them, and the
rejected alternatives for the Slow AI project. It is written chronologically so the
evolution of thinking is preserved.

---

## Session: Context Graph Ontology + Skill System (April 2026)

---

### 1. Context Graph Ontology — Work Type as a First-Class Property

**Decision:** Work items in the context graph must declare the *nature of the work*
required, not just what the work is about.

**The problem with the original design:**
The context graph had `WorkItem` nodes with `id`, `name`, `description`,
`success_criteria`, and `depends_on`. This captured *what* needed to happen but not
*how* — meaning the orchestrator had to figure out what kind of agent to assign at
wave-dispatch time, using domain-specific knowledge baked into a hardcoded prompt.
The system was a research system, but it acted like an earth-observation system
because the orchestrator prompt said so.

**The insight:**
Work items should declare `required_skills`. A work item that needs satellite imagery
retrieval says so explicitly. A work item that needs statistical analysis says so
explicitly. The nature of the work is part of the blueprint, not an inference the
orchestrator makes at runtime.

**Why this matters:**
- Wave planning becomes more principled: search items naturally precede analysis items,
  which precede synthesis items, because the dependency graph reflects this.
- Agent assignment becomes deterministic: the skill declaration drives which tools the
  agent gets, not the domain.
- The system becomes genuinely domain-agnostic: the same orchestration logic runs for
  earth observation, legal due diligence, pharmaceutical research, or competitive
  analysis. Only the skills and the brief change.

**Model change:**
```python
class WorkItem(BaseModel):
    id: str
    name: str
    description: str
    success_criteria: list[str] = []
    depends_on: list[str] = []
    required_skills: list[str] = []  # added
```

---

### 2. Context Planner Should Plan Ideally, Not Within Current Constraints

**Decision:** The context planner is given the skill registry as *context* but is
explicitly told it is NOT limited to available skills. It should declare whatever
skills the ideal research methodology requires.

**The rejected alternative:**
Constrain the context planner to only declare skills that exist in the registry. This
would prevent skill gap detection entirely — the plan would silently degrade to whatever
the system currently knows how to do, with no signal that better approaches exist.

**Why we rejected it:**
A system that plans within its own constraints can never surface what it doesn't know.
The gap between the ideal plan and the available capabilities is precisely the
information needed to grow the system. Hiding that gap is the worst possible outcome.

**The principle:**
Plan for the ideal approach. Surface the gaps. Resolve them. This is "knowing what
you don't know" — far more valuable than a system that silently produces weaker results.

**Prompt addition to context planner:**
> IMPORTANT: You are NOT limited to these skills. If the ideal research methodology
> requires a skill that is not yet listed, declare it anyway. Undeclared skill
> requirements cannot be detected or resolved. Better to declare and flag the gap
> than to omit and silently produce weaker research.

---

### 3. Capability Gap Detection and the Viability Gate

**Decision:** After context planning, a dedicated viability gate runs before any wave
executes. It has two layers: structural (graph topology) and semantic (LLM judgment).

**Structural layer (pure function, no LLM):**
- For each work item, check if all `required_skills` exist in the registry.
- Items with missing skills are "direct gap items".
- BFS through the dependency graph to find all transitive dependents of gap items.
- These are "all blocked items".
- Compute coverage ratio: `executable_items / total_items`.
- Flag critical path gaps: skills that block > 50% of the graph.

**Semantic layer (LLM — `viability_assess`):**
- Receives the brief, graph, structural analysis, and coverage ratio.
- Decides: `go` / `degraded` / `no_go`.
- Key principle: judge by *what* is blocked, not *how many* items. A single missing
  skill that blocks the core research question is `no_go`. Several missing skills that
  only affect peripheral enrichment are `degraded`.

**Why two layers:**
The structural layer is deterministic and cheap — it runs in microseconds with no LLM
call. The semantic layer adds judgment the structural layer can't provide: whether the
blocked items are actually important to the brief's goal. Count alone is misleading.

**Outcomes:**
- `go`: all skills available, run normally.
- `degraded`: some skills missing, but remaining work is sufficient. Gap items are
  committed to `paths/not_taken/` as skipped paths. A filtered `working_graph`
  (executable items only) is used for the wave loop.
- `no_go`: gaps are too central to the goal. Run aborts. `capability_checkpoint.json`
  is written with gap details. Status = `blocked_on_capabilities`.

**Short-circuit optimisation:**
If there are zero gaps, `viability_assess` returns `go` immediately without an LLM
call. The structural check is sufficient.

**Durable record:**
Even a `no_go` run is committed to git (`M-1-viability` milestone). The gap record
accumulates across runs — over time you can see which skills are repeatedly missing
and prioritise them.

---

### 4. Tools vs Skills — The Naming and Architecture Decision

**Decision:** Distinguish clearly between *tools* (callable functions) and *skills*
(abstract abilities). Work items declare required skills. Skills map to tools.

**Tools:**
A single callable function an agent can invoke. Atomic, defined inputs/outputs.
- `perplexity_search(query: str) -> SearchResult`
- `web_browse(url: str) -> BrowseResult`
- `code_execution(code: str) -> ExecutionResult`

Tools are implementations. They live in `src/slow_ai/tools/`.

**Skills:**
The abstract ability to do a type of work. A skill may require one or more tools.
- `web_search` → tools: `[perplexity_search]`
- `web_browse` → tools: `[web_browse]`
- `code_execution` → tools: `[code_execution]`
- `statistical_analysis` → tools: `[code_execution]` (synthesized)
- `ontology_engineering` → tools: `[code_execution]` (synthesized)

Skills are what work items *require* and what agents *have*. They live in the skill
registry at `src/slow_ai/skills/registry.json`.

**Why this matters for the future:**
The skill layer is the integration surface. Adding an open source tool from openclaw,
nemoclaw, opencode, or any other repository means:
1. Add the tool implementation to `src/slow_ai/tools/`.
2. Add a skill entry to the registry mapping the skill name to the tool.
3. Every work item that declares that skill now gets the tool automatically.
No rewiring of agents, prompts, or orchestration needed.

**Agent tool assignment:**
At dispatch time, the runner resolves: `work_item.required_skills` → skill registry
→ `tools_for_skills()` → `AgentContext.tools_available`. The specialist agent then
registers only the tools it was granted. This is explicit and auditable.

---

### 5. Skill Format — JSON vs Markdown

**Decision (deferred):** Currently JSON (`registry.json`). Will migrate to per-skill
markdown files with YAML frontmatter when the registry grows beyond ~10 skills.

**The markdown format advantage:**
Each skill file can carry both structured metadata (frontmatter) and prose documentation
(when to use, failure modes, example outputs). Makes the skill library browsable,
diffable, and contributable without touching a central file.

```markdown
---
name: statistical_analysis
tools: [code_execution]
source: synthesized
tags: [analysis, compute]
---

Run statistical analysis using Python. Use pandas, scipy, or numpy. Always print()
results. Suitable for descriptive statistics, correlation analysis, time series.
```

**Why deferred:**
Two skills don't justify a parser dependency. Migrate when the registry grows and
authoring experience matters more than simplicity.

---

### 6. Skill Synthesizer — On-the-Fly Skill Generation

**Decision:** When skill gaps are detected, before declaring `no_go`, a `synthesize_skills`
agent attempts to resolve each gap by mapping it to existing tools.

**The mechanism:**
1. Skill gap detected (e.g., `statistical_analysis` missing).
2. Synthesizer LLM receives: list of missing skills + all available tools in registry.
3. For each gap, decides:
   - **Synthesizable**: maps to existing tools. Produces a `SynthesizedSkill` entry.
   - **Needs new tool**: cannot be satisfied. Adds to `needs_new_tool` list and
     generates a GitHub search query for a suitable tool.
4. Synthesized skills are written to `registry.json` immediately (persisted).
5. Structural resolution re-runs with the expanded registry.
6. Viability assessment re-runs on the new gap set.

**Key insight — most skills map to `code_execution`:**
`data_transformation`, `statistical_analysis`, `knowledge_graph_modeling`,
`ontology_engineering`, `rdf_serialization`, `data_visualization`, `document_parsing`
— all of these amount to "write and run Python code". Once `code_execution` is in the
registry, the synthesizer can resolve most gaps to it immediately.

`web_search` + `web_browse` covers: `domain_analysis`, `literature_review`,
`source_discovery` — any skill that amounts to "find information and reason over it".

**The accumulation flywheel:**
```
Run 1: skill gap detected → synthesizer runs → new skills written to registry
Run 2: those skills are already in registry → no synthesis needed → faster
Run N: registry is rich → most runs go straight to execution
```

Every run that hits a new gap makes the next run cheaper. The system learns from
its own limitations.

**Persistence:**
Synthesized skills are persisted immediately in `synthesize_skills()` before returning.
They are also committed to git as part of the `M-1-viability` milestone, so the
expansion of the registry is part of the run's durable record.

---

### 7. `code_execution` as a First-Class Tool

**Decision:** Add a Python code execution tool (`src/slow_ai/tools/code_execution.py`)
that runs arbitrary Python in an isolated subprocess with a timeout.

**Implementation:**
- Write code to a temp file.
- Run via `asyncio.create_subprocess_exec(sys.executable, tmp_path)`.
- `asyncio.wait_for()` enforces the timeout (default: 30s).
- Returns `{success: bool, stdout: str, stderr: str}`.
- Temp file is always cleaned up in `finally`.

**Why subprocess over `exec()`:**
- True isolation: a crash in the code doesn't crash the agent process.
- Timeout enforcement is clean via `asyncio.wait_for`.
- The same Python environment is used, so installed libraries (pandas, rdflib,
  geopandas) are available without configuration.

**Agent interface:**
```python
execute(code: str) -> str  # JSON-encoded {success, stdout, stderr}
```
The agent writes Python, calls `execute()`, reads stdout. Results must be `print()`ed
— return values are not visible.

---

### 8. The Broader Vision — Beyond Research

**Decision:** The architecture is deliberately domain-agnostic. Research is the first
instantiation, not the definition.

**What makes it general:**

- **Context graph**: decomposes any goal into dependency-ordered work. Legal audits,
  due diligence, regulatory compliance, clinical protocol reviews, software security
  assessments — any structured multi-step investigation.

- **Skills + tools**: swap the skill registry and you swap the domain. A legal system
  has `document_parsing`, `precedent_search`, `clause_analysis`. A financial system
  has `market_data_retrieval`, `ratio_analysis`, `risk_modeling`. The orchestration
  is identical.

- **Human in the loop**: already a first-class primitive (`escalate_to_human`). The
  file-based checkpoint contract is in place. Full blocking resume (Phase 3) is the
  remaining implementation work. Once done, humans and agents hand off as a normal
  workflow step, not an exception handler.

- **Auditability**: git per run, `paths/not_taken/` for skipped paths, milestone
  commits at every decision point. In regulated domains (legal, financial, medical)
  this is a requirement, not a nice-to-have.

- **Accumulation**: the skill registry grows with every run. A system doing due
  diligence on 50 companies learns from each one. The registry after 50 runs is
  fundamentally more capable than after 1.

**The value proposition:**
Speed is traded for reliability, traceability, and the ability to inspect and rerun.
That is exactly what high-stakes, long-horizon work requires. "Slow AI" is the right
name — provenance over pace.

---

## Architectural Invariants

These are decisions that should not be revisited without strong reason:

1. **Subprocess per run** — Streamlit's `nest_asyncio` + Google GenAI SDK's `anyio`
   cannot share an event loop. Subprocess is the permanent clean fix. Do not suggest
   threading alternatives.

2. **Context graph before agent assignment** — the blueprint (what needs to happen)
   must be separated from execution (who does it). This enables completeness checks,
   replayability, gap detection, and retrospective clarity.

3. **Dependency-aware waves** — wave ordering is enforced in code via
   `_ready_work_items(graph, covered)`, not left to the LLM. Deterministic, not
   approximate.

4. **File-based live contract** — the execution plane writes JSON to `runs/{id}/live/`.
   The UI polls those files. No shared state, no threading, no asyncio coupling. Any
   future UI can replace Streamlit without touching the execution plane.

5. **Git as the execution record** — artefacts, envelopes, assessments, and registry
   snapshots are committed at every milestone. The git log is the audit trail.

6. **Skills are not tools** — work items declare skills (abstract abilities). The
   registry resolves skills to tools. Agents receive tools. These three layers must
   remain distinct.
