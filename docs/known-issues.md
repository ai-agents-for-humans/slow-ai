---
layout: default
title: Known Issues
nav_order: 5
---

# Known Issues
{: .no_toc }

This is a working system with a point of view — not a finished product. This page documents known limitations, untested paths, and behaviour that will improve as the system matures. Transparency is a design principle here, not just a feature.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

### Retry and exception handling is not user-friendly

{: .label .label-red }
Needs work

When an agent or tool call fails, the error is logged to `runner.log` and the run continues with what it has. The UI does not surface errors in a clear, actionable way — you may see a red node in the DAG with no explanation visible without opening the log.

**Impact:** Users cannot easily tell whether a failure is recoverable, transient, or a configuration issue.

**Planned:** Clearer in-UI error surfaces, user-readable error messages at phase boundaries, and the ability to retry a failed agent without restarting the full run.

---

## Run continuity and chaining
{: .label .label-red }
Needs work

How to actually implement and continue the run once we have a v1 of it done is something that needs to looked into. Does that mean expansion of context graph reusing the existing one, and then running agent swarms for the new elements only , so that we can reuse a lot of artefacts generated, or is that polluting an insight that we couldve identified without reusing but just starting with a better context, I dont know. This needs investigation.

**Impact**: You cannot run chain properly now after a post run.

**Planned** : A better way to support run chaining for a user, by understanding intent.


## Execution and reliability

### Human-in-the-loop escalation does not block

{: .label .label-yellow }
Partially implemented

When the orchestrator decides to `escalate_to_human`, it writes `human_checkpoint.json` and sets the run status to `waiting_for_human` — but then immediately synthesises with whatever evidence is available rather than pausing for a response.

**Impact:** The HITL escalation path exists in the data model and is triggered correctly, but does not produce an actual gate. The system does not wait for human input before proceeding.

**Planned:** Full blocking pause — the UI surfaces the checkpoint with a response panel, the user inputs their guidance, and the runner resumes from that exact point.

---

### No circuit breaker beyond wave count

{: .label .label-yellow }
Not yet built

The MAPE-K observer — which monitors for runaway agent spawning, token budget overruns, cost ceiling breaches, and confidence dropping across subtrees — is designed but not implemented.

**Impact:** The only protection against a runaway run is the maximum wave count (5 waves). A run cannot self-terminate based on cost or confidence signals alone.

**Planned:** An observer subprocess that monitors `live/dag.json` in real time and can signal the runner to pause, prune, or escalate when thresholds are breached.

---

### SpawnRequest mechanism is inconsistent

{: .label .label-yellow }
Partially implemented

The mechanism for a specialist to spawn sub-workers mid-execution (`SpawnRequest`) exists and produces correct DAG lineage when used, but specialist agents do not consistently invoke it. Some complex work items that warrant sub-workers complete as a single agent instead.

**Impact:** Some research tasks that benefit from parallel sub-investigation are handled sequentially within a single specialist context window, reducing coverage depth.

---

### Context graph coverage overlay is static during live run

{: .label .label-yellow }
Known limitation

The context graph coverage overlay (which nodes are covered, partial, or uncovered) is computed once when the graph first renders during a live run and is not updated during the polling cycle. This is intentional — rebuilding the graph layout on every 5-second poll causes visual instability.

**Impact:** Coverage shown during a live run reflects the state at first render, not the current state. Coverage in the completed run view is always correct.

**Fix:** The React migration resolves this — the coverage overlay updates independently without triggering a full layout re-render.

---


### Bandit security scan results are not surfaced

{: .label .label-yellow }
Not surfaced to user

Before any agent-generated Python code executes, `bandit` runs a static security scan. The scan results — severity levels, specific findings, what was flagged — are used internally to decide whether to block or warn, but are not shown to the user anywhere in the UI.

**Impact:** Users have no visibility into what security checks ran on code that executed in their environment, or what was flagged at MEDIUM or LOW severity (which does not block execution but may still be relevant).

**What is needed:** Bandit scan results surfaced in the agent envelope — findings by severity, the specific code patterns flagged, and the decision taken (blocked / warned / clean). This gives users the same transparency over code execution that they have over web search and evidence synthesis.

---

## Not yet built

### RL layer

Designed in full — trajectory corpus, sidecar policy model, GRPO formulation, the Bellman equation framing — but not implemented. The data it needs (envelopes, HITL records, approved graphs, outcomes) is being collected correctly by the git layer. The learning infrastructure does not yet exist.

---

### MAPE-K observer

Monitor, Analyze, Plan, Execute with shared Knowledge. The observer that watches agent behaviour in real time and signals the orchestrator when something is wrong. Described in the architecture; not built.

---

## Reporting issues

Found something not listed here? Open an issue on GitHub — a clear description of what you expected and what happened is enough to get started.

[Open an issue](https://github.com/ai-agents-for-humans/slow-ai/issues){: .btn .btn-primary }
