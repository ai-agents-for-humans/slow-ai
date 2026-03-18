from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slow_ai.tools.perplexity import PerplexityResult, perplexity_search
from slow_ai.tools.web_browse import BrowseResult, web_browse


# --- perplexity_search ---

@pytest.fixture
def mock_perplexity_response():
    return {
        "choices": [{"message": {"content": "Sentinel-2 provides 10m resolution data."}}],
        "citations": ["https://scihub.copernicus.eu", "https://earthengine.google.com"],
    }


async def test_perplexity_returns_answer_and_citations(mock_perplexity_response, mocker):
    mock_response = MagicMock()
    mock_response.json.return_value = mock_perplexity_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

    mocker.patch("slow_ai.tools.perplexity.httpx.AsyncClient", return_value=mock_client)

    result = await perplexity_search("Sentinel-2 East Africa")

    assert isinstance(result, PerplexityResult)
    assert result.answer == "Sentinel-2 provides 10m resolution data."
    assert len(result.citations) == 2
    assert "scihub.copernicus.eu" in result.citations[0]


async def test_perplexity_extracts_urls_from_answer_when_no_citations(mocker):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "See https://example.com for more info."}}],
        "citations": [],
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

    mocker.patch("slow_ai.tools.perplexity.httpx.AsyncClient", return_value=mock_client)

    result = await perplexity_search("any query")
    assert "https://example.com" in result.citations


# --- web_browse ---

_SAMPLE_HTML = """
<html>
  <head><title>Copernicus Open Access Hub</title></head>
  <body>
    <nav>Skip nav</nav>
    <main>
      <p>Sentinel-2 data is freely available for download.</p>
    </main>
    <footer>Footer content</footer>
  </body>
</html>
"""


async def test_web_browse_returns_title_and_text(mocker):
    mock_response = MagicMock()
    mock_response.text = _SAMPLE_HTML
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

    mocker.patch("slow_ai.tools.web_browse.httpx.AsyncClient", return_value=mock_client)

    result = await web_browse("https://scihub.copernicus.eu")

    assert result.success is True
    assert result.title == "Copernicus Open Access Hub"
    assert "Sentinel-2 data is freely available" in result.text
    assert "Skip nav" not in result.text
    assert "Footer content" not in result.text


async def test_web_browse_returns_error_on_failure(mocker):
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get = AsyncMock(
        side_effect=Exception("Connection timeout")
    )

    mocker.patch("slow_ai.tools.web_browse.httpx.AsyncClient", return_value=mock_client)

    result = await web_browse("https://unreachable.example.com")

    assert result.success is False
    assert "Connection timeout" in result.error


async def test_web_browse_respects_max_chars(mocker):
    long_text = "word " * 2000
    mock_response = MagicMock()
    mock_response.text = f"<html><body><main>{long_text}</main></body></html>"
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

    mocker.patch("slow_ai.tools.web_browse.httpx.AsyncClient", return_value=mock_client)

    result = await web_browse("https://example.com", max_chars=100)
    assert len(result.text) <= 100
