# Slow AI — Phase 1 init
## For Claude Code

---

## The rule

Build only what is in this file.
After every file you create, stop. Tell me what you built. Wait for my go-ahead before the next file.
Do not build ahead. Do not infer what comes next. One file at a time.

---

## What we are building

A terminal-based interview agent.
The user runs it, has a conversation with an LLM, and at the end a validated problem brief is saved to disk.
Nothing else. No orchestrator, no agents, no git, no web server.

---

## Stack

- Python, managed with `uv`
- `pydantic` and `pydantic-ai` for the agent and models
- `google-generativeai` as the LLM provider (Gemini)
- `rich` for terminal output
- No other dependencies

---

## Project structure to create

```
slow-ai/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
└── src/
    └── slow_ai/
        ├── __init__.py
        ├── config.py
        ├── models.py
        └── agents/
            ├── __init__.py
            └── interviewer.py
└── main.py
```

Create this structure one file at a time. Stop after each one.

---

## File specifications

### `pyproject.toml`

Use `uv`. Project name `slow-ai`. Python `>=3.11`.

Dependencies:
- `pydantic>=2.0`
- `pydantic-ai[google]`
- `google-generativeai`
- `rich`
- `python-dotenv`
- `pydantic-settings`

Include a `[project.scripts]` entry: `slow-ai = "main:main"`.

---

### `.env.example`

```
GEMINI_API_KEY=your-key-here
```

---

### `.gitignore`

Standard Python gitignore. Also ignore `.env` and `output/`.

---

### `src/slow_ai/config.py`

Pydantic `BaseSettings` class called `Settings`.
Reads `GEMINI_API_KEY` from environment.
Loads `.env` automatically.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str

    model_config = {"env_file": ".env"}

settings = Settings()
```

---

### `src/slow_ai/models.py`

One model: `ProblemBrief`.

```python
from pydantic import BaseModel
from typing import Any

class ProblemBrief(BaseModel):
    goal: str
    domain: str
    constraints: dict[str, Any]
    unknowns: list[str]
    success_criteria: list[str]
    milestone_flags: list[str]
    excluded_paths: list[str]
```

Nothing else in this file. No other models yet.

---

### `src/slow_ai/agents/interviewer.py`

A PydanticAI agent that conducts the interview and returns a `ProblemBrief`.

Use `google-gla:gemini-2.0-flash` as the model.
Pass the API key via the `GEMINI_API_KEY` environment variable — PydanticAI's Google provider
picks it up automatically when the env var is set. No need to pass it explicitly.

PydanticAI Gemini setup:

```python
import os
from pydantic_ai import Agent
from slow_ai.models import ProblemBrief
from slow_ai.config import settings

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

interviewer = Agent(
    model="google-gla:gemini-2.0-flash",
    result_type=ProblemBrief,
    system_prompt=SYSTEM_PROMPT,
)
```

System prompt:

```
You are a research consultant helping a user define a data research problem precisely.

Your job is to interview the user until you have enough to fill out a complete ProblemBrief
with these fields: goal, domain, constraints, unknowns, success_criteria,
milestone_flags, excluded_paths.

Rules:
- Ask one question at a time. Never more than one.
- Start by asking the user to describe the problem they want to solve.
- Push back gently if the answer is vague. Specific goals produce better research.
- Surface assumptions the user has not stated explicitly.
- When you have enough information, tell the user you are ready to produce the brief.
- Present the complete brief clearly and ask for confirmation before finalising.
- Do not finalise without explicit confirmation from the user.

Domain context: the user works in earth observation and geospatial data.
```

The agent should:
- Accept a conversation history as input (list of message dicts)
- Return either a follow-up question as a string, or a completed `ProblemBrief`
- Keep conversation history across turns so context is preserved

For multi-turn conversation, use `agent.run()` with the `message_history` parameter
that PydanticAI provides — pass the previous `result.all_messages()` on each subsequent turn.

---

### `main.py`

Entry point. Runs the interview loop in the terminal using `rich`.

Behaviour:
- Print a welcome message on start
- Loop: show agent message → get user input → send to agent with full history
- When the agent returns a `ProblemBrief`, display it as a formatted `rich` table
- Ask the user to confirm (y/n)
- On confirmation: save to `output/problem_brief.json`, print the path, exit
- On rejection: continue the conversation so the user can correct it

The terminal layout:
- Agent messages: left-aligned, teal
- User messages: right-aligned, white
- Keep it simple — no complex TUI, just `rich.console`

---

## Acceptance criteria

Before telling me Phase 1 is done, verify:

- [x] `uv run main.py` starts without errors
- [x] The agent asks one question at a time
- [x] A complete `ProblemBrief` is produced and confirmed by the user
- [x] `output/{uuid}/problem_brief.json` is saved and validates against the Pydantic model
- [x] The conversation feels like a consultation, not a form

---

## What not to build

Do not build any of the following — they are for later phases:

- Git integration
- Temporal workflows
- Orchestrator
- Research agents
- Skills or process registry
- FastAPI or any web server
- Frontend or React

If you find yourself reaching for any of these, stop and check back with me.

---

## Start here

Create `pyproject.toml` first. Show it to me. Wait.
