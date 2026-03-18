import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel


class BrowseResult(BaseModel):
    url: str
    title: str = ""
    text: str = ""
    success: bool = True
    error: str | None = None


async def web_browse(url: str, max_chars: int = 4000) -> BrowseResult:
    """Fetch URL and extract readable text. Max 4000 chars."""
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SlowAI-Research/1.0)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title else ""
        main = soup.find("main") or soup.find("body")
        text = " ".join(main.get_text(separator=" ").split()) if main else ""
        text = text[:max_chars]

        return BrowseResult(url=url, title=title, text=text)

    except Exception as e:
        return BrowseResult(url=url, success=False, error=str(e))
