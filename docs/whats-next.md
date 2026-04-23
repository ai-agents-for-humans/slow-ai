---
layout: default
title: What's Next
nav_order: 6
---

# What's Next
{: .no_toc }

The roadmap — what is being built, and why each piece matters.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

{: .note }
> Slow AI is a working system with a point of view, not a finished product. Everything here is already designed — the sequencing reflects what unlocks what, not what is hardest or most interesting.

---

## React frontend

The Streamlit UI is a prototype rendering layer. It proved the concept. It is not the long-term answer.

**Why Streamlit is the wrong tool for this:** Streamlit reruns the entire script on every interaction. The live run view works around this with a 5-second polling cycle — which causes layout instability, loses scroll position, and makes the DAG and context graph interfere with each other. These are not bugs that can be fixed. They are the consequence of how Streamlit works.

**What the React migration delivers:**

- **SSE-driven live updates** — the DAG updates in real time without polling. Each node updates independently, not as part of a full page rerender.
- **URL-based routing** — a refresh rehydrates the view from the same run state files. No more lost sessions.
- **ReactFlow for the DAG and context graph** — proper graph components with zoom, pan, click-to-expand, and independent update cycles.
- **FastAPI backend** — a thin API layer between the execution plane and the UI. The execution plane already writes files; the API reads them and streams events. Any client can consume this — browser, CLI, another service.

The execution plane is already React-ready. It writes to files; any UI can read them. The frontend rewrite is purely additive — the runner does not change.

---

## MAPE-K observer

Monitor, Analyze, Plan, Execute with shared Knowledge.

The agent swarm has no circuit breaker beyond the maximum wave count. A run cannot currently self-terminate based on cost signals, confidence trends, or anomalous spawning patterns. The only thing that stops a runaway run is the hard limit on waves.

**Why this matters:** As run complexity grows — more phases, more parallel agents, longer chains — the probability of a run going wrong in a way that isn't immediately visible increases. An orchestrator that cannot observe its own behaviour cannot self-correct.

**What the MAPE-K observer does:**

- Watches `live/dag.json` in real time from a sidecar subprocess
- Tracks token spend across the run against a configurable budget ceiling
- Monitors confidence trends across phases — if confidence is consistently low, something is wrong with the brief or the graph, not the agents
- Detects anomalous spawning — a specialist that keeps spawning sub-workers without producing envelopes
- Signals the runner to pause, prune a subtree, or escalate to human when thresholds are breached

The observer is designed as a separate process with a single write channel to the runner — a signal file. This keeps the blast radius small. The runner makes the decision; the observer provides the signal.

---

## RL layer

The reinforcement learning layer is the reason every run is committed to git.

Every envelope, every HITL record, every approved context graph, every abandoned run — all of it is structured data that describes what the system tried, what humans approved, and what worked. This is the trajectory corpus. It exists now. The learning infrastructure does not yet.

**Why delayed reward is the right frame:** Research quality cannot be evaluated at the step level. An agent that searched three sources and found nothing useful is not a bad agent — it may have correctly ruled out an entire class of evidence. The reward signal comes from the human who reads the final report, approves the context graph, or corrects an agent's finding. That is a delayed, sparse signal — exactly the setting where GRPO (Group Relative Policy Optimisation) is the right algorithm.

**What gets learned:**

- **Context graph quality** — which decompositions of a problem type produce high-confidence, complete runs
- **Skill selection** — which skills produce useful evidence for which classes of work item
- **Orchestration decisions** — when to spawn sub-workers, when to escalate, when a phase has enough to proceed

**Three trajectory types the corpus already captures:**

1. **Original** — the run as it happened, with confidence scores
2. **Human-augmented** — runs where a human corrected an agent, refined the graph, or added context via HITL
3. **Abandoned** — runs the human stopped, which signal what the system got wrong

The sidecar policy model trains on this corpus without touching the main system. When it improves, the model slot in `registry.json` is updated. Every agent that uses that slot benefits immediately.

---

## Human-in-the-loop — full blocking gate

The HITL escalation path exists and is triggered correctly. When the orchestrator decides to escalate, it writes `human_checkpoint.json` and sets the run status to `waiting_for_human`. But it does not wait — it proceeds immediately with whatever evidence is available.

**Why this needs to block:** The value of a human checkpoint is that the human can redirect the investigation before the system commits further resources to the wrong direction. A checkpoint that doesn't pause is a log entry, not a gate.

**What full HITL looks like:**

- The UI surfaces the checkpoint with a response panel — what the orchestrator is uncertain about, what it needs to know
- The user provides guidance in plain language
- The runner resumes from exactly that point, with the human's input injected into the orchestrator's context

This is the loop that makes the system genuinely collaborative rather than just observable.

---

## True run resumption

"Dig deeper" currently generates a follow-on brief and starts a new run. The prior run's findings are available as context, but it is a new run — new run ID, new graph, fresh start.

**Why true resumption matters:** Some investigations require iteration at the phase level. You want to re-enter at the boundary where confidence was low, add a phase, and continue — not restart the whole thing.

**What this requires:**

- Phase boundary state serialised completely enough to re-enter
- The orchestrator accepting a resume signal alongside an existing run's envelopes
- The UI surfacing "continue from phase N" as an explicit option, not just "dig deeper"

This is the last piece that makes run chaining feel like a single compounding investigation rather than a sequence of related but separate runs.

---

## Multi-provider support at install time

The current install script asks for a Gemini API key and optionally a Perplexity key. That is the right model for getting started quickly, but the wrong model for a system that is supposed to be provider-agnostic.

**Why this matters at install time, not just in config:** Most users will not go digging in `registry.json` before running their first investigation. The choice of provider is a first-class decision — it affects cost, privacy, capability, and whether any data leaves the user's infrastructure at all. It belongs in the setup flow, not buried in a JSON file.

**What this looks like:**

The install script presents a menu — Google Gemini, Anthropic, OpenAI, OpenRouter, or Ollama (local, no key required). The user picks one, provides a key if needed, and `registry.json` is written accordingly. Every model slot defaults to the chosen provider. Advanced users can mix providers after the fact.

**OpenRouter** is particularly valuable here — a single key that routes to any model from any provider, with unified billing. For users who want flexibility without managing multiple API relationships, it is the right default.

**Ollama** is the right default for regulated environments — no key, no data leaving the machine, models running on local hardware.

---

## MCP — human communication layer

Model Context Protocol opens up a different kind of human-in-the-loop: one that does not require the user to be looking at the browser.

**The problem with browser-only HITL:** A checkpoint that requires the user to be in the Streamlit UI is a checkpoint that gets ignored. Research runs take 10–30 minutes. Users close tabs. They come back later. A gate that only works when you are watching is not really a gate.

**What MCP-based communication enables:**

When the orchestrator escalates, or when a phase completes with low confidence, or when an agent hits something genuinely uncertain — the system sends a message. To Slack. To email. To whatever channel the user has configured.

The user responds in that channel. The response is picked up by the MCP listener and injected back into the runner. The gate is real. The loop closes. The user never had to be in the browser.

This is also a demonstration of what MCP is actually for — not just connecting tools to models, but connecting models to the humans those tools serve. Slack and email are the first two targets because they are where knowledge workers already live.

---

## Per-agent data sources and success constraints

Every work item in the context graph has an implicit scope — what it is trying to find, what counts as enough. Today that scope is set entirely by the planner agent and the brief. The user cannot inject specific data sources for a work item, or tell a particular agent "for this one, success means finding a primary source, not a summary."

**Two intervention points:**

**Before launch — at graph review time.** When reviewing the context graph, the user should be able to click a work item and add context: a specific URL, a dataset, a document, or a tightened success criterion. The agent assigned to that work item receives this as part of its brief. The graph review is already a HITL step; this extends it from shape-approval to resource-annotation.

**At phase boundaries — before the next wave.** When a phase completes and the orchestrator synthesises, the user sees what was found. Before the next phase launches, they should be able to adjust the brief for specific upcoming work items — add a source that the prior phase surfaced, or raise the confidence threshold for a critical node.

**What this means for the agent design:** Each specialist's brief already accepts a `context` field. Populating that field from user-provided annotations is a UI and orchestration change, not an agent change. The work items in the context graph carry the annotations; the orchestrator passes them through when spawning.

**The ReactFlow connection:** This is one of the reasons the React migration matters. ReactFlow nodes can carry editable side panels — click a work item, a drawer opens, you add a source URL or change the success criterion, save, launch. That interaction pattern is not possible in Streamlit.

---

## MCP connector console

MCP connections — to Slack, email, data sources, APIs — need to be managed somewhere. Adding a new connection should not require editing config files or understanding the protocol.

**Two options are being evaluated:**

**Build a lightweight connector console** — a page in the React app where the user adds MCP server connections by URL or package name, authorises them, and assigns them to contexts (global, per-run, per-agent). Simple enough to set up in an afternoon, opinionated enough to work well for the Slow AI use case.

**Integrate an existing open-source MCP hub** — projects like [mcp-manager](https://github.com/zueai/mcp-manager) and others are emerging as the ecosystem matures. If one of these covers the configuration and lifecycle management well enough, the right call is to integrate rather than rebuild.

The decision depends on how the ecosystem looks when the React frontend lands. The principle is the same either way: MCP connections are a first-class concept in the UI, not a developer configuration task. A non-technical user should be able to add a Slack connection and have the system start sending phase summaries to their channel — without touching a config file.

---

## Scheduled runs — research on a cadence

Some investigations are not one-offs. A competitive monitoring brief, a campaign performance check, a weekly market signal sweep — these are briefs that have already been refined through a first run and human review. Running them again manually every week is friction that should not exist.

**The pattern this enables:** You run an investigation. You work with it — refine the graph, correct agents via HITL, shape the brief until the output is exactly what you need. That first run is the calibration. Every subsequent run on the same brief benefits from that calibration. The brief is proven. The graph is proven. The system just needs to run it again.

**What scheduled runs look like:**

After a run completes, the user can promote it to a schedule — daily, weekly, or on a custom cron expression. The schedule runs the same approved brief and graph, with prior run evidence available to each new run. Each scheduled run is a new entry in the run chain: it does not repeat covered ground, it checks for what has changed.

**Why this is particularly valuable for:**

- **Marketing campaigns** — weekly checks on campaign performance signals, competitor activity, share of voice changes. The brief is the same; the world has moved.
- **Web search monitoring** — tracking a technology, a regulatory development, a market. The graph is already decomposed correctly; you want the latest evidence, not a redesign of the investigation.
- **Recurring client deliverables** — the same research class run for the same client on a regular cadence, with each run building on the last.

**Implementation:** A cron layer that calls `_start_research()` with the saved brief and approved graph from the prior run. No new interview, no graph review unless the user opts in. The scheduler is a lightweight service — a cron job or a simple background process — that reads the schedule configuration and fires runs. The human stays in the loop via MCP notifications when each scheduled run completes.

---

## Run console — full observability, properly designed

The current post-run view works. It surfaces the right data. But the UX is clunky — tabs that are too flat, envelopes that require too many clicks, a log that is a raw list, a DAG that cannot be explored at the depth the data supports.

**The problem is not the data. The data is all there.** Every envelope, every tool call, every confidence score, every source, every artefact — it is all written to disk and loaded into the UI. The problem is the presentation layer. Streamlit makes it hard to build the kind of dense, navigable, multi-pane console that this data deserves.

**What a proper run console looks like:**

A three-pane layout. Left: the agent DAG as the primary navigation surface — click any node to drive the right panels. Centre: the evidence envelope for the selected agent — findings, confidence, sources, tool calls made, what was not found. Right: context — the work item this agent was assigned to, what phase it was in, what other agents covered the same work item.

Phase summaries as first-class views, not collapsed expanders. A timeline view of the run — which agents ran when, how long each took, where the bottlenecks were. The log filterable by agent, by phase, by severity. Artefacts — generated code, downloaded datasets, parsed documents — browsable inline, not referenced by path.

**The confidence map:** A visual overlay on the context graph showing, at a glance, which parts of the investigation are solid, which are thin, and which were not reached. Not the current static overlay — a live, interactive surface where you can click a low-confidence node and immediately see why.

This is the console that makes the system genuinely inspectable — not just technically transparent, but legible to a non-engineer who needs to understand what the agents did and why.

---

## Reporting issues and contributing

Found something not on this list? Open an issue.

[Open an issue](https://github.com/ai-agents-for-humans/slow-ai/issues){: .btn .btn-primary }
[View on GitHub](https://github.com/ai-agents-for-humans/slow-ai){: .btn }
