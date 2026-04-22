# Slow AI — Technical Deep Dive

A design-first walkthrough of the system. Not a reference manual — a narrative.
Each section explains the *why* before the *what*, built from the ground up through
a conversation with the system's architect.

---

## Part 1 — The Bird's Eye View

Before anything else, here is the complete picture of the system in one diagram.

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
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   CONTEXT GRAPH  (artifact)                 │ │
│  │   phases · work items · dependencies · viability gate       │ │
│  └─────────────────────────────┬───────────────────────────────┘ │
│                                │                                  │
│    ② Orchestrator reads + drives swarm                           │
│                                │                                  │
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

### What the diagram is saying

The system has several distinct layers, each with a clear responsibility.
The key insight is in the agentic layer: **an agent designs the workflow,
then a swarm executes it.**

This is not a pipeline where nodes are wired together in advance. The workflow
itself is a first-class artifact — a context graph — that emerges from a
conversation between the human and a planning agent. The graph is reviewed,
refined, and approved by the human before a single specialist runs. Only then
does the orchestrator read that graph and drive the swarm through it.

The three-way collaboration inside the agentic layer is equally important:
- **Agents** select which model to use for each task (via BYOFM)
- **Agents** select which tools to invoke (via the skills registry)
- Neither the model nor the tools are hardcoded — every agent call is a
  runtime decision

Everything that runs is committed to **git**. Every envelope, every artefact,
every phase summary, every approved graph. The git layer is not a backup —
it is the system of record. The RL layer sits as a sidecar, reading from
that record to fine-tune models and update the skill registry over time.

### The one-sentence version

> An agent designs the workflow. The workflow becomes the contract.
> A swarm executes against it. Everything is committed to git.
> The RL layer learns from what happened.

---

*Next: Part 2 — The Agentic Layer (agents, BYOFM, skills and tools)*

---

## Part 2 — The Agentic Layer

The agentic layer is not a single agent. It is a collaboration between three things
that work together at runtime: **agents**, **the model registry (BYOFM)**, and the
**skills and tools registry**. None of the three is useful without the other two.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          AGENTIC LAYER                              │
│                                                                     │
│  ┌───────────────────┐    ┌─────────────────┐    ┌───────────────┐ │
│  │      AGENTS       │    │   MODEL REGISTRY │    │   SKILLS &   │ │
│  │                   │    │     (BYOFM)      │    │    TOOLS     │ │
│  │  Interviewer      │    │                  │    │              │ │
│  │  Planner    ──────┼───▶│  reasoning slot  │    │  perplexity  │ │
│  │  Orchestrator     │    │  fast slot       │    │  web_browse  │ │
│  │  Specialist ──────┼───▶│  code slot  ─────┼───▶│  code_exec   │ │
│  │  Synthesiser      │    │  specialist slot │    │  prior_evid. │ │
│  │  Assessor   ──────┼───▶│                  │    │              │ │
│  └───────────────────┘    │  any provider:   │    │  registry.   │ │
│                           │  Google · OpenAI │    │  json maps   │ │
│                           │  Anthropic · any │    │  skill →     │ │
│                           │  OpenAI-compat.  │    │  tool fn     │ │
│                           │  (Ollama, vLLM)  │    │              │ │
│                           └─────────────────┘    └───────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### The agents

Five agent roles, each with a distinct responsibility:

| Agent | Role | Model slot |
|---|---|---|
| **Interviewer** | Elicits a structured brief from free-form conversation | `fast` |
| **Planner** | Generates the context graph from the brief | `reasoning` |
| **Orchestrator** | Drives the swarm through the approved graph | `reasoning` |
| **Specialist** | Executes one work item using tools | `specialist` |
| **Synthesiser / Assessor** | Consolidates phase output, assesses confidence | `fast` / `reasoning` |

The agents are not a hierarchy. They are a sequence of hand-offs, each agent
consuming the output of the last and producing a structured artifact for the next.

### BYOFM — the model registry

Every model slot is defined in a single JSON file:

```json
{ "name": "reasoning",   "model_id": "google-gla:gemini-2.5-pro",
  "use_for": ["context_planning", "orchestration", "assessment"] }

{ "name": "fast",        "model_id": "google-gla:gemini-2.5-flash",
  "use_for": ["skill_synthesis", "report_synthesis", "interview"] }

{ "name": "code",        "model_id": "google-gla:gemini-2.5-pro",
  "use_for": ["code_generation"] }

{ "name": "specialist",  "model_id": "google-gla:gemini-2.5-pro",
  "use_for": ["specialist_research"] }
```

Agents declare what *kind* of reasoning they need. The registry resolves which
model does that best today. This is a deliberate design choice — and the reason
for it is simple: **the model leaderboard moves faster than agent code should.**

When a better reasoning model appears, one JSON entry changes. Every agent that
uses that slot benefits immediately. No code is touched.

The slot abstraction also manages cost by design. Simple, well-defined tasks
(synthesis, interview, skill mapping) go to fast, cheap models. High-stakes
decisions (planning, orchestration, assessment) go to the most capable reasoning
model available. The routing happens automatically from the task type — no
manual budget configuration needed.

The longer vision is richer still. The slot abstraction already supports domain
specialist models: a geospatial reasoning model, a legal reasoning model, a
biomedical literature model. Add a new slot, point it at a specialist model, and
any agent that needs that capability can declare it. The architecture does not need
to change.

Out of the box, the curated defaults are Gemini models — one API key and the
system runs. Swap any slot to OpenAI, Anthropic, Ollama, vLLM, or any
OpenAI-compatible endpoint without touching agent code. For regulated environments
where data cannot leave the perimeter, point every slot at a local Ollama instance.
The agents do not know or care.

### The bootstrap inside the agentic layer

The agentic layer runs in two distinct phases, and the context graph is the
artifact that separates them:

```
  ① DESIGN PHASE
  ──────────────
  Interviewer ──▶ ProblemBrief ──▶ Planner ──▶ ContextGraph
                                                     │
                                              human reviews
                                              + approves
                                                     │
  ② EXECUTION PHASE                                  ▼
  ────────────────                         ContextGraph (approved)
  Orchestrator reads graph                           │
        │                                            │
        └──────────────────────────────────────────▶ drives
                                                     │
                                              Specialist swarm
                                              (wave loop)
                                                     │
                                              Synthesiser
                                              Assessor
```

The context graph is not a configuration file written by a human. It is generated
by the planner agent from the brief, reviewed in a chat interface, and approved by
the human before execution begins. The human reviews the *shape of the work*, not
the implementation details. This is the right level of abstraction for human oversight.

---

*Next: Part 3 — Skills and Tools (the registry, how capabilities accumulate)*

---

## Part 3 — Skills and Tools

Tools are primitives. Skills are compositions.

This distinction is the foundation of how Slow AI accumulates capability over time.
A tool is a concrete callable — a function that does one atomic thing. A skill is a
named combination of tools applied in a specific way to solve a specific class of
problem. The same tools, composed differently, produce different skills.

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

Skills compose other skills. The registry is not flat — it is a graph.
`remote_sensing_analysis` is built from `geospatial_processing`, `image_analysis`,
and `api_integration`, each of which is itself a synthesized skill built on
`code_execution`. Everything ultimately bottoms out at four atomic tools.

Domain-specific skills like `german_healthcare_expertise` and
`spanish_agricultural_expertise` were not designed upfront. They were synthesized
when runs encountered those domains and needed capabilities that didn't exist yet.
The registry grew to capture what was learned.

### Alignment with the emerging standard

Anthropic published Agent Skills in December 2025 — a standard format for
composable, portable agent capabilities: a `SKILL.md` file plus a scripts directory
per skill, importable across Claude apps, Claude Code, and any API consumer.

The mental model is identical to what Slow AI built independently: named,
composable capabilities that specialize a general-purpose agent for a specific
class of work. The implementation format differs — the current Slow AI registry
is JSON-based — and migrating to the `SKILL.md` standard is a planned step.
Building against a proprietary schema when a standard exists would create an
import wall, preventing skills built elsewhere from being loaded, and skills
built here from being shared.

> **Note:** The technical implementation of this migration — how the synthesiser,
> viability gate, and skill loader adapt to the directory-based format — is covered
> in a separate implementation section.

### Success rates and the human signal

Skills are not just defined — they are evaluated. The signal is behavioral:
if a human continues past a run, engages with the output, and comes back for
the next one, that is evidence that the skills used in that run, in that context,
with that combination of tools, worked.

This is revealed preference, not a rating form. The corpus of
`(skill, tools, context, human continued)` triples accumulates across every run
and feeds the RL layer. No survey. No star rating. The action speaks.

### The vision: APIs, MCPs, and a governed tool ecosystem

Every new tool added expands the space of synthesizable skills. A new API
integration unlocks dozens of potential skills. An MCP server unlocks a whole
category. The vision is a growing ecosystem: proprietary APIs, open data portals,
MCP servers (GitHub, Notion, Linear, databases), domain-specialist models.

Critically, tools are added by humans — not discovered autonomously by agents.
An agent *could* search for and load a new tool at runtime. But that introduces
unreviewed code and unvetted capabilities into the execution path. The safer
design: the system knows what it cannot do, says so clearly, and surfaces the
gap as a concrete capability item for a human to close. The tool ecosystem grows
deliberately, not opportunistically.

---

## Part 4 — The Workflow Layer

### The context graph

Most workflow tools ask you to draw the workflow. Slow AI asks you to describe
the problem — and proposes the workflow for you.

The context graph is not a DAG of agent calls. It is a representation of how
a human expert thinks about decomposing a big problem: overarching topics first,
without diving into the specifics of every activity. A compass, not a map.

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
- **What** needs to be investigated (work items, named clearly)
- **When** — the dependency ordering between phases
- **Why it is structured this way** — the narrative summary the planner generates
  after every plan or refinement, explaining the logic of the breakdown

The graph is not a configuration file written by a human. It is generated by the
planner agent from the brief, then presented to the human expert in a chat
interface. The question being asked — implicitly, at every graph review — is:

> *"Do you see this problem the same way I do?"*

If the breakdown is wrong, there is no point running hundreds of agents against it.
This is the validation the graph review provides. The human either backs the LLM's
breakdown, refines it through natural language conversation, or redirects it
entirely. Only when the human approves the graph does execution begin.

The context graph is a **shared mental model**. When both the human expert and the
system agree on the shape of the problem, the work can start.

### The viability gate

Between graph approval and execution sits the viability gate. It runs two checks
in sequence:

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

The gate is the enforcement point for the governance decision: tools are added
by humans, not discovered by agents. When a gap is found, the system does not
go looking for a tool to fill it. It names the gap, describes what tool would
be needed to close it, and surfaces that as a concrete item for a human to act on.

*"If the direction is not clear, there is no point running hundreds of agents on it."*

The viability gate is where that principle is enforced.

### The wave loop

Once the graph is approved and the viability gate passes, the orchestrator begins
the wave loop. Phases execute sequentially — the output of one phase informs the
next. Work items within each phase execute in parallel.

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
  │  Phase 2  ──────────────────────────────┐  │
  │  │  (receives Phase 1 summaries)        │  │
  │  │  work item D  ──▶ envelope D  (par.) │  │
  │  └──────────────────────────────────────┘  │
  │       │                                     │
  │       ▼                                     │
  │  ...                                        │
  │       │                                     │
  │       ▼                                     │
  │  Final synthesis ──▶ run summary            │
  └─────────────────────────────────────────────┘
```

Every phase boundary is a consolidation checkpoint. The synthesiser reads all
envelopes from the completed phase and produces a phase summary. The assessor
evaluates confidence and flags whether the next phase should proceed, pause for
human review, or escalate. The system cannot skip ahead — it must consolidate
what it knows before it opens new lines of inquiry.

---

*Next: Part 5 — The Processing Layer (sandboxed execution, the venv per run)*

---

## Part 5 — The Processing Layer

The processing layer exists because of a principle borrowed from distributed systems:
**blast radius**.

Before granting any process permissions, answer one question: *if this goes wrong,
what is the worst it can do?* The answer determines the isolation boundary. For an
agent swarm running arbitrary Python code against the web, the answer without
isolation is: *it can affect everything*. With isolation, the answer is:
*it can only affect itself.*

This principle — and four others — were the founding design constraints of Slow AI,
articulated in [Agents Are Just Distributed Systems](https://nischalhp.substack.com/p/agents-are-just-distributed-systems)
before a line of code was written. The processing layer is where those constraints
become concrete.

### Sandboxed subprocess per run

Every run executes in its own subprocess, with its own `uv` virtual environment,
scoped entirely to that run's artefacts directory.

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

Three things this isolation gives you:

**1. Parallel runs without interference**
Multiple runs can execute simultaneously. Once the React frontend is live, users
will not babysit a single run — they will start one, move on, and come back to
results. Subprocess isolation means no shared state, no lock contention, no run
affecting another's output.

**2. Blast radius containment**
If a run's generated code hangs, consumes excessive memory, or hits an unexpected
error, the damage is contained to that subprocess. The rest of the system — other
runs, the UI, the agent registry — is unaffected. This is the circuit breaker
principle applied at the process boundary: isolate first, then limit.

**3. Dependency hygiene**
Each venv is created fresh from the run's requirements. Different runs can use
different library versions. A geospatial run installs `geopandas` and `rasterio`.
A data analysis run installs `polars` and `scipy`. Neither pollutes the other.
The global environment stays clean. Dependency hell is not managed — it is
structurally prevented.

### Bandit security scanning

Before any agent-generated code executes, it is scanned with `bandit` — a static
analysis tool for Python security issues:

```
  Agent generates code
        │
        ▼
  bandit scan
        │
   ┌────┴────────┐
   │             │
  HIGH         MEDIUM / LOW
   │             │
  BLOCK        WARN / silent
   │             │
  run halts    code executes
```

This is the Byzantine Fault Tolerance principle in practice: the system does not
trust its own agents' output. Generated code is treated as untrusted until it
passes inspection. An agent that returns a clean result but produced dangerous
code does not get to run that code.

### The distributed systems principles

The five principles from distributed systems that shaped this layer — and the
system as a whole:

| Principle | What it means here |
|---|---|
| **Blast radius** | Sandbox every run. Scope permissions to the minimum needed. |
| **Circuit breakers** | Isolate failures. One run cannot cascade into another. |
| **Byzantine fault tolerance** | Do not trust agent output. Require evidence envelopes. Scan generated code. |
| **Idempotency** | Runs can be repeated. Envelopes are replayable. Git preserves every state. |
| **MAPE-K** | Separate observation from execution. The live files are the observable state. The UI reads them; the runner writes them. |

These are not abstractions layered on top of an existing design. They are the
design. The architecture was built to satisfy them before the first agent was
written.

---

*Next: Part 6 — The Memory Layer (runs, artefacts, envelopes, HITL, and git as the system of record)*

---

## Part 6 — The Memory Layer

The memory layer exists to answer one question: **how do you trust what an agent did
if you cannot verify it?**

This is not a philosophical question. In a system where agents generate code,
make tool calls, produce reasoning, and synthesise evidence across dozens of
concurrent processes — none of which you can observe directly — trust requires
a verifiable record of everything that happened. Not a summary. Not a log file.
Every intermediate state, every decision, every artefact, versioned and inspectable.

Git provides this. Not as an afterthought — as the design.

### What gets versioned

For every run, the following are committed to git at defined milestone points:

```
  runs/{run_id}/
    input_brief.json        ← the contract that started the run
    input_graph.json        ← the approved context graph
    envelopes/              ← one per specialist: evidence, confidence, verdict,
    │                          tool calls made, reasoning shown
    artefacts/              ← generated code, data, visualisations
    live/                   ← dag.json, status.json, phase summaries (UI reads these)
    conversation.jsonl      ← full HITL history: interview, graph review, post-run
    runner.log              ← structured log: every milestone, every error
```

What this means in practice:

| What you want to know | Where to look |
|---|---|
| What was the original research goal? | `input_brief.json` |
| What workflow did the human approve? | `input_graph.json` |
| What did agent X actually find? | `envelopes/{agent_id}.json` |
| What code did the agent write and run? | `artefacts/*.py` + git diff |
| What model was used for which task? | envelope metadata + model registry snapshot |
| What did the human say at review? | `conversation.jsonl` |
| Where did the run fail? | `runner.log` + git history |

### The coordination mechanism

Agents in a swarm do not communicate directly. They coordinate through the
versioned shared record. An orchestrator writes the plan. Specialists read their
work item and write their envelope. The synthesiser reads all envelopes and writes
the phase summary. Each step is a git commit.

This is idempotency in practice. Every operation produces a verifiable output
that is committed before the next operation reads it. If the system restarts, it
can resume from the last commit. If an agent produces unexpected output, the commit
is there to inspect. No silent failures. No lost state.

### Forking for experimentation

The most powerful property of a versioned run is not the audit trail — it is
the ability to branch.

```
  run A  ──────────────────────────────────────────▶  outcome A
    │
    │  fork at Phase 2 boundary
    │  (change: swap reasoning model, gemini-pro → claude-opus)
    │
  run B  ──────────────────────────────────────────▶  outcome B
    │
    │  fork at Phase 2 boundary
    │  (change: refine graph — split work item into two)
    │
  run C  ──────────────────────────────────────────▶  outcome C
```

For any run, at any milestone commit, you can fork: change the model, adjust the
prompt, refine the graph, add a tool — and observe what changes in the outcome.
This is the experimental substrate that makes a learning system possible. You
cannot improve what you cannot compare. You cannot compare what you have not
versioned.

The `(brief, graph, model, prompts, tools, envelopes, outcome)` tuple, fully
versioned and reproducible, is the training datum for the RL layer. The git
history is not a log. It is the dataset.

### The two-plane architecture

The memory layer makes a clean separation possible: the execution plane writes
files, the UI plane reads them. They share no in-process state.

```
  EXECUTION PLANE                     UI PLANE
  ───────────────                     ────────
  runner.py                           Streamlit / React
  orchestrator                        reads live/ via polling or SSE
  specialist agents                   reads envelopes/ on demand
        │                             reads conversation.jsonl
        │ writes                      reads runner.log
        ▼
  runs/{run_id}/live/
  runs/{run_id}/envelopes/
  runs/{run_id}/conversation.jsonl
        │
        ▼
  git commit  (at every milestone)
```

The UI never calls an agent. The execution plane never calls the UI.
The filesystem — versioned by git — is the interface between them.
Any future rendering layer (React, CLI, another API) plugs in without
touching the execution plane. The intelligence stays in Python.

---

*Next: Part 7 — The RL Layer (the learning loop, revealed preference, run chaining)*

---

## Part 7 — The RL Layer

The RL layer does not run during a research session. It is a sidecar — it watches,
accumulates, and learns. Its job is to make the system measurably better at planning
and execution with every run that completes.

### The trajectory corpus

Every run produces a trajectory: a sequence of states and actions from brief to
outcome, fully versioned in git. Over time, three distinct trajectory types
accumulate:

```
  TYPE 1 — Original agent path
  ─────────────────────────────
  Agent planned → swarm executed → human reviewed outcome
  No human intervention during execution.
  Outcome: continued (success) or abandoned (failure)

  TYPE 2 — Human-augmented path
  ──────────────────────────────
  Agent planned → human refined the graph → swarm executed
  → human intervened mid-run or at review → continued
  The human's corrections are part of the trajectory.
  Outcome: success (human participation made it better)

  TYPE 3 — Abandoned path
  ─────────────────────────
  Agent planned → swarm executed → human could not recover it
  Human participation could not make the output useful.
  Outcome: abandoned — signal of fundamentally bad planning
```

All three are training data. Type 1 successes show what works without help.
Type 2 trajectories show exactly where agent planning diverged from expert
judgment — and what correction looked like. Type 3 trajectories show the
failure modes that no amount of human intervention could fix.

### The sidecar model

The goal of RL is not to replace the foundational LLM. It is to produce a
**policy model** — a critic that runs alongside the foundational LLM, observing
every planning and execution decision and providing corrective signal.

```
  FOUNDATIONAL LLM  ─────▶  proposed action
                                  │
                                  ▼
                        POLICY MODEL (sidecar)
                        "is this the right next step?"
                        "what should change?"
                                  │
                         ┌────────┴────────┐
                         │                 │
                       good             adjust
                         │                 │
                         ▼                 ▼
                    proceed          corrected action
```

The sidecar reduces bad planning before it propagates into a swarm of agents.
A poor decomposition in the context graph, left uncorrected, means hundreds of
agent actions running in the wrong direction. The sidecar catches this at the
planning stage — where intervention is cheap — not at the synthesis stage where
damage has already been done.

### The RL formulation

The graph and sequence of agent actions is a delayed reward problem. No single
tool call, no single work item completion, produces the reward signal. The signal
arrives at the end — when a human continues with the output or abandons it.

This maps naturally to the Bellman equation:

```
  V(s) = R(s) + γ · max_a V(s')

  State s:    current graph + completed actions + evidence accumulated so far
  Action a:   next agent decision (plan step, tool call, synthesis move)
  Reward R:   delayed — human continuation is the signal, not per-step feedback
  Value V(s): expected future reward from this state — did this intermediate
              step contribute to an outcome a human found valuable?
```

The algorithm being considered for the policy model is **GRPO** — Group Relative
Policy Optimization. Rather than computing absolute rewards per trajectory, GRPO
compares groups of trajectories relative to each other: across comparable briefs,
which planning approach produced better outcomes? The policy learns from the delta
between variants, not from a fixed reward function.

This fits naturally with the forking design in the memory layer. Every experimental
branch — different model, different graph refinement, different tool combination —
is a new trajectory variant. The more variants you accumulate across comparable
briefs, the sharper the policy becomes.

### Episodes compound

The system improves with scale — not by retraining the foundational LLM, but by
accumulating episodes:

```
  Run 5:    limited trajectory variants · policy has weak signal
  Run 50:   multiple variants per brief type · policy identifies planning patterns
  Run 500:  rich cross-domain corpus · policy generalises across problem types
             human-augmented paths show where agent judgment diverges from expert
             abandoned paths show the failure modes to avoid entirely
```

Every fork, every human correction, every model swap is a new episode. Every
comparable brief run with a different configuration is a controlled experiment.
The git history is not a log. It is the dataset that makes this learning system
possible.

---

*Next: Part 8 — Human-in-the-Loop by Design (interview, graph review, post-run conversation)*

---

## Part 8 — Human-in-the-Loop by Design

The goal of Slow AI is not automation. It is augmentation.

Automation replaces human judgment. Augmentation extends it. These are different
design goals and they produce different systems. A system built for automation
removes the human from the loop as quickly as possible. A system built for
augmentation keeps the human at every moment where their judgment cannot be
replicated by a model.

There are three such moments. Each asks for a different kind of judgment.

```
  ┌─────────────────────────────────────────────────────────────────┐
  │  1. INTERVIEW                                                   │
  │     "Did the agent understand what I actually need?"            │
  │                                                                 │
  │  Kind of judgment: foundational                                 │
  │  The brief is the cornerstone of everything that follows.       │
  │  If the brief is wrong, the graph is wrong. If the graph is     │
  │  wrong, the swarm runs in the wrong direction. Every failure    │
  │  downstream can be traced to a brief that wasn't precise enough.│
  │                                                                 │
  │  The interview agent asks clarifying questions until the        │
  │  problem is specific enough to plan against. The human is not   │
  │  filling out a form — they are thinking through the problem     │
  │  out loud, and the agent is helping them become precise.        │
  └─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ ProblemBrief (committed)
  ┌─────────────────────────────────────────────────────────────────┐
  │  2. CONTEXT GRAPH REVIEW                                        │
  │     "Does this breakdown match how an expert would approach it?"│
  │                                                                 │
  │  Kind of judgment: directional                                  │
  │  The planner has decomposed the brief into phases and work      │
  │  items. The human now sees the shape of the proposed work.      │
  │  Is this how they would think about it? Are the right topics    │
  │  covered? Are the dependencies correct?                         │
  │                                                                 │
  │  The human can refine through natural language conversation.    │
  │  When they approve, they are not approving implementation       │
  │  details — they are confirming the direction. That is the       │
  │  right level of abstraction for expert oversight.               │
  └─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ Approved graph (committed) → swarm executes
  ┌─────────────────────────────────────────────────────────────────┐
  │  3. POST-RUN CONVERSATION                                       │
  │     "Did this output actually extend my thinking?"              │
  │                                                                 │
  │  Kind of judgment: evaluative                                   │
  │  The run is complete. The human reads the Perplexity-style      │
  │  summary, inspects the evidence envelopes, reviews the phase    │
  │  summaries. Then they can ask follow-up questions, request      │
  │  drill-downs, or generate a follow-on brief that seeds the      │
  │  next run with everything already learned.                      │
  │                                                                 │
  │  If they continue — they engage, they come back — that is the   │
  │  signal that the system augmented their thinking rather than    │
  │  just producing output. If they abandon it, the opposite is     │
  │  true. The action is the label.                                 │
  └─────────────────────────────────────────────────────────────────┘
```

### Why LLM-as-judge is not enough

An LLM can evaluate whether an output is well-structured, internally consistent,
and factually plausible. It cannot evaluate whether a hard problem was actually
solved in a way that is useful to a specific expert in a specific context.

For the kinds of problems Slow AI is designed for — due diligence, regulatory
analysis, strategic research, scientific synthesis — the quality of the output
determines the quality of everything built on top of it. A plausible-sounding
but subtly wrong analysis is worse than no analysis, because it provides false
confidence. Only the domain expert can provide ground truth on whether the output
is actually useful.

Human feedback is not a feature of the system. It is the source of the signal
that makes the system improve.

### HITL as the learning loop

Every human interaction in the system is a labeled training example:

| Interaction | What it labels |
|---|---|
| Interview correction ("that's not quite what I meant") | Brief generation quality |
| Graph refinement ("split this phase into two") | Planning decomposition quality |
| Graph approval | Planning accepted as correct |
| Mid-run escalation response | Specialist judgment quality |
| Post-run engagement | Full-run outcome quality |
| Abandonment | Full-run outcome failure |

The context graph, skill synthesiser, agent swarm, skills, tools — the final
outcome is the sum of all of these being mostly right. Learning requires feedback
on all of them. The HITL touchpoints are not just checkpoints for human safety —
they are the measurement instruments of a system that is designed to improve.

---

*Next: Part 9 — Run Chaining and the Learning Flywheel*

---

## Part 9 — Run Chaining and the Learning Flywheel

There is a pattern in how experts actually learn: knowledge reveals the boundary
of your ignorance.

Every research run converts **unknown unknowns into known unknowns**, and
**known unknowns into known knowns**. When you start a brief on protein folding,
you are mostly in the unknown unknowns — you don't know what you don't know.
The first run sheds light. Now you know what you know, and you know what you
still don't. The natural response to that is to go deeper. Follow the thread.

*Follow the white rabbit.*

A system that makes you start from zero every time is fighting human nature.
Starting over without building on top is not how experts actually think. Run
chaining is the mechanism that lets the system grow with the person using it.

### What the second run inherits

When a follow-on run is created, it does not get a dump of everything the prior
run produced. It gets a scoped selection — only what is relevant to the new brief.

```
  Run 1: "What is protein folding and why does it matter?"
    └── envelopes: basic mechanisms, AlphaFold overview, key researchers
    └── phase summaries: structure prediction landscape, open problems
    └── gaps identified: misfolding diseases, therapeutic implications (unexplored)

                │
                │  generate_follow_on_brief()
                │  reads: phase summaries + identified gaps
                │  produces: new ProblemBrief scoped to next question
                ▼

  Run 2: "What are the therapeutic implications of protein misfolding?"
    └── prior_run_ids: [run_1]
    └── read_prior_evidence tool: specialists can pull specific envelopes
        from run_1 when relevant — not by default, only when needed
    └── context graph: shaped by what run_1 already covered — no duplication
    └── envelopes: misfolding mechanisms, disease targets, pipeline landscape
```

The key design decision: prior evidence is **pull, not push**. The second run's
specialists know prior runs exist. They can call `read_prior_evidence` to retrieve
specific findings when their work item needs them. They do not receive a broadcast
of everything. Memory is scoped to what the current task actually requires.

This prevents context pollution — the failure mode where prior runs flood the
context window and degrade the quality of new reasoning. The system knows more,
but it retrieves selectively.

### The compounding trajectory

```
  Run 1  →  "I know the basics. I now know what I don't know."
              gaps: misfolding, therapeutics, computational methods

  Run 2  →  "I understand misfolding. I now know what I still don't know."
              gaps: specific disease mechanisms, clinical pipeline

  Run 3  →  "I understand the clinical landscape. I'm building real expertise."
              gaps: regulatory pathway, key players, investment thesis

  Run N  →  Expert-level synthesis, built incrementally,
              each run standing on the shoulders of the last.
```

This is the trajectory that most systems are missing. Not a one-shot answer —
a compounding understanding, built the way human expertise actually builds:
curiosity, investigation, synthesis, new questions, repeat.

### The brief as the continuity mechanism

The `generate_follow_on_brief` function reads the completed run's phase summaries
and identified gaps, and produces a new `ProblemBrief` that:

- Scopes the next question to what remains unexplored
- Carries forward the domain framing from prior runs
- References the completed run ID so specialists know where to look for prior evidence
- Does not repeat work already done

The brief is the continuity mechanism between runs. The human reviews it —
confirming the next question is the right one — before the next run begins.
The human stays in control of the direction. The system remembers where they've been.

### The flywheel

```
       curious expert
             │
             │ starts a brief
             ▼
        Run 1 executes
             │
             │ unknown unknowns → known unknowns
             ▼
        follow-on brief generated
        human approves next question
             │
             ▼
        Run 2 executes
        (builds on Run 1, pulls prior evidence selectively)
             │
             │ known unknowns → known knowns
             │ new unknown unknowns surface
             ▼
        ...
             │
             ▼
        Expert with deep,
        verifiable, compounding
        understanding of the domain
```

Every run is a training episode for the RL layer. Every follow-on brief is a
labeled example of what a good next question looks like given prior findings.
Every human approval or abandonment is a reward signal. The more the system
is used, the better it gets at knowing which threads are worth following.

The system learns. The expert deepens. The two compound together.

---

*The technical deep dive is now complete as a first draft. The nine parts cover:*
*bird's eye view → agentic layer → skills & tools → workflow layer → processing*
*layer → memory layer → RL layer → HITL design → run chaining.*

