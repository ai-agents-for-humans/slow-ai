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

## UI and experience

### Graph visuals stack incorrectly during a live run

{: .label .label-yellow }
Streamlit limitation

The context graph and agent DAG can overlap or stack in an unexpected layout during a live run. The 5-second polling cycle that drives the live view causes re-renders that Streamlit cannot control at the layout level — there is no way to preserve scroll position or component placement across reruns.

**Impact:** Visual disruption during the live run view. The data is correct; the presentation is not.

**Fix:** This will be resolved when the Streamlit UI is replaced with the React frontend. React mounts and unmounts components independently — the DAG and context graph become separate components that never interfere with each other.

---

### Page refresh during a live run loses the session view

{: .label .label-yellow }
Streamlit limitation

If you refresh the browser while a run is in progress, the Streamlit session state is cleared. The run itself continues in the background (it's a separate subprocess), but the UI loses its connection to the live view and falls back to the project sidebar.

**Workaround:** Navigate to the run from the sidebar — select the project and click the active run to reconnect.

**Fix:** The React migration addresses this natively. URL-based routing and `localStorage` mean a refresh rehydrates the view from the same run state files the execution plane is writing.

---

### Retry and exception handling is not user-friendly

{: .label .label-red }
Needs work

When an agent or tool call fails, the error is logged to `runner.log` and the run continues with what it has. The UI does not surface errors in a clear, actionable way — you may see a red node in the DAG with no explanation visible without opening the log.

**Impact:** Users cannot easily tell whether a failure is recoverable, transient, or a configuration issue.

**Planned:** Clearer in-UI error surfaces, user-readable error messages at phase boundaries, and the ability to retry a failed agent without restarting the full run.

---

## Run continuity and chaining

### "Dig deeper" starts a new run rather than continuing

{: .label .label-red }
Known bug

The post-run "Dig deeper" option currently generates a new follow-on brief and launches a completely new run. It does not resume from the point where the previous run ended — it starts fresh with the prior run's findings available as context.

**Impact:** You lose the ability to pick up exactly where you left off. The new run will not duplicate covered ground, but it is a new run with a new run ID, not a continuation.

**Planned:** True run resumption — the ability to re-enter a run at a phase boundary, with the existing envelopes and state intact.

---

### "Do what we didn't finish" path is not fully tested

{: .label .label-yellow }
Undertested

The follow-on brief generation from identified gaps (`generate_follow_on_brief`) works in isolation, but the full path — generating the brief, reviewing the new context graph, and launching a chained run that correctly pulls prior evidence — has not been tested end-to-end across a wide range of run types.

**Known risk:** Prior evidence retrieval (`read_prior_evidence`) may not correctly scope to relevant envelopes in all cases, leading to over-retrieval or missed context from the prior run.

**Status:** Use with care. Verify the follow-on brief and context graph carefully before launching.

---

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

## Code execution observability

### Generated Python code is not visible in the UI

{: .label .label-red }
Needs work

When a specialist agent generates and executes Python code, the artefact files saved to `runs/{run_id}/artefacts/` contain JSON objects describing the output — not the Python source code that actually ran. There is currently no way to inspect the generated code from inside the UI.

**Impact:** Users cannot verify what the agent wrote and executed. For any investigation where code was used to process data, cross-reference datasets, or call APIs, the computation is a black box. This undermines the system's transparency principle directly.

**What is needed:** The Python source generated by each code execution should be saved alongside its output and surfaced in the agent envelope view — the code that ran, the output it produced, and whether execution succeeded or failed.

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

### Full React frontend

The Streamlit UI is the current rendering layer. The [React migration spec]({{ site.baseurl }}/react_migration) is written — FastAPI backend, SSE-driven live updates, ReactFlow for the DAG and context graph, full browser control. The execution plane is already React-ready (it writes files; any UI can read them). The frontend rewrite is the next major milestone.

---

## Reporting issues

Found something not listed here? Open an issue on GitHub — a clear description of what you expected and what happened is enough to get started.

[Open an issue](https://github.com/ai-agents-for-humans/slow-ai/issues){: .btn .btn-primary }
