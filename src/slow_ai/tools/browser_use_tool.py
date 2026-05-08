import logging

from pydantic import BaseModel

from slow_ai.config import settings

logger = logging.getLogger(__name__)


class BrowserUseResult(BaseModel):
    task: str
    result: str = ""
    success: bool = True
    error: str | None = None


async def browser_use(task: str, max_steps: int = 25) -> BrowserUseResult:
    """
    Run an LLM-driven browser agent to complete an interactive web task.
    Handles JS-rendered pages, login flows, form interactions, multi-step navigation.
    Falls back with a clear error if browser-use or Playwright is not installed.
    """
    try:
        from browser_use import Agent as BrowserAgent
        from browser_use.llm.google.chat import ChatGoogle
    except ImportError as e:
        return BrowserUseResult(
            task=task,
            success=False,
            error=(
                f"browser-use not installed ({e}). "
                "Run: uv add browser-use && uv run playwright install chromium"
            ),
        )

    try:
        llm = ChatGoogle(model="gemini-2.0-flash", api_key=settings.gemini_key_slow_ai)
        agent = BrowserAgent(task=task, llm=llm)
        history = await agent.run(max_steps=max_steps)
        final = history.final_result() or ""
        return BrowserUseResult(task=task, result=final)
    except Exception as e:
        logger.warning("browser_use failed for task %r: %s", task[:80], e)
        return BrowserUseResult(task=task, success=False, error=str(e))
    finally:
        try:
            if "agent" in dir() and agent.browser_session:
                await agent.browser_session.stop()
        except Exception:
            pass
