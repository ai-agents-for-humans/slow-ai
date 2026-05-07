"""
Model registry — bring your own model.

Agents call ModelRegistry().for_task("context_planning") to get the right
model for their task type. Adding a new provider (Ollama, Anthropic, OpenAI,
Mistral) is a registry entry, not a code change.

Supported provider types:
  "google"            — native pydantic_ai Google provider
  "openai"            — native pydantic_ai OpenAI provider
  "anthropic"         — native pydantic_ai Anthropic provider
  "ollama"            — native pydantic_ai OllamaModel (uses JSON schema output,
                        no tool-call wrangling, grammar-constrained decoding)
  "openai_compatible" — legacy alias for "ollama"; kept for existing registry files

Each registry entry must declare "api_key_setting": the field name on Settings
that holds the key for that provider. ModelRegistry validates at init that all
configured models have their keys available, so misconfiguration fails fast at
startup rather than mid-run. Ollama entries need no api_key_setting.
"""

import json
from pathlib import Path
from typing import Any


class ModelRegistry:
    def __init__(self):
        from slow_ai.config import settings

        local_path = Path(__file__).parent / "registry.local.json"
        registry_path = (
            local_path if local_path.exists() else Path(__file__).parent / "registry.json"
        )
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        self._models = {m["name"]: m for m in data["models"]}

        self._task_map: dict[str, str] = {}
        for name, model in self._models.items():
            for task in model.get("use_for", []):
                self._task_map[task] = name

        self._instances: dict[str, Any] = {}
        for name, entry in self._models.items():
            self._instances[name] = self._build(entry, settings)

    def _build(self, entry: dict, settings: Any) -> Any:
        provider = entry.get("provider", "google")

        if provider in ("ollama", "openai_compatible"):
            return self._build_ollama(entry)

        api_key_setting = entry.get("api_key_setting")
        api_key = getattr(settings, api_key_setting, None) if api_key_setting else None
        if not api_key:
            raise RuntimeError(
                f"Model '{entry['name']}' requires {api_key_setting.upper()} "
                f"but it is not set. Add it to your .env file."
            )

        model_id = entry["model_id"]
        if provider == "google":
            return self._build_google(model_id, api_key)
        if provider == "openai":
            return self._build_openai(model_id, api_key)
        if provider == "anthropic":
            return self._build_anthropic(model_id, api_key)
        raise ValueError(f"Unknown provider '{provider}' for model '{entry['name']}'")

    def _build_google(self, model_id: str, api_key: str) -> Any:
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(model_id, provider=GoogleProvider(api_key=api_key))

    def _build_openai(self, model_id: str, api_key: str) -> Any:
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIModel(model_id, provider=OpenAIProvider(api_key=api_key))

    def _build_anthropic(self, model_id: str, api_key: str) -> Any:
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(model_id, provider=AnthropicProvider(api_key=api_key))

    def _build_ollama(self, entry: dict) -> Any:
        from pydantic_ai.models.ollama import OllamaModel
        from pydantic_ai.providers.ollama import OllamaProvider

        base_url = entry.get("base_url", "http://localhost:11434/v1")
        return OllamaModel(
            entry["model_id"],
            provider=OllamaProvider(base_url=base_url),
        )

    def for_task(self, task_type: str) -> Any:
        model_name = self._task_map.get(task_type, "fast")
        return self._instances[model_name]

    def model_id_for_task(self, task_type: str) -> str:
        model_name = self._task_map.get(task_type, "fast")
        return self._models[model_name]["model_id"]

    def available_tasks(self) -> dict[str, str]:
        return {task: self._models[name]["model_id"] for task, name in self._task_map.items()}
