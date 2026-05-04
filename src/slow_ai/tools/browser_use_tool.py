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
    Falls back with a clear error if browser-use is not installed.
    """
    try:
        from browser_use import Agent as BrowserAgent
        from browser_use.browser.browser import Browser, BrowserConfig
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as e:
        return BrowserUseResult(
            task=task,
            success=False,
            error=(
                f"browser-use not installed ({e}). "
                "Run: uv add browser-use langchain-google-genai && uv run playwright install chromium"
            ),
        )

    browser = None
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=settings.gemini_key_slow_ai,
        )
        browser = Browser(config=BrowserConfig(headless=True))
        agent = BrowserAgent(task=task, llm=llm, browser=browser)
        history = await agent.run(max_steps=max_steps)
        final = history.final_result() or ""
        return BrowserUseResult(task=task, result=final)
    except Exception as e:
        logger.warning("browser_use failed for task %r: %s", task[:80], e)
        return BrowserUseResult(task=task, success=False, error=str(e))
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
