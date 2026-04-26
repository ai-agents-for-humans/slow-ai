---
layout: default
title: Getting Started
nav_order: 4
---

# Getting Started
{: .no_toc }

From zero to your first completed research run. No prior experience with agents required.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Before you begin

**What you need:**

| Requirement | Details |
|---|---|
| **Python 3.11+** | Check with `python3 --version` |
| **Git** | For cloning and the run audit trail |
| **Gemini API key** | Free tier works for exploration — [get one here](https://aistudio.google.com/app/apikey) |
| **Perplexity API key** | Powers live web search — [get one here](https://www.perplexity.ai/settings/api) |

{: .note }
> Perplexity is optional if your research doesn't require live web search. The system will still run — specialists will use web browsing and code execution instead.

**What you do not need:**
- Docker
- A database
- An account with any platform
- Anything beyond the two API keys above

---

## Installation

```bash
git clone https://github.com/ai-agents-for-humans/slow-ai
cd slow-ai
bash install.sh
```

The install script does four things in sequence:

1. **Checks your environment** — confirms Python 3.11+ is available
2. **Installs `uv`** — the fast Python package manager that powers sandboxed execution
3. **Installs dependencies** — `uv sync` pulls everything from `pyproject.toml`
4. **Configures your API keys** — prompts for Gemini and Perplexity keys, writes them to `.env` and your shell profile

Your keys are stored locally and never leave your machine.

When it finishes you will see:

```
  ╔══════════════════════════════════════════════════════════╗
  ║                     you're ready                        ║
  ╚══════════════════════════════════════════════════════════╝

  Load keys in this terminal
    source ~/.zshrc   (or ~/.bashrc depending on your shell)

  Run the app
    PYTHONPATH=. uv run uvicorn app.main:app --reload
```

---

## Start the app

```bash
PYTHONPATH=. uv run uvicorn app.main:app --reload
```

This starts the web interface at `http://localhost:8000`. Keep the terminal running while you work — the app uses server-sent events to stream live updates to your browser.

---

## Your first research run

### Step 1 — Start the interview

Click **New** in the sidebar. The interview begins immediately.

The interviewer agent asks you questions one at a time to understand your research goal. Answer naturally — as if you were briefing a colleague who needs to understand exactly what you need and why.

**What the interview is doing:**
- Identifying the domain and goal
- Clarifying scope (geography, timeframe, perspective)
- Surfacing assumptions you may not have articulated
- Producing a structured brief precise enough to plan against

**What good interview answers look like:**
- Be specific about *why* you need this — the purpose shapes what evidence matters
- Don't worry about framing it perfectly — the agent will push back if something is vague
- Answer one question at a time; don't pre-answer questions that haven't been asked

![The interview — one question at a time, pushing toward precision](assets/images/interview.png)

When the agent has enough, it presents a structured **Problem Brief** directly in the conversation — goal, domain, constraints, unknowns, and success criteria laid out clearly.

![The Problem Brief appears inline — review it before confirming](assets/images/problem-brief.png)

Read it carefully. If something is missing or wrong, type your correction and the agent will revise. When you're satisfied, click **Confirm Brief →**.

![Confirm the brief or ask for a refinement](assets/images/confirm-brief.png)

{: .highlight }
> **The brief is the cornerstone.** Everything that follows — the context graph, the agent assignments, the synthesis — is built on top of it. A five-minute interview is the highest-leverage thing the system does.

---

### Step 2 — Review the workflow plan

After confirming your brief, the planner generates a **workflow plan**: a structured breakdown of the research question into phases and parallel work items, rendered as an interactive graph.

You will see:
- A visual graph — phases as dark nodes, work items as white nodes connected by dependency edges
- A narrative summary on the right explaining the logic of the breakdown
- A chat panel for refinement

**Read the narrative first.** It explains why the graph is structured the way it is. If the narrative doesn't match your mental model of the work, that is the signal to refine.

![The workflow plan — phases and work items, the shape of the problem made visible](assets/images/context_graph.png)

**Refining the plan through conversation:**

You don't edit the graph directly — you tell the system what you want changed in plain language. Type in the "Suggest a change…" panel and the graph regenerates with a new narrative.

```
  "The regulatory phase should come before the market sizing —
   reimbursement rules will constrain what's commercially viable."

  "Add a phase on competitive dynamics — I need to understand
   who the incumbents are before we assess entry strategy."

  "Remove the pricing phase entirely — the client already has this data."
```

Repeat until the shape of the work matches how an expert in your domain would approach it.

{: .note }
> **You are the expert.** The system proposes, you decide. The graph is not locked until you launch — take the time to get the direction right. A well-shaped graph produces dramatically better results than a vague one.

When you're satisfied: click **Launch Agent Swarm →** at the bottom.

{: .important }
> **The direction matters more than the detail.** You are approving the shape of the investigation, not the implementation. Your job is to confirm the phases make sense and nothing critical is missing.

---

### Step 3 — Watch the swarm

After launch, the approved plan drives a swarm of specialist agents running in parallel. The **Run tab** shows the agent DAG filling in as agents complete their work.

**What you're seeing:**

| Node colour | Meaning |
|---|---|
| Grey | Waiting — dependency not yet satisfied |
| Blue | Running — agent is actively working |
| Green | Complete — evidence envelope produced |
| Red | Failed or partial — agent flagged a gap |

![The agent swarm in progress — nodes updating in real time, log streaming on the right](assets/images/live_run.png)

The **Log** panel on the right streams every agent action as it happens — phase launches, specialist completions, synthesis steps, confidence scores. The **Phases** tab shows a card for each completed phase with its synthesis and confidence. The **Plan** tab shows the original context graph for reference.

**Click any completed node** to open the evidence envelope — what the agent found, its confidence score, the sources it cited, and what it couldn't determine.

![Clicking a node opens the evidence envelope at the bottom of the DAG](assets/images/agent_envelope.png)

You do not need to watch it run. You can close the browser and come back later. The run continues in the background and the state is always written to disk.

---

### Step 4 — Read the results

When the run completes, the **Results tab** opens automatically. Everything is in one place.

**The Final Research Report** — at the very top of the Results tab, the system synthesises all agent findings into a single long-form document. This is not a summary card. It is a full research report: executive summary, thematic findings (organised by insight, not by phase), open questions, limitations, recommendations, and an inline source list. Every claim is cited back to the agent that produced it.

![The Results tab — final report at the top, phase tree below](assets/images/post_run_results.png)

**Export the report** — click **↓ Export HTML** next to the report to download a self-contained, standalone HTML file. It has no external dependencies, renders correctly without the app running, and is print-ready. Share it, archive it, or open it offline.

**Below the report:** the full phase tree. Expanding a phase shows the synthesis for that phase, then each agent card. Expand an agent card to see its full findings and confidence score.

![Phase 1 expanded — synthesis and individual agent findings](assets/images/post_run_phases_agent_view.png)

**Tool Calls** — each agent card has a collapsible Tool Calls section. Expand it to see every search query, web browse, or code execution the agent made, with the source shown as a colour-coded badge. Click any row to expand the snippet it returned.

![Tool calls expanded — each call shown as a row with source badge and query](assets/images/post_run_tool_calls_artefacts.png)

**Artefacts** — agents that ran code or produced documents show an Artefacts section. Click any chip to open the file in a full-screen viewer with syntax highlighting and a copy button.

![An artefact open in the viewer — generated Python code with syntax highlighting](assets/images/post_run_artefacts_viewer.png)

**Ask about the run — and update the report** — the chat bar at the bottom of the Results page is always available. You can ask follow-up questions grounded in the run's evidence, drill into specific findings, or instruct the agent to rewrite or expand a section of the report. When you ask for a report change, the agent edits the document in place — the updated version is reflected immediately and the updated export is available on next download.

![The bottom chat drawer — ask questions or update the report](assets/images/post_run_chat.png)

The **Run Summary** panel on the right shows confidence per phase, total tokens, and the Continue Investigation button.

---

### Step 5 — Continue the investigation

The run doesn't have to end here. Click **Continue Investigation** in the stats panel on the right.

The system generates a follow-on brief from the current run's identified gaps — questions that surfaced but weren't answered. You review the new context graph (it will not duplicate work already done), confirm the direction, and launch.

The next run's specialists pull specific evidence from prior runs when their work item needs it. The understanding compounds.

```
  Run 1  →  Market landscape. Gaps: regulatory detail, pricing pressure.
  Run 2  →  Regulatory + pricing. Builds on Run 1. Gaps: competitive moat.
  Run 3  →  Competitive synthesis. Uses Runs 1 + 2. Strategic recommendation.
```

Each run starts smarter than the last. This is the loop that turns a one-off investigation into a compounding body of knowledge.

---

## Bring your own models

Out of the box, Slow AI uses Gemini models. To swap any model slot, edit `src/slow_ai/llm/registry.json`:

```json
{
  "models": [
    {
      "name": "reasoning",
      "model_id": "google-gla:gemini-3.1-pro",
      "use_for": ["context_planning", "orchestration", "assessment"]
    },
    {
      "name": "fast",
      "model_id": "google-gla:gemini-3.1-flash",
      "use_for": ["skill_synthesis", "report_synthesis", "interview"]
    },
    {
      "name": "code",
      "model_id": "google-gla:gemini-3.1-pro",
      "use_for": ["code_generation"]
    },
    {
      "name": "specialist",
      "model_id": "google-gla:gemini-3.1-pro",
      "use_for": ["specialist_research"]
    }
  ]
}
```

Change `model_id` to any supported provider. No code changes needed.

**Supported providers:**

| Provider | Example model_id |
|---|---|
| Google | `google-gla:gemini-3.1-pro` |
| OpenAI | `openai:gpt-4o` |
| Anthropic | `anthropic:claude-opus-4-6` |
| Ollama (local) | `ollama:qwen2.5-coder:7b` |
| vLLM / LM Studio | `openai:model-name` with custom base URL |

{: .highlight }
> **For regulated environments:** point every slot at a local Ollama instance. No data leaves your infrastructure. The agents do not know or care which provider they use.

---

## Understanding what's stored

Every run creates a directory under `runs/`:

```
runs/
  {run_id}/
    input_brief.json      ← the brief that started the run
    input_graph.json      ← the approved context graph
    envelopes/            ← one JSON file per specialist agent
    artefacts/            ← generated code, datasets, parsed documents
    live/                 ← real-time state files read by the UI
    conversation.jsonl    ← full history: interview, review, post-run chat
    runner.log            ← structured run log
```

Projects are stored under `output/`:

```
output/
  {project_id}/
    problem_brief.json
    runs.jsonl            ← index of all runs for this project
```

Everything is plain files. Nothing requires a running service to read. Open any envelope JSON to see exactly what an agent produced.

---

## Common questions

**The run is taking a long time — is it stuck?**

Check `runs/{run_id}/runner.log` for the most recent log entry. If agents are still writing to their envelopes, the run is active. Some research questions — especially those requiring document parsing or dataset analysis — take 10–20 minutes per phase.

**An agent failed — what now?**

Red nodes in the DAG indicate a failed or partial agent. Click the node to see the evidence envelope — it will include an error description and what the agent attempted. The run continues with whatever work items were not blocked by that failure.

**I want to add a new tool or API integration.**

Tools are added to `src/slow_ai/tools/`. A tool is a Python function decorated with the pydantic-ai tool pattern. Once added, create a corresponding entry in `src/slow_ai/skills/catalog/{skill_name}/SKILL.md` with YAML frontmatter (name, description, tools, tags) and a full playbook body (when to use, how to execute, output contract, quality bar). The skill catalog is what the context planner draws from when assigning skills to work items.

**Can I run it without the web UI?**

Yes. The execution plane runs independently:

```bash
uv run python -m slow_ai.research --brief path/to/brief.json --graph path/to/graph.json
```

The UI reads the files the runner writes. Any other reader — a script, a different UI, a CLI — works the same way.

---

## What to investigate first

If you're not sure where to start, here are briefs that work well as first runs:

- A market or competitive question in your professional domain
- A technology evaluation — comparing frameworks, libraries, or approaches
- A regulatory or policy question in a domain you know
- A medical or scientific question you've been meaning to research properly

The interview will help you get the brief right regardless of where you start. The more specific your problem, the sharper the context graph — and the more useful the output.

[Read how it works in depth](how-it-works){: .btn }
[Explore the architecture](architecture){: .btn }
