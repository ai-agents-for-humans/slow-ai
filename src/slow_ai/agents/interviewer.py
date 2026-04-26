import os
from pathlib import Path

from pydantic_ai import Agent

from slow_ai.config import settings
from slow_ai.llm import ModelRegistry
from slow_ai.models import ProblemBrief
from slow_ai.tools.perplexity import perplexity_search

os.environ["GEMINI_API_KEY"] = settings.gemini_key_slow_ai

_SKILL_PATH = (
    Path(__file__).parents[1] / "skills" / "catalog" / "interview_facilitation" / "SKILL.md"
)


def _load_system_prompt() -> str:
    content = _SKILL_PATH.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    return parts[2].strip() if len(parts) >= 3 else content


_tools = [perplexity_search] if settings.perplexity_key_slow_ai else []

interviewer = Agent(
    model=ModelRegistry().for_task("interview"),
    output_type=str | ProblemBrief,
    system_prompt=_load_system_prompt(),
    tools=_tools,
)
