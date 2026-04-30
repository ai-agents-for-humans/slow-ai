import pytest

# Live integration tests — require API keys and call real LLMs.
# Run manually: GEMINI_KEY_SLOW_AI=... uv run pytest tests/test_specialists.py -m integration
pytestmark = pytest.mark.skip(reason="live integration test — requires API keys")
