import logging
import re

import httpx
from pydantic import BaseModel

from slow_ai.config import settings
from slow_ai.utils import retry_async

logger = logging.getLogger(__name__)


class PerplexityResult(BaseModel):
    answer: str
    citations: list[str]


async def perplexity_search(query: str) -> PerplexityResult:
    """Search Perplexity. Returns synthesised answer and cited URLs.

    Retries up to 3 times with exponential backoff on network errors and
    rate-limit (429) responses.
    """
    async def _call() -> PerplexityResult:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_key_slow_ai}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": query}],
                },
                timeout=30.0,
            )
            if response.status_code == 429:
                raise httpx.HTTPStatusError(
                    "Rate limited (429)", request=response.request, response=response
                )
            response.raise_for_status()
            data = response.json()

        answer = data["choices"][0]["message"]["content"]
        citations = data.get("citations", [])
        if not citations:
            citations = re.findall(r'https?://[^\s\)\"]+', answer)

        return PerplexityResult(answer=answer, citations=citations)

    logger.debug("perplexity_search: %s", query[:120])
    return await retry_async(
        _call,
        max_attempts=3,
        base_delay=3.0,
        retryable=(httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException),
    )
