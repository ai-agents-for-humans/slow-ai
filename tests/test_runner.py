import pytest

# Integration test — requires live API keys. Run manually with:
#   GEMINI_KEY_SLOW_AI=... uv run pytest tests/test_runner.py -m integration
pytestmark = pytest.mark.skip(reason="live integration test — requires API keys")
