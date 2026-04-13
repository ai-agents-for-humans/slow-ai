"""
Model registry — bring your own model.

Agents call ModelRegistry().for_task("context_planning") to get the right
model for their task type. Adding a new provider (Ollama, Anthropic, OpenAI,
Mistral) is a registry entry, not a code change.

Supported provider types:
  "google"            — native pydantic_ai Google provider (model_id passed as string)
  "openai"            — native pydantic_ai OpenAI provider
  "anthropic"         — native pydantic_ai Anthropic provider
  "openai_compatible" — any OpenAI-compatible endpoint (Ollama, vLLM, LM Studio, etc.)
                        Requires: base_url, optional api_key
"""

import json
from pathlib import Path
from typing import Any


class ModelRegistry:
    def __init__(self):
        registry_path = Path(__file__).parent / "registry.json"
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        self._models = {m["name"]: m for m in data["models"]}
        # Build reverse lookup: task_type -> model name
        self._task_map: dict[str, str] = {}
        for name, model in self._models.items():
            for task in model.get("use_for", []):
                self._task_map[task] = name

    def for_task(self, task_type: str) -> Any:
        """
        Return the pydantic_ai model for the given task type.

        For native providers (google, openai, anthropic): returns the model_id
        string — pydantic_ai resolves it via its provider prefix.

        For openai_compatible (Ollama, vLLM, etc.): returns a configured
        OpenAIModel instance pointing at the custom base_url.
        """
        model_name = self._task_map.get(task_type)
        if not model_name:
            # Fall back to "fast" if no specific mapping exists
            model_name = "fast"

        entry = self._models[model_name]
        provider = entry.get("provider", "google")
        model_id = entry["model_id"]

        if provider == "openai_compatible":
            return self._build_openai_compatible(entry)

        # For google / openai / anthropic — pydantic_ai handles via model_id prefix
        return model_id

    def _build_openai_compatible(self, entry: dict) -> Any:
        """Build a pydantic_ai OpenAIModel for a custom OpenAI-compatible endpoint."""
        from openai import AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider

        client = AsyncOpenAI(
            base_url=entry["base_url"],
            api_key=entry.get("api_key", "local"),
        )
        return OpenAIModel(
            entry["model_id"],
            provider=OpenAIProvider(openai_client=client),
        )

    def model_id_for_task(self, task_type: str) -> str:
        """Return the raw model_id string (useful for logging)."""
        model_name = self._task_map.get(task_type, "fast")
        return self._models[model_name]["model_id"]

    def available_tasks(self) -> dict[str, str]:
        """Return {task_type: model_id} for all registered mappings."""
        return {task: self._models[name]["model_id"] for task, name in self._task_map.items()}
