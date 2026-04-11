import json
from pathlib import Path


class SkillRegistry:
    def __init__(self):
        self._path = Path(__file__).parent / "registry.json"
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._skills = {s["name"]: s for s in data["skills"]}

    def available_names(self) -> list[str]:
        return list(self._skills.keys())

    def tools_for(self, skill_name: str) -> list[str]:
        """Return the tools that implement this skill."""
        return self._skills.get(skill_name, {}).get("tools", [])

    def tools_for_skills(self, skill_names: list[str]) -> list[str]:
        """Return the union of tools needed to satisfy a list of skills."""
        tools: set[str] = set()
        for name in skill_names:
            tools.update(self.tools_for(name))
        return sorted(tools)

    def descriptions_for_prompt(self) -> str:
        """Formatted for inclusion in LLM prompts."""
        return "\n".join(
            f"- {name}: {skill['description']}"
            for name, skill in self._skills.items()
        )

    def has(self, skill_name: str) -> bool:
        return skill_name in self._skills

    def add_skills(self, skills: list[dict]) -> None:
        """Add new skills to the in-memory registry."""
        for skill in skills:
            self._skills[skill["name"]] = skill

    def save(self) -> None:
        """Persist the current registry to registry.json."""
        data = {"skills": list(self._skills.values())}
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
