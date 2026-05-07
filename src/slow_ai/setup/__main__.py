"""
Interactive setup wizard.

Writes:
  src/slow_ai/llm/registry.local.json  — model/provider config (git-ignored)
  .env                                  — API keys (safe merge, git-ignored)

Run with:  uv run python -m slow_ai.setup
"""

import getpass
import json
import sys
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[4]  # …/slow_ai/
REGISTRY_LOCAL = Path(__file__).parents[1] / "llm" / "registry.local.json"
REGISTRY_TEMPLATE = Path(__file__).parents[1] / "llm" / "registry.json"
ENV_FILE = _REPO_ROOT / ".env"

# (provider_key, display_label, env_var | None, hint)
PROVIDERS = [
    ("google", "Google Gemini", "GEMINI_KEY_SLOW_AI", "aistudio.google.com/app/apikey"),
    ("anthropic", "Anthropic Claude", "ANTHROPIC_API_KEY", "console.anthropic.com"),
    ("openai", "OpenAI", "OPENAI_API_KEY", "platform.openai.com/api-keys"),
    ("ollama", "Ollama (local)", None, None),
]

# (key, display_label, env_var, hint, available)
WEB_SEARCH_PROVIDERS = [
    ("perplexity", "Perplexity", "PERPLEXITY_KEY_SLOW_AI", "perplexity.ai/settings/api", True),
    ("parallel", "Parallel AI", "PARALLEL_KEY_SLOW_AI", "parallel.ai", False),
    ("none", "None — skip", None, None, True),
]

KNOWN_MODELS = {
    "google": ["gemini-2.5-pro-preview-05-06", "gemini-2.5-flash-preview-05-20"],
    "anthropic": ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    "openai": ["gpt-4.1", "gpt-4o", "o3"],
}


# ── helpers ──────────────────────────────────────────────────────────────────


def _sep(title: str) -> None:
    print(f"\n── {title} {'─' * max(0, 50 - len(title))}\n")


def _pick_numbered(prompt: str, options: list[str], allow_manual: bool = True) -> str:
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    if allow_manual:
        print(f"  {len(options) + 1}. Enter manually")
    while True:
        raw = input("> ").strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if allow_manual and idx == len(options):
                return input("  Model name: ").strip()
            if 0 <= idx < len(options):
                return options[idx]
        elif raw:
            return raw
        print(f"  Enter a number 1–{len(options) + (1 if allow_manual else 0)}")


def _ask_key(env_var: str, hint: str) -> str:
    print(f"  {env_var}")
    if hint:
        print(f"  Get yours at: {hint}")
    print("  (press Enter to skip — add to .env later)")
    return getpass.getpass("  Key: ").strip()


def _detect_ollama_models() -> list[str] | None:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = json.loads(r.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return None


def _update_env(updates: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip().strip("'\"")
    existing.update({k: v for k, v in updates.items() if v})
    ENV_FILE.write_text(
        "\n".join(f"{k}='{v}'" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    print("\n=== Slow AI Setup ===")

    if REGISTRY_LOCAL.exists():
        ans = input("\nregistry.local.json already exists. Reconfigure? [y/N] ").strip().lower()
        if ans != "y":
            print("Setup cancelled.")
            return

    # ── model provider ────────────────────────────────────────────────────────
    _sep("Model Provider")
    chosen_label = _pick_numbered(
        "Choose your provider:",
        [label for _, label, _, _ in PROVIDERS],
        allow_manual=False,
    )
    provider_key, provider_label, provider_env_var, provider_hint = next(
        p for p in PROVIDERS if p[1] == chosen_label
    )

    # ── model ─────────────────────────────────────────────────────────────────
    base_url = None
    if provider_key == "openai_compatible":
        print("\nChecking Ollama at localhost:11434 ...")
        models = _detect_ollama_models()
        if models is None:
            print("  Could not reach Ollama. Make sure it is running: ollama serve")
            model_id = input("  Enter model name anyway (e.g. gemma3:4b): ").strip()
        elif not models:
            print("  Ollama is running but no models are installed.")
            print("  Pull one first: ollama pull <model>")
            model_id = input("  Enter model name: ").strip()
        else:
            model_id = _pick_numbered(f"\n  Found {len(models)} model(s):", models)
        base_url = "http://localhost:11434/v1"
    else:
        known = KNOWN_MODELS.get(provider_key, [])
        if known:
            model_id = _pick_numbered(f"\nChoose a {provider_label} model:", known)
        else:
            model_id = input(f"\nEnter {provider_label} model ID: ").strip()

    # ── web search ────────────────────────────────────────────────────────────
    _sep("Web Search")
    search_options = []
    for key, label, _, _, available in WEB_SEARCH_PROVIDERS:
        search_options.append(label if available else f"{label}  (coming soon)")
    chosen_search_label = _pick_numbered(
        "Choose your web search provider:", search_options, allow_manual=False
    )
    # strip the "(coming soon)" suffix before matching
    chosen_search_label_clean = chosen_search_label.replace("  (coming soon)", "")
    search_key, search_label, search_env_var, search_hint, search_available = next(
        p for p in WEB_SEARCH_PROVIDERS if p[1] == chosen_search_label_clean
    )
    if not search_available:
        print(f"  {search_label} is not yet available — defaulting to no web search.")
        search_key, search_env_var, search_hint = "none", None, None

    # ── api keys ──────────────────────────────────────────────────────────────
    keys_to_write: dict[str, str] = {}

    if provider_env_var:
        _sep("API Keys")
        print(f"  Model provider: {provider_label}")
        val = _ask_key(provider_env_var, provider_hint)
        if val:
            keys_to_write[provider_env_var] = val

    if search_env_var:
        if not provider_env_var:
            _sep("API Keys")
        print(f"\n  Web search: {search_label}")
        val = _ask_key(search_env_var, search_hint)
        if val:
            keys_to_write[search_env_var] = val

    # ── write registry.local.json ─────────────────────────────────────────────
    template = json.loads(REGISTRY_TEMPLATE.read_text(encoding="utf-8"))
    models_out = []
    for tmpl in template["models"]:
        entry: dict = {
            "name": tmpl["name"],
            "model_id": model_id,
            "provider": provider_key,
            "strengths": tmpl["strengths"],
            "use_for": tmpl["use_for"],
            "notes": tmpl["notes"],
        }
        if base_url:
            entry["base_url"] = base_url
        if provider_env_var:
            entry["api_key_setting"] = provider_env_var.lower()
        models_out.append(entry)

    REGISTRY_LOCAL.write_text(json.dumps({"models": models_out}, indent=2), encoding="utf-8")

    # ── write .env ────────────────────────────────────────────────────────────
    if keys_to_write:
        _update_env(keys_to_write)

    # ── summary ───────────────────────────────────────────────────────────────
    print("\n" + "─" * 54)
    print(f"  Model    : {provider_label} / {model_id}")
    print(f"  Search   : {search_label if search_key != 'none' else 'none'}")
    print(f"  Registry : {REGISTRY_LOCAL}")
    if keys_to_write:
        print(f"  Keys     : {', '.join(keys_to_write)} → .env")
    print("\n  Start:  uv run uvicorn app.main:app --reload\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
