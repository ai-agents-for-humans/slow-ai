# Slow AI — Website Content

---

## Hero

**Orchestrate any work. With any model. With full provenance.**

Slow AI is an open-source agentic work orchestration platform. Define the work.
Declare the skills. Bring your own models. The system plans, validates, executes,
and gets better every time it runs.

Human experts stay in control — approving plans, steering execution, and reviewing
evidence before it becomes a decision. Every agent action is visible. Every output
is provable. You do not have to trust the system blindly. The system earns trust by
showing its work.

**CTA:** Get started on GitHub

---

## The Problem

Most AI agent frameworks are built for demos.

They assume a single provider, a fixed set of tools, and an optimistic execution
path. They produce answers — not evidence. When something goes wrong, you cannot
tell whether an agent hallucinated, missed a source, ran out of budget, or simply
gave up. There is no plan to inspect, no record to audit, and no way to know
whether the next run will do better.

Real work is not like this.

It involves dead ends. Partial answers. Conflicting sources. Decisions that only
make sense when you understand the reasoning that produced them. It involves human
experts who need to review, redirect, and sign off before the work is used. It
involves repeating the same type of task across different inputs — and expecting
the system to improve over time.

Slow AI is built for this.

---

## What It Is

Slow AI is a **general-purpose agentic work orchestration platform** built on
distributed systems principles.

It turns any structured work — research, software delivery, content production,
incident response, compliance monitoring, sales intelligence — into a directed
graph of tasks with declared skill requirements. Specialists execute the graph
wave by wave, in dependency order, with scoped permissions and a full audit trail.

Human experts are embedded in the process — not bolted on at the end. They can
inspect the plan before a single agent fires, approve waves before they execute,
inject context mid-run, and correct agent conclusions before they propagate.
Everything the system does is visible, provable, and correctable by the people
who know the domain best.

The domain changes. The principles do not.

---

## How It Works

### 1. Brief

A consultant agent interviews you to build a precise `WorkBrief`. Vague goals
produce bad work. Slow AI makes you specific before it starts — one question at a
time, pushing back on ambiguity and surfacing assumptions you have not stated.

### 2. Context Graph

A planning agent decomposes the brief into a directed acyclic graph of work items.
Each node declares the skills it needs. Dependencies between nodes are explicit.
Nothing runs out of order.

The graph is the plan — visible and inspectable before a single agent fires. Domain
experts can review it, challenge it, and approve it. The graph externalises the
system's reasoning about how to approach the work, so the humans who own the domain
can validate the approach before any resources are spent.

### 3. Viability Gate

Before execution begins, the system checks whether the declared skills can be
satisfied. Missing skills trigger the synthesizer, which maps abstract requirements
to existing tools and writes new entries to the skills registry for every future
run.

If coverage is zero, the run does not proceed — and the gap record tells you
exactly what needs to be built or sourced. If partial, it runs in degraded mode
on the executable subgraph, surfacing the gaps so a human can decide whether to
proceed or wait for full coverage.

### 4. Wave Execution

Work items execute in dependency order, wave by wave. Each specialist agent
receives only the tools its work item requires, a scoped memory budget, and context
from upstream results.

At any wave boundary, a human expert can inspect the evidence collected so far,
correct any findings that are off-track, and approve or redirect the next wave
before it fires. Agents that exhaust their budget surface remaining work explicitly
rather than hallucinating completeness.

### 5. Synthesis and Commit

A synthesis agent assembles all evidence envelopes into a final output. Every
claim traces back to a specific agent, tool call, and timestamp. Every artefact —
documents, code, data — is committed to git alongside the run that produced it.

Experts can read the full record before acting on the output. The system earns
trust because every conclusion comes with proof.

---

## Not Just Research

Research was the first domain. The architecture is not research-specific.

The orchestration layer — context graph, viability gate, wave executor, skills
registry — is a general engine. The domain is a parameter. What changes between
domains is the brief type, the skills declared, and the tools in the registry.

| Domain | Brief | Skills needed |
|---|---|---|
| Research & intelligence | Investigation question | web_search, data_analysis, code_execution |
| Software delivery | Feature specification | code_generation, run_tests, open_pr, code_review |
| Content production | Content brief | draft_document, web_research, edit, publish |
| Sales intelligence | Target account | company_research, crm_enrichment, draft_outreach |
| Incident response | Incident description | query_logs, run_diagnostics, page_oncall, draft_postmortem |
| Compliance monitoring | Regulation change | scan_policies, flag_gaps, assess_risk, draft_report |
| Due diligence | Target company | financial_analysis, market_research, legal_review |
| Engineering assessment | Technical question | repo_analysis, benchmark, code_execution, document |

The platform does not change. The `registry.json` and the context planner change.

---

## The Accumulation Flywheel

Every time a run hits a skill gap, one of two things happens:

**Option A:** The synthesizer maps the missing skill to existing tools and writes a
new entry to the skills registry. Future runs that need the same skill pay zero
overhead. The gap is closed permanently.

**Option B:** If no mapping is possible, the system surfaces the genuine tool gap
with concrete search queries — so you know exactly what to build, import from an
MCP server, or pull from an open source skills repository.

Over time, your platform accumulates skills. The registry grows. The rate of
degraded runs falls. Each run makes the next run better.

This is not a static product. It is a compounding system.

---

## Bring Your Own Models

Slow AI does not care which model you use.

Different tasks benefit from different models. Context planning benefits from deep
reasoning. Synthesis benefits from speed and structured output. Code generation
benefits from code-specialist models. Interview benefits from conversational fluency.

The model registry routes each task type to the right model. Swap models without
touching a single line of agent code.

```json
{ "name": "reasoning", "model_id": "google-gla:gemini-2.5-pro",    "use_for": ["context_planning", "orchestration"] }
{ "name": "code",      "model_id": "ollama:qwen2.5-coder:7b",       "use_for": ["code_generation"] }
{ "name": "fast",      "model_id": "openai:gpt-4o-mini",            "use_for": ["skill_synthesis", "report_synthesis"] }
{ "name": "local",     "model_id": "llama3.1:70b",                  "use_for": ["specialist_research"] }
```

**Supported:** Google, OpenAI, Anthropic, and any OpenAI-compatible endpoint —
Ollama, vLLM, LM Studio, or any private inference server.

For regulated industries, this means sensitive data never leaves your
infrastructure. Every model in the pipeline runs locally. The platform is entirely
yours.

---

## Distributed Systems Discipline

Slow AI applies lessons from distributed systems to agent orchestration — because
agents are distributed systems. The failure modes are identical. The solutions have
existed for thirty years.

**Blast radius** — every agent operates with minimum permissions. Tools are granted
explicitly based on the skills required by the work item. An agent that needs
web_search cannot touch code_execution.

**Circuit breakers** — the orchestrator knows about every agent. When a threshold
is breached — time, tokens, cost — the circuit opens. The agent stops. The state
is preserved. Nothing is lost.

**Evidence over verdicts** — agents do not return verdicts. They return evidence
envelopes containing proof: sources checked, findings, confidence scores, artefact
filenames. The synthesis is only as good as the evidence behind it.

**Idempotency** — every agent action is safe to run twice. Execution state lives
outside the agents, in a git repository. If a run fails at any depth, it resumes
from the last committed milestone.

**MAPE-K** — Monitor, Analyse, Plan, Execute, with a shared Knowledge base. The
context planner plans. Specialists execute. The git repository is the knowledge
base — the permanent, versioned record of what every agent in every run knew and
did.

---

## Human in the Loop

Human involvement is a first-class design primitive — not an exception handler.

The orchestrator can decide at any milestone that the run should pause for human
review. The full run state is preserved. Every artefact produced up to that point
is committed and inspectable. When the human approves, the run resumes exactly
where it paused.

Three things make this work:

**Git as the inspection surface** — every artefact, every evidence envelope, every
agent memory is a versioned file. A human expert can read the full record and
verify every claim before deciding whether to continue, redirect, or stop.

**Structured pause, not a crash** — nothing is lost, nothing is re-run. The system
waits. The human decides on their schedule, not the system's.

**Granular intervention** — a human can edit artefacts directly in git before the
next wave fires. The edit is itself a commit — part of the audit trail, not outside
it. Human judgment becomes part of the provenance record.

The result is a system where experts stay in the loop not as a concession to
distrust, but as a design feature. The human's domain knowledge improves the
output. The system's provenance gives the human the context they need to intervene
effectively. Each makes the other more capable.

---

## Architecture

```
WorkBrief (confirmed by domain expert)
    │
    ▼
Context Graph ─── DAG of WorkItems, each with required_skills
    │              (visible and reviewable before execution)
    ▼
Viability Gate ──► Skills Synthesizer ──► Skills Registry (grows every run)
    │
    ├── no_go: coverage = 0%, run aborted with gap record
    ├── degraded: partial coverage, executable subgraph only
    └── go: full coverage
    │
    ▼
Wave Executor (dependency-ordered, budget-scoped)
    ├─ Specialist Agent (tools scoped to work item skills)
    ├─ Specialist Agent           ◄── human can inspect and correct
    └─ Specialist Agent               between any two waves
    │
    ▼
Evidence Envelopes → Synthesis → Final Output
    │                             (every claim has a source)
    ▼
Git commit (run branch, artefacts, generated code, full audit trail)
```

**Two independent planes sharing nothing but files on disk.** The execution plane
writes JSON to `runs/{run_id}/live/`. The UI polls those files every five seconds.
Any future UI — React, CLI, API — can replace the current Streamlit app without
touching the execution engine.

---

## Use Cases

**Financial services**
Competitive intelligence, market structure analysis, regulatory horizon scanning.
Models run on-prem. No sensitive thesis leaves the perimeter. Analysts review the
context graph before execution and approve the synthesis before it becomes a
decision input.

**Life sciences**
Literature synthesis, clinical trial landscape mapping, target identification.
Code-execution agents pull and process structured datasets. Scientists inspect
every evidence envelope before the synthesis propagates to downstream decisions.

**Management consulting**
Due diligence, market sizing, operational benchmarking. The context graph
externalises the research plan so partners can review the approach before a single
token is spent. HITL gates ensure the right people sign off at each wave.

**Legal and compliance**
Policy monitoring, jurisdiction comparison, contract clause analysis. Agents surface
gaps with confidence scores and citations. Nothing is finalised without expert
review. Every conclusion is auditable to a specific source document.

**Engineering teams**
Technical landscape assessment, library evaluation, architecture decision research.
Code agents generate working prototypes and commit them alongside the report. Every
generated file is auditable in git.

**Operations and incident response**
Alert triage, root cause investigation, runbook execution, postmortem drafting. The
DAG enforces the right order. Human gates prevent automated actions on ambiguous
signals. The full investigation is committed and searchable after every incident.

---

## What's Coming

### V2 — Observe, Coordinate, and Connect

**Temporal integration** — durable, resumable execution. If a run crashes at any
depth of the agent tree, Temporal resumes from the last committed milestone. Workers
that completed are not re-run. The `escalate_to_human` path becomes a
`workflow.wait_for_signal()` — a run can pause for days while a human reviews,
without holding any resources.

**Full human-in-the-loop** — the UI surfaces every checkpoint with an input form.
Humans can approve waves before they fire, inject context mid-execution, provide
data agents could not find, and redirect work items that are going off-course.
The human response is committed to git as part of the audit trail.

**MCP tool integration** — Model Context Protocol servers expose standardised tools
(GitHub, Slack, Notion, Linear, databases, file systems) that the skills registry
can reference without writing custom integration code. A skill entry points to an
MCP server. The synthesizer can propose MCP-backed skills when resolving gaps.
This turns the skills registry into a gateway to the entire MCP ecosystem and makes
Slow AI applicable to any workflow domain that has MCP coverage.

**LLM-powered outcome analysis** — after a run, an analysis agent reads the full
git history and produces a plain-language narrative of what happened and why, an
explanation of underperforming agents, and a comparison against previous runs on
the same brief. The run record becomes something you can converse with, not just
inspect.

**MAPE-K observer** — a watchdog process that monitors the AgentRegistry in real
time. Detects runaway spawning, cost ceiling breaches, and confidence dropping
across subtrees. Signals the orchestrator to prune, pause, or escalate.

### V3 — Learn from Every Run

**Reinforcement learning on context graphs** — the context planner is a policy.
Its job is to produce a graph given a brief. The quality of the final output —
coverage, confidence, human ratings — is the reward signal. Over time the system
learns which planning patterns produce better outcomes for similar problem types.
Not RL on model weights. Preference learning on planning strategy, using the corpus
of `(brief, context_graph, outcome)` triples that accumulates across runs.

**Human feedback as reward signal** — post-run ratings, corrections to agent
conclusions, and approvals during execution become the labels that tell the system
what good looks like. The system gets ground truth, not proxy metrics. Human
expertise directly improves planning quality over time.

**Richer HITL contract** — approve waves before they fire, steer running agents
with injected context, rate findings per work item, correct conclusions, trigger
targeted follow-up investigations. Human interventions propagate into the RL reward
signal, closing the loop between human judgment and system improvement.

**Local model routing** — routing logic that selects between cloud and local models
based on task sensitivity, data residency requirements, and cost. The model registry
already supports local endpoints; V3 adds the intelligence to choose between them
automatically.

---

## Built on Open Standards

| Component | Technology |
|---|---|
| Agent definition | pydantic-ai |
| Data models | pydantic (fully typed, serialisable) |
| Provenance | Git (one repo per run, milestone commits) |
| Model providers | Any OpenAI-compatible API |
| Tool protocol | MCP (V2) |
| Live UI | Streamlit |
| Execution isolation | Python subprocess |

---

## Get Started

```bash
git clone https://github.com/yourhandle/slow-ai
cd slow-ai
uv sync
cp .env.example .env   # add your API keys
uv run streamlit run main.py
```

Add a model to the registry. Define a workflow. Run a brief. Watch the graph build.

---

## Philosophy

Speed is not free.

When an agent produces an answer in seconds with no explanation, no citations, and
no way to verify the reasoning — that speed has a hidden cost. It costs trust. It
costs reproducibility. It costs the ability to improve. And it costs the expert the
context they need to know whether to act on the output.

Slow AI is slow on purpose. The graph is visible before execution starts. The plan
is inspectable and correctable by the humans who know the domain. The gaps are
surfaced before resources are spent. The evidence is committed alongside the
reasoning that produced it, so every conclusion can be verified by the people whose
judgment it informs.

This is not an AI assistant. It is a system where human expertise and agent
capability reinforce each other — the agent brings scale and speed, the human
brings judgment and domain knowledge, and the platform provides the visibility and
provenance that lets both operate at their best.

*Every run is a data point. The registry grows with every gap resolved. Human
feedback shapes every future plan. This is what it means for institutional knowledge
to compound.*

---

## Tagline Options

1. **Orchestrate any work. With any model. With full provenance.**
2. **Multi-agent work orchestration. Built like a distributed system.**
3. **Define the work. Declare the skills. Trust the output.**
4. **The agent platform that shows its work.**
5. **Bring your models. Bring your tools. Build workflows that compound.**
