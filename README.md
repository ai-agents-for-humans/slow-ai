```
 ██████  ██       ██████  ██     ██      █████  ██
██        ██      ██    ██ ██     ██    ██   ██  ██
 █████    ██      ██    ██ ██  █  ██    ███████  ██
     ██   ██      ██    ██ ██ ███ ██    ██   ██  ██
 ██████   ███████  ██████   ███ ███     ██   ██  ██
```

> *It's called Slow AI. In 2026. When everyone else is shipping "turbo", "instant", and "flash".*

![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)
![pydantic-ai](https://img.shields.io/badge/built%20with-pydantic--ai-7c3aed?style=flat-square)
![git](https://img.shields.io/badge/memory-git-f97316?style=flat-square)
![BYOM](https://img.shields.io/badge/BYOM-any%20provider-0ea5e9?style=flat-square)
![status](https://img.shields.io/badge/status-unfinished%20%26%20proud-22c55e?style=flat-square)

---

The name is a design decision.

Fast agents you cannot inspect, correct, or reproduce are not fast — they are expensive coin flips. And right now, every time you hand a research brief to a hosted agent platform, three things happen that nobody talks about:

**Your questions become someone else's training data.** Your competitive research, your due diligence briefs, your market theses — sitting in a context window you do not own, on infrastructure you did not choose.

**Your agents guzzle tokens and you have no idea why.** 40,000 tokens. A summary. No trace of what it searched, what it skipped, why it concluded what it did. You cannot verify it. You cannot reproduce it. You just paid for it.

**You are giving away the knowledge of your business.** Every workflow you run in a hosted platform is a knowledge transfer you did not sign up for. The patterns of how you investigate, what you care about, how your domain works — that is your moat. It is leaving the building every time you hit run.

Slow AI is my attempt to fix this. It is unfinished. The UI is clunky. The RL layer is designed but not coded. I am telling you this upfront because transparency is the entire point.

*Run it anyway.*

---

## What you get back

**Your data stays in your git.** Every run — every evidence envelope, every agent decision, every source, every artefact — is committed to a versioned branch on your own infrastructure. Not a platform's training data. Yours. When you build a moat, you keep the moat.

**You can see exactly what happened and why.** Every claim links to the agent that produced it. Every agent shows its confidence, its sources, the tools it called, what it couldn't find. When something goes wrong, you know where. When something is right, you know why.

**The knowledge your agents accumulate compounds.** Skills the system learns are written to a catalog that every future run can use. Prior run evidence is available to every follow-on run. The 50th investigation is smarter than the first — without retraining anything, without reconfiguring anything.

**You stay in control.** An agent proposes the workflow. You review it, shape it, and approve it before a single token is spent on research. You can inspect, correct, and redirect at every phase boundary. The agents work for you. Not the other way around.

---

## The nerdy bit

Slow AI treats agents the way distributed systems engineers treat services.

```
  Bounded context windows.     No agent sees everything — only what its
                               work item actually requires.

  Scoped permissions.          Each specialist gets only the tools its
                               task needs. Nothing more.

  Explicit memory.             Brief → wave context → agent working memory
                               → git. Every layer is inspectable and
                               bounded. No "just dump it all in context".

  Structured outputs.          Evidence envelopes, not free text.
                               Typed. Scored. Citable. Every claim has
                               a confidence level.

  Git as the persistence layer. One branch per run. Milestone commits.
                               The run is permanent. Auditable. Diffable.
                               Long-term memory that lives outside the model.
```

You would not deploy a distributed system with no observability. No logs, no traces, no way to replay what happened. You would not trust a service that couldn't show you why it made a decision.

The agents are the service. This is the observability layer.

---

## How it runs

```
  Interview      →  one question at a time, until the brief is precise
  Context graph  →  agent decomposes the brief into phases and work items
  You review it  →  shape it, approve it, or send it back
  Swarm launches →  specialists run in parallel, wave by wave
  You watch       →  or don't — the state is always on disk
  Results         →  every finding, every source, every gap, honestly reported
  Go deeper       →  chain runs, each one smarter than the last
```

Two independent planes. No shared state between them.

```
  ┌─────────────────────────────────┐
  │  UI  (Streamlit, for now)       │  ← reads files, renders state
  └──────────────┬──────────────────┘
                 │  files on disk only — no direct coupling
  ┌──────────────▼──────────────────┐
  │  Execution engine  (subprocess) │  ← writes files, commits to git
  │  plan → gate → waves → report   │
  └──────────────┬──────────────────┘
                 │
               git  (one branch per run · milestone commits)
```

The execution plane does not know or care what UI is reading its files. Streamlit today. React tomorrow. A CLI. An API. Swap it without touching the engine.

---

## Bring your own models — and your own infrastructure

One JSON file. No rebuilds.

```json
{
  "models": [
    { "name": "reasoning",  "model_id": "google-gla:gemini-3.1-pro",  "use_for": ["context_planning", "orchestration"] },
    { "name": "fast",       "model_id": "openai:gpt-4o-mini",         "use_for": ["skill_synthesis", "interview"] },
    { "name": "code",       "model_id": "ollama:qwen2.5-coder:7b",    "use_for": ["code_generation"] },
    { "name": "specialist", "model_id": "anthropic:claude-opus-4-6",  "use_for": ["specialist_research"] }
  ]
}
```

**For regulated environments:** point every slot at a local Ollama instance. No data leaves your infrastructure. The agents do not know or care which provider they use. Neither does the engine.

Supported: Google · OpenAI · Anthropic · OpenRouter · Ollama · any OpenAI-compatible endpoint.

---

## Run it

```bash
git clone https://github.com/ai-agents-for-humans/slow-ai
cd slow-ai
bash install.sh
uv run streamlit run main.py
```

The install script handles `uv`, dependencies, and walks you through API key setup. You need a Gemini key for the default model config. Perplexity is optional — if you have it, web search gets better. Everything else runs without it.

**What you need:** Python 3.11+. Git. Two API keys maximum.
**What you do not need:** Docker. A database. An account with any platform.

---

## What's honest about the current state

The UI is Streamlit. It works. It is not pretty. There is a React migration in the roadmap because Streamlit hits real limits at the layout level — and this system deserves a proper console.

The RL layer is designed in full — trajectory corpus, GRPO formulation, sidecar policy model — but not implemented. The data it needs is being collected correctly right now, in every run, committed to git. The learning infrastructure comes next.

The MAPE-K observer — the circuit breaker that watches for runaway agents, cost ceiling breaches, confidence drops — is architected but not built. The only current protection against a runaway run is the maximum wave count.

The HITL gate exists and triggers correctly. It does not yet block. It logs and continues. Full blocking pause is on the roadmap.

This is a working system with a point of view. Not a finished product. Not a platform with a pricing page.

It currently works with Gemini API key and Perplexity API key. You cannot yet bring your own models.

[Full known issues →](https://ai-agents-for-humans.github.io/slow-ai/known-issues)

---

## Documentation

Everything is at **[ai-agents-for-humans.github.io/slow-ai](https://ai-agents-for-humans.github.io/slow-ai)**

- [How it works](https://ai-agents-for-humans.github.io/slow-ai/how-it-works) — five acts, one thread of understanding
- [Architecture](https://ai-agents-for-humans.github.io/slow-ai/architecture) — the full technical deep dive
- [Getting started](https://ai-agents-for-humans.github.io/slow-ai/getting-started) — from zero to first run
- [Known Issues](https://ai-agents-for-humans.github.io/slow-ai/known-issues) - Known issues
- [What's next](https://ai-agents-for-humans.github.io/slow-ai/whats-next) — the roadmap and why

---

*Your agents. Your data. Your moat.*
