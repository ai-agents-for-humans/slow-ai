import re

import httpx
from pydantic import BaseModel

from slow_ai.config import settings


class PerplexityResult(BaseModel):
    answer: str
    citations: list[str]


async def perplexity_search(query: str) -> PerplexityResult:
    """Search Perplexity. Returns synthesised answer and cited URLs."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.perplexity_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": query}],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

    answer = data["choices"][0]["message"]["content"]
    citations = data.get("citations", [])

    # fallback: extract URLs from answer text if citations missing
    if not citations:
        citations = re.findall(r'https?://[^\s\)\"]+', answer)

    return PerplexityResult(answer=answer, citations=citations)
