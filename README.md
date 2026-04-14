```
 ██████  ██       ██████  ██     ██      █████  ██
██        ██      ██    ██ ██     ██    ██   ██  ██
 █████    ██      ██    ██ ██  █  ██    ███████  ██
     ██   ██      ██    ██ ██ ███ ██    ██   ██  ██
 ██████   ███████  ██████   ███ ███     ██   ██  ██
```

> **Agentic work orchestration. Built like a distributed system.**

![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)
![pydantic-ai](https://img.shields.io/badge/built%20with-pydantic--ai-7c3aed?style=flat-square)
![git](https://img.shields.io/badge/built%20with-git-7c3aed?style=flat-square)
![BYOM](https://img.shields.io/badge/BYOM-any%20model%20provider-f97316?style=flat-square)
![status](https://img.shields.io/badge/status-active-0ea5e9?style=flat-square)

---

## The Problem

AI agents produce answers. They do not produce evidence.

When you use a research assistant, a coding agent, or a workflow automation tool today, you get an output — but you cannot see the plan that produced it, verify the reasoning behind it, or know what it chose to ignore. When it goes wrong, you cannot tell why. When you run it again, it starts from zero.

If you have tried to solve this with workflow tools like n8n, Make, or Zapier, you have hit a different wall. Someone still has to design the workflow — every node, every branch, every edge case — by hand. When the input changes even slightly, you are back to reconfiguring. A different company, a different jurisdiction, a different question: the workflow does not adapt. You rebuild. The workflow is a static artefact. The work it represents is dynamic.

For any work where the quality of the output determines the quality of everything built on top of it — due diligence, compliance, engineering decisions, strategic research — neither approach is enough.

---

## Why This Approach Works

**Plan before you act.** Before a single agent fires, Slow AI decomposes the goal into a visible, inspectable graph of work items. Each node declares what skills it needs. Human experts can review the plan, challenge it, and approve it. The graph is the contract — it captures what needs to happen independently of how it will be executed.

**Skills accumulate. The system improves.** Every run that hits a missing skill either synthesises a new one into a shared registry — making it available to every future run — or surfaces a concrete gap with actionable steps to close it. The 50th run is fundamentally more capable than the first. No retraining. No reconfiguration. The registry grows.

**No cold start. No brittle templates.** The context graph is not configured — it is generated from the brief by an agent. Describe the work in plain language. The system designs the workflow, declares the skills each step needs, and validates it can execute before a single agent fires. Run it again identically, or change the brief and let the system adapt. What takes hours to wire up in a workflow tool takes a sentence here.

**Humans stay in the loop by design, not by exception.** At any point in a run, an expert can inspect every evidence envelope, correct agent conclusions before they propagate, approve the next wave, or redirect the work entirely. The system earns trust by showing its work. Every claim has a source. Every source has a commit.

---

## Memory Architecture

Most AI systems treat memory as "bigger is better" — put everything into one large
context window and let the model sort it out. This produces unverifiable outputs,
scales poorly, and gives you no way to inspect or correct what the model actually
attended to.

Slow AI treats memory the way distributed systems treat state: **scoped, bounded,
explicit, and persisted outside the computation.**

```
  ┌──────────────────────────────────────────────────────────────┐
  │  BRIEF  (intent memory)                                      │
  │  Committed at run start. Never changes. Every agent is       │
  │  measured against it. The contract that survives the run.    │
  └──────────────────────────────────────────────────────────────┘
                              │
              flows into orchestrator and each wave
                              │
  ┌──────────────────────────────────────────────────────────────┐
  │  WAVE CONTEXT  (working memory per dependency)               │
  │  Each agent receives upstream evidence from the nodes it     │
  │  directly depends on — not a broadcast of everything.        │
  │  Information flows through DAG edges, not dumped into        │
  │  every agent's context.                                      │
  └──────────────────────────────────────────────────────────────┘
                              │
              scoped to each specialist
                              │
  ┌──────────────────────────────────────────────────────────────┐
  │  AGENT WORKING MEMORY  (8K token budget per agent)           │
  │  Each specialist accumulates findings within a hard token    │
  │  ceiling. When the budget runs low, the agent returns        │
  │  partial results and surfaces remaining work — the runner    │
  │  spawns continuations. No hallucinated completeness.         │
  │  The constraint is the feature: it forces decomposition.     │
  └──────────────────────────────────────────────────────────────┘
                              │
              committed at every milestone
                              │
  ┌──────────────────────────────────────────────────────────────┐
  │  GIT  (persistent memory)                                    │
  │  Every evidence envelope, agent memory dump, artefact, and   │
  │  generated file committed to a versioned branch. The run     │
  │  is permanent. Past runs are auditable and referenceable.    │
  │  Long-term memory lives outside the model — in version       │
  │  control — where it can be inspected, branched, and diffed.  │
  └──────────────────────────────────────────────────────────────┘
                              │
              accumulates across runs
                              │
  ┌──────────────────────────────────────────────────────────────┐
  │  SKILLS REGISTRY  (institutional memory)                     │
  │  What the system has learned about resolving skill gaps      │
  │  persists permanently. The registry is the memory that       │
  │  compounds — every gap closed makes every future run         │
  │  smarter, without retraining anything.                       │
  └──────────────────────────────────────────────────────────────┘
```

The 8K token budget per agent is configurable — but the default is intentionally
tight. An agent that cannot complete its work within budget does not fabricate a
conclusion. It reports what it found and flags what remains. The system continues.
This is the behaviour you want in any serious agentic pipeline.

---

## Who It's For

| Domain | What you run | Why it matters |
|---|---|---|
| **Financial services** | Competitive intelligence, market structure, regulatory scanning | Models run on-prem — no thesis leaves the perimeter |
| **Life sciences** | Literature synthesis, trial landscape, target identification | Every synthesis step is auditable before it informs a decision |
| **Legal & compliance** | Policy monitoring, jurisdiction comparison, gap analysis | Nothing finalised without expert review — full citation trail |
| **Management consulting** | Due diligence, market sizing, operational benchmarking | Partners review the graph before a single token is spent |
| **Engineering teams** | Technical assessment, library evaluation, architecture research | Code agents generate and commit working prototypes |
| **Operations** | Incident triage, root cause investigation, postmortem drafting | DAG enforces order — human gates block automated actions on ambiguous signals |
| **Sales & GTM** | Account research, signal enrichment, outreach drafting | Specialist agents run in parallel across a prospect list |
| **Content & research** | Deep investigation, synthesis, structured reporting | Any domain, any brief — the framework does not change |

---

## How It Works

```
  ┌─────────────────────────────────────────────────────────────┐
  │  1. BRIEF                                                   │
  │     Interview agent captures the goal precisely.            │
  │     Vague input → pushed back on. Specific → committed.     │
  └───────────────────────────┬─────────────────────────────────┘
                              │
  ┌───────────────────────────▼─────────────────────────────────┐
  │  2. GRAPH                                                   │
  │     Planning agent decomposes the brief into a DAG.         │
  │     Each node: what to do · what skills it needs · who      │
  │     depends on it. Visible before execution starts.         │
  └───────────────────────────┬─────────────────────────────────┘
                              │
  ┌───────────────────────────▼─────────────────────────────────┐
  │  3. VIABILITY GATE                                          │
  │     Skills checked against the registry before any agent    │
  │     fires. Gaps → synthesiser maps them to existing tools   │
  │     and writes new skills to the registry permanently.      │
  │     Zero coverage → stop. Partial → degraded mode.          │
  └───────────────────────────┬─────────────────────────────────┘
                              │
  ┌───────────────────────────▼─────────────────────────────────┐
  │  4. WAVE EXECUTION                                          │
  │     Specialists run in dependency order, wave by wave.      │
  │     Each agent: minimum permissions · scoped memory budget  │
  │     · only the tools its work item requires.                │
  │     Human experts can inspect and correct between waves.    │
  └───────────────────────────┬─────────────────────────────────┘
                              │
  ┌───────────────────────────▼─────────────────────────────────┐
  │  5. SYNTHESIS + COMMIT                                      │
  │     All evidence assembled into a final output.             │
  │     Every claim → specific agent → tool call → timestamp.   │
  │     Every artefact committed to git alongside the run.      │
  └─────────────────────────────────────────────────────────────┘
```

**Two independent planes. No shared state.**

```
  ┌─────────────────────────────────┐
  │  UI  (Streamlit)                │  ← polls JSON files every 5s
  │  interview · live graph · runs  │
  └──────────────┬──────────────────┘
                 │  files on disk only
  ┌──────────────▼──────────────────┐
  │  Execution engine  (subprocess) │  ← writes JSON, commits to git
  │  plan → gate → waves → report   │
  │                                 │
  │  skills registry · model reg.   │
  └──────────────┬──────────────────┘
                 │
               git  (one branch per run · milestone commits)
```

Any future UI — React, CLI, API — replaces Streamlit without touching the engine.

---

## The Accumulation Flywheel

This is what makes Slow AI different from a tool you configure once and forget.

```
       ┌──────────────────────────────────────────────┐
       │                                              │
  run encounters ──► synthesiser maps ──► new skill   │
  a skill gap         gap → tools       written to    │
                                        registry      │
       │                                    │         │
       │          every future run          │         │
       └────────── finds the skill ◄────────┘         │
                   already there                      │
       │                                              │
       └──── registry grows · degraded runs fall ─────┘
```

When no mapping is possible, the system surfaces the gap with concrete steps to close it — search queries, open source repositories to evaluate, tool patterns to implement. The gap record accumulates across runs and becomes a capability backlog.

**The result:** every run makes the next run smarter. Skills compound. This is institutional knowledge that persists.

---

## Bring Your Own Models

Route each task to the right model. Swap providers without touching agent code.

```json
{ "name": "reasoning", "model_id": "google-gla:gemini-2.5-pro",  "use_for": ["context_planning", "orchestration"] }
{ "name": "code",      "model_id": "ollama:qwen2.5-coder:7b",     "use_for": ["code_generation"] }
{ "name": "fast",      "model_id": "openai:gpt-4o-mini",          "use_for": ["skill_synthesis", "report_synthesis"] }
```

Supported: **Google · OpenAI · Anthropic · any OpenAI-compatible endpoint** (Ollama, vLLM, LM Studio, private inference).

For regulated industries — sensitive data never leaves your infrastructure. Every model runs locally. The platform is entirely yours.

---

## Quick Start

```bash
git clone https://github.com/your-handle/slow-ai
cd slow-ai
bash install.sh       # installs uv, deps, and prompts for API keys
uv run streamlit run main.py
```

The install script handles uv, dependencies, and walks you through API key setup interactively.

---

## Roadmap

### V2 — Observe, Benchmark, and Connect

**Brief-adaptive context graphs** — modify the brief and re-run against an existing
context graph. The system identifies which nodes are still valid, which need updating,
and which are new — then replans only the delta. Particularly valuable for recurring
workflows where the input varies slightly: a different target company, a different
time period, a different jurisdiction. The structure of the work stays the same; the
graph adapts to the new input automatically. No reconfiguration. No rebuild from zero.

**Benchmark against deep research tools** — a structured evaluation of Slow AI against
Perplexity Deep Research, OpenAI Deep Research, and Gemini Deep Research on identical
briefs. Measured across: coverage, provenance (can every claim be verified?), human
steerability mid-run, domain customisation, and data residency. The benchmark makes
the abstract concrete — where the approaches differ, and why those differences matter
for serious work.

**MCP tool integration** — Model Context Protocol servers expose standardised tools
(GitHub, Slack, Notion, Linear, databases, file systems) that the skills registry can
route to without custom integration code. A skill entry points to an MCP server. The
synthesiser can propose MCP-backed skills when resolving gaps. This turns the skills
registry into a gateway to the entire MCP ecosystem.

**Full human-in-the-loop** — the run pauses at explicit gates, the UI surfaces the
checkpoint, the human responds, the run resumes from the exact point it paused.
Humans can approve waves before they fire, inject context mid-execution, and provide
data agents could not find. Every human response is committed to git.

**Temporal integration** — durable, resumable execution. Runs survive restarts at any
depth. The `escalate_to_human` path becomes a `wait_for_signal` — a run can pause for
days while a human reviews, without holding resources.

**MAPE-K observer** — monitors the agent tree in real time. Detects runaway spawning,
cost ceiling breaches, confidence drops. Signals the orchestrator to prune, pause,
or escalate.

**LLM-powered outcome analysis** — after a run, reads the full git history and
produces a plain-language narrative: what happened, why agents underperformed,
how this run compares to prior runs on the same brief.

### V3 — Learn from Every Run

**Reinforcement learning on context graphs** — the context planner is a policy. The
quality of the final output — coverage, confidence, human ratings — is the reward
signal. Over time, the system learns which planning patterns produce better outcomes
for similar problem types. Not RL on model weights. Preference learning on planning
strategy, using the corpus of `(brief, context_graph, outcome)` triples that
accumulates across runs.

**Human feedback as reward signal** — post-run ratings, mid-run corrections, and
wave approvals become training labels. Human expertise directly improves planning
quality over time. The system gets ground truth, not proxy metrics.

**Richer HITL contract** — rate findings per work item, correct conclusions, fork the
graph, trigger targeted re-investigation. Human interventions propagate into the RL
reward signal, closing the loop between judgment and system improvement.

---

## Technical Documentation

Architecture, agent specifications, data models, the execution layer, and
configuration reference are in [`docs/technical.md`](docs/technical.md).

---

*Trust no node. Trust is built. Trust is designed.*
