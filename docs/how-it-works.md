---
layout: default
title: How It Works
nav_order: 2
---

# How It Works
{: .no_toc }

Five acts. One continuous thread of understanding.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

{: .highlight }
> Every other AI tool starts with the answer. Slow AI starts with the question — and doesn't stop until the question is properly understood.

---

## Act I — The Interview

### Your problem, made precise.

Before any agent runs, Slow AI interviews you.

Not a form. Not a search box. A conversation — one question at a time, with an agent that pushes back on vagueness, surfaces assumptions you didn't know you were making, and refuses to proceed until the problem is specific enough to plan against.

Most research fails before the first search is run. The question is wrong. The scope is wrong. The person asking didn't know what they didn't know. The interview is the place where that gets fixed.

By the time you confirm your brief, you understand your own problem more clearly than when you started. That is not a side effect. It is the point.

```
  You: "I want to understand the market for personalised medicine."

  Agent: "When you say 'market' — are you investigating investment
          opportunity, regulatory landscape, competitive dynamics,
          or something else? And what geography?"

  You: "Investment. Europe, specifically Germany and UK."

  Agent: "Are you evaluating from the position of a potential
          investor, a company considering entry, or an advisor
          assessing the space? That changes what evidence matters."

  You: "An advisor. Client is a US biotech considering European expansion."

  Agent: "Got it. Last question: what's the timeframe — is this a
          decision they're making now, or planning for 2–3 years out?"
```

Every exchange sharpens the brief. By the end, the agent produces a structured `ProblemBrief` — a typed, committed artifact that becomes the contract for everything that follows.

{: .important }
> **Why this matters:** The brief is the cornerstone. If the brief is wrong, the context graph is wrong. If the graph is wrong, the agents run in the wrong direction. A five-minute interview is the highest-leverage thing the system does.

---

## Act II — The Context Graph

### The shape of your problem, made visible.

Your brief becomes a **context graph** — a structured decomposition of the research question into phases and parallel investigations.

This is how expert thinking actually works: breaking a hard problem into its component parts, understanding which depend on which, identifying what needs to be established before the next question can be asked.

```
  Brief: US biotech advisor · personalised medicine · Germany + UK · 2-3yr horizon
       │
       ▼
  ┌─────────────────────────────────────────────────────────┐
  │                    CONTEXT GRAPH                        │
  │                                                         │
  │  Phase 1: Market landscape           (parallel)         │
  │    ├── regulatory environment (DE + UK post-Brexit)     │
  │    ├── reimbursement structures (GKV, NICE pathways)    │
  │    └── market size and growth trajectory                │
  │                                                         │
  │  Phase 2: Competitive dynamics       (needs Phase 1)    │
  │    ├── incumbent players and positioning                │
  │    └── recent M&A and partnership activity              │
  │                                                         │
  │  Phase 3: Entry strategy synthesis   (needs Phase 2)    │
  │    └── go/no-go and recommended entry vectors           │
  │                                                         │
  └─────────────────────────────────────────────────────────┘
```

The graph tells you:
- **What** will be investigated, in plain language
- **When** — which phases depend on which
- **Why** — a narrative summary explaining the logic of the breakdown

You review this before anything runs. You can change it. Add phases. Merge work items. Tell the system what's missing or what you'd rather skip. The graph is yours.

The question being asked — implicitly, at every graph review — is:

> *"Do you see this problem the same way I do?"*

When you approve the graph, you are not approving implementation details. You are confirming the direction. When the direction is wrong, there is no point running hundreds of agents against it. The review is where that is caught.

{: .note }
> **Refinement is conversation.** You don't edit the graph directly — you tell the system what you want changed in plain language. It updates the graph and regenerates the narrative summary. You can refine as many times as you need before launching.

---

## Act III — The Agent Swarm

### Agents that do the work the work actually requires.

When you launch, a swarm of specialist agents goes to work in parallel — each assigned to exactly one piece of the graph, each equipped with only the tools that piece of work actually needs.

```
  PHASE 1  (all parallel)
  ──────────────────────
  Agent A → regulatory_environment_de_uk
    tools: web_search, web_browse, pdf_extraction
    → evidence envelope A

  Agent B → reimbursement_structures
    tools: web_search, web_browse, healthcare_policy_analysis
    → evidence envelope B

  Agent C → market_size_trajectory
    tools: web_search, economic_data_discovery, statistical_analysis
    → evidence envelope C
         │
         │  Phase synthesis
         ▼
  Phase 1 summary + confidence scores
         │
         ▼
  PHASE 2  (informed by Phase 1 summaries)
  ────────────────────────────────────────
  Agent D → competitive_landscape
  Agent E → ma_activity
         │
         │  Phase synthesis + assessment
         ▼
  PHASE 3 ...
```

No single agent does everything. Each does one thing well. The orchestrator reads the approved graph and assigns work items to specialists. Specialists report structured evidence envelopes — not free text, but typed, scored, citable outputs with explicit confidence levels.

The tools agents can use:

| Tool | What it does |
|---|---|
| `perplexity_search` | Live web search with source attribution |
| `web_browse` | Navigate to specific URLs, extract full content |
| `code_execution` | Write and run Python in a sandboxed venv |
| `url_fetch` | Download and inspect datasets, PDFs |
| `read_prior_evidence` | Pull specific findings from prior runs |

Skills combine these tools. `healthcare_policy_analysis` uses `web_search` + `web_browse` + `pdf_extraction`. `economic_modeling` uses `code_execution` + `statistical_analysis` + `data_transformation`. When a skill the graph needs doesn't exist yet, the system tries to synthesize it from available tools. When that's not possible, it flags the gap rather than guessing.

{: .highlight }
> **The evidence envelope** is the unit of trust. Every specialist produces one: what it found, how confident it is (0–1), what it couldn't determine, what tools it used, what sources it cited. The envelope is the proof of work. You can inspect any of them.

---

## Act IV — Transparency

### See everything. Not just the answer.

This is the part that changes how you think about AI.

While the swarm runs, every agent registers to the DAG in real time. You can watch the graph fill in — grey nodes (waiting), active nodes (running), green nodes (complete), red nodes (failed or partial). Each node is clickable. Click it, and you see the full evidence envelope: what the agent found, what it searched, what it couldn't determine.

After each phase completes, a synthesis appears — what the agents collectively established, where they contradicted each other, what the next phase needs to know.

```
  WHAT YOU CAN SEE

  ├── Agent DAG (live)
  │    every node · every status · every edge
  │
  ├── Evidence envelopes (per agent)
  │    findings · confidence score · sources
  │    tool calls made · what wasn't found
  │
  ├── Phase summaries
  │    consolidated understanding after each wave
  │    confidence assessment · gaps identified
  │
  ├── Artefacts
  │    generated code · downloaded datasets
  │    parsed documents · API responses
  │    all committed to git
  │
  └── Run log
       every milestone · every error
       model used per task · timing
```

This is what honest AI looks like:

- When an agent can't find enough evidence, it says so — and scores its confidence accordingly
- When a skill is missing, the system surfaces the gap rather than fabricating an answer
- Partial coverage is shown as partial — not inflated to look complete
- Every claim has a source. Every source has a commit.

> *"The output is not a result. It is a record."*

---

## Act V — Conversation and continuation

### Ask anything. Go further.

When the run completes, the system generates a briefing — a structured narrative of what was found, phase by phase, written in the style of a Perplexity deep research summary: inline citations linked to the specific agents and evidence that produced them.

Then you can talk to it.

Ask follow-up questions. Drill into a specific agent's reasoning. Request the actual dataset it downloaded. Understand why confidence was low on a particular question. Dispute a finding and ask the system to look again.

Every response is grounded in the evidence produced during the run. The system doesn't fabricate new research in this conversation — it helps you navigate what was actually found.

```
  You: "The regulatory section seemed confident but the reimbursement
        section was only 0.6 confidence. Why?"

  System: "Agent B found the GKV framework well-documented but noted that
           recent changes to the AMNOG process (post-2023 amendments) had
           limited secondary coverage. It marked 3 of 7 sub-questions as
           partially covered. The gaps are in: [1] accelerated assessment
           pathways for orphan designations, [2] companion diagnostics
           reimbursement, and [3] cross-border coverage agreements.
           Would you like me to queue those as a follow-on run?"
```

And if there is more to investigate:

**Continue the run.** Build on what was already found. Don't repeat covered ground. A follow-on brief is generated from the current run's gaps — the questions that surfaced but weren't answered. You review the new context graph, confirm the direction, and launch.

The next run's specialists know what the prior run found. They pull specific prior evidence when relevant. They do not re-do work already done.

```
  Run 1  →  Market landscape established. Gaps: competitive detail.
  Run 2  →  Competitive dynamics. Uses Run 1 evidence. Gaps: M&A recency.
  Run 3  →  M&A activity + synthesis. Uses Runs 1 + 2. Entry strategy.
```

Each run starts smarter than the last. The understanding compounds. The expert deepens.

> *"Follow the white rabbit."*

---

## Quick start

```bash
git clone https://github.com/ai-agents-for-humans/slow-ai
cd slow-ai
bash install.sh
uv run streamlit run main.py
```

The install script handles `uv`, dependencies, and walks you through API key setup interactively.

**What you need:**
- A Gemini API key (free tier works for exploration)
- Python 3.11+
- That's it

**Optional:** Bring your own models. Edit `src/slow_ai/llm/registry.json` to point any slot at any provider — OpenAI, Anthropic, Ollama, vLLM, anything OpenAI-compatible.

[View on GitHub](https://github.com/ai-agents-for-humans/slow-ai){: .btn .btn-primary }
[Read the architecture](architecture){: .btn }
