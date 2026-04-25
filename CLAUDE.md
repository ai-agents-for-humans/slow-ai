# Slow AI — Claude Code context

Read this before anything else. It gives you full project context so you can contribute without re-deriving the architecture from scratch.

---

## What this project is

Slow AI is an agentic research orchestration system. It runs multi-agent research investigations in parallel, phase by phase, on your local infrastructure. Everything is file-based and git-committed. No external platforms. No shared state you don't own.

The name is intentional. Deliberate, inspectable, reproducible work — the opposite of black-box hosted agents.

---

## Architecture in one page

### Two independent planes

```
  ┌─────────────────────────────────┐
  │  UI  (FastAPI + htmx)           │  reads files, renders state over SSE
  └──────────────┬──────────────────┘
                 │  files on disk only — no direct coupling
  ┌──────────────▼──────────────────┐
  │  Execution engine  (subprocess) │  writes files, commits to git
  │  plan → gate → waves → report   │
  └──────────────┬──────────────────┘
                 │
               git  (one branch per run · milestone commits)
```

The UI never calls the execution engine directly. It launches it as a subprocess (`python -m slow_ai.research`) and reads the files it writes. This isolation is intentional — threading caused asyncio event loop conflicts. Do not suggest threading as an alternative.

### Execution flow

```
Interview  →  ProblemBrief  →  ContextGraph  →  Viability check
  →  Skill synthesis (if gaps)  →  Wave loop:
       Phase N: [specialist-1 ‖ specialist-2 ‖ ...] → orchestrator assesses
         → synthesise  →  proceed / circuit_break / escalate
  →  ResearchReport  →  git commit
```

### Context graph

The `ContextGraph` is the approved work plan. It has `Phase` objects (sequential) each containing `WorkItem` objects (parallel within the phase). Every specialist agent maps to exactly one work item. No agent sees the full graph — only its own work item + the phase's prior evidence.

### Skill system

Skills live in `src/slow_ai/skills/catalog/{skill_name}/SKILL.md`. Each file has YAML frontmatter (name, description, tools, tags) and a playbook body (when to use, how to execute, output contract, quality bar, pairs with).

Built-in skills: `web_search`, `web_browse`, `pdf_extraction`, `dataset_inspection`, `code_execution`.

The context planner assigns skill names from the catalog to work items. The skill resolver checks availability. The synthesizer can create new skill definitions when existing ones don't cover a gap. **Always use catalog names exactly** — do not invent synonyms.

### Evidence envelopes

Every specialist writes an `EvidenceEnvelope` to `runs/{run_id}/envelopes/`. Fields: `agent_id`, `role`, `status`, `proof` (dict), `verdict`, `confidence` (0.0–1.0), `cost_tokens`, `artefacts` (list of paths). This is the atomic unit of evidence — everything in the UI traces back to envelopes.

---

## Source map

```
src/slow_ai/
  agents/
    orchestrator.py       — context planner, orchestrator assess, phase synthesis, run summary
    specialist.py         — specialist agent loop (tools, memory, artefact writes)
    interviewer.py        — interview agent (produces ProblemBrief)
    run_conversation.py   — post-run chat agent (grounded in run evidence)
  execution/
    git_store.py          — GitStore: run directories, live/ files, git commits
    registry.py           — AgentRegistry: in-memory agent tracking per run
  skills/
    resolver.py           — viability_assess: checks catalog coverage, identifies gaps
    synthesizer.py        — synthesize_skills: LLM-generates new SKILL.md files
  tools/
    perplexity.py         — perplexity_search tool (Perplexity API)
    web_browse.py         — web_browse tool (httpx + BeautifulSoup)
    url_fetch.py          — raw URL fetch
    code_execution.py     — sandboxed Python execution (per-run venv)
    code_generation.py    — code generation tool
    run_reader.py         — read_prior_evidence tool (cross-run context)
  models.py               — all Pydantic models (ProblemBrief, ContextGraph, EvidenceEnvelope, ...)
  config.py               — Settings (GEMINI_KEY_SLOW_AI, PERPLEXITY_KEY_SLOW_AI)
  research/runner.py      — run_research(): the main execution loop

app/
  main.py                 — FastAPI app, mounts static + templates, includes routers
  api/
    interview.py          — POST /api/interview/start, /api/interview/message
    brief.py              — POST /api/brief/confirm
    graph.py              — GET/POST /api/graph/{project_id}
    projects.py           — GET /api/projects
    runs.py               — POST /api/runs/launch, GET /api/runs/{run_id}/stream (SSE),
                            GET /api/runs/{run_id}/state, POST /api/runs/{run_id}/chat
  templates/
    base.html             — shell: sidebar + main slot
    views/
      interview.html      — full-width chat, htmx, typing indicator
      brief.html          — brief confirmation card
      graph_review.html   — Cytoscape context graph + refinement chat
      run.html            — unified live run + results page (tab switch on completion)
    partials/             — sidebar, agent drawer, phase cards, etc.
  static/
    js/
      dag.js              — Cytoscape DAG init + SSE-driven updates
      chat.js             — chat scroll, send, stream
      run_stream.js       — SSE EventSource → Alpine store dispatch
```

---

## Key design decisions

| Decision | Rationale |
|---|---|
| Subprocess isolation for runner | Threading causes `RuntimeError: asyncio.locks.Event bound to different event loop` with nest_asyncio + anyio. Subprocess is the permanent fix. |
| File-based state (no DB) | Any reader (UI, CLI, script) can read run state without a running service. Plain JSON. Git-versioned. |
| Evidence envelopes as the atom | Every claim is traceable to an agent, a confidence score, and sources. No free-text summaries that can't be verified. |
| Two-plane architecture | The UI is a thin render layer. The execution plane is completely independent. A different UI (CLI, Jupyter) can consume the same files. |
| Skill catalog over hardcoded tools | Domain knowledge lives in SKILL.md playbooks, not in agent prompts. Skills compose — a specialist gets injected with the playbooks for its assigned skills at runtime. |
| Git as long-term memory | One branch per run. Milestone commits. The run corpus is the RL training data — collected correctly from day one. |

---

## Environment and run

```bash
# Start the app
PYTHONPATH=. uv run uvicorn app.main:app --reload

# Run execution plane directly (no UI)
uv run python -m slow_ai.research --brief path/to/brief.json --graph path/to/graph.json

# Run tests
uv run pytest
```

**API keys** (stored in `.env` and shell profile):
- `GEMINI_KEY_SLOW_AI` — Google Gemini (required)
- `PERPLEXITY_KEY_SLOW_AI` — Perplexity web search (optional, improves search quality)

Both are read by `src/slow_ai/config.py` via pydantic-settings. Env vars take priority over `.env`.

**Models** are configured in `src/slow_ai/llm/registry.json`. Change `model_id` to swap providers — Google, OpenAI, Anthropic, Ollama, any OpenAI-compatible endpoint. No code changes required.

---

## On-disk run structure

```
runs/{run_id}/
  input_brief.json        — the brief that started the run
  approved_graph.json     — the approved context graph
  envelopes/              — one JSON file per specialist (EvidenceEnvelope)
  artefacts/              — generated code, datasets, parsed docs (per agent subdir)
  live/                   — real-time state files read by the UI (status.json, dag.json, log.jsonl, ...)
  conversation.jsonl      — full history: interview, review, post-run chat
  runner.log              — structured run log

output/{project_id}/
  problem_brief.json
  runs.jsonl              — index of all runs for this project
```

---

## Current state (as of v1, 2026-04-25)

**Working end-to-end:**
- Interview → brief → context graph review → swarm launch → live DAG → results
- Phase synthesis + confidence scoring
- Tool calls (web search, web browse, PDF, code execution)
- Artefact generation and viewer
- Post-run chat grounded in run evidence
- Run chaining (prior_run_ids on ProblemBrief)
- Skill catalog with 5 built-in skills
- Skill synthesis for gaps

**Not yet built (roadmap):**
- RL layer (trajectory corpus is being collected correctly; GRPO formulation designed)
- MAPE-K observer / circuit breaker (only max wave count guard exists)
- HITL gate blocking (logs and continues; does not pause)
- Branch protection + CI pipeline
- Pre-commit hooks (ruff, mypy)
- Test coverage (pytest infra exists, tests directory is sparse)

---

## How to work with this codebase

**Before changing anything non-trivial:** discuss architecture first. The user is the domain expert and wants to align on approach before code is written.

**Do not:**
- Suggest threading as an alternative to subprocess isolation
- Add error handling for scenarios that can't happen
- Invent new skill names — always prefer catalog names
- Add docstrings, comments, or type annotations to code you didn't change
- Create new files unless strictly necessary

**Do:**
- Read the relevant files before proposing changes
- Keep the two-plane separation clean — UI reads files, engine writes files
- Trust pydantic model validation at the boundary; don't re-validate internally
- When adding a tool, also add a SKILL.md in the catalog that uses it
