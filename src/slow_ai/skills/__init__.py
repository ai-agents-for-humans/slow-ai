from pathlib import Path

import yaml


class SkillRegistry:
    """
    Loads skills from catalog/{skill_name}/SKILL.md — the Anthropic Agent Skills
    standard format. Each skill directory contains a SKILL.md with YAML frontmatter
    (name, description, tools, source, tags) and an optional markdown body.

    Synthesized skills are written as new SKILL.md directories immediately on add,
    so they are available to all future runs without a separate save() call.
    """

    def __init__(self, catalog_dir: Path | None = None):
        self._catalog = catalog_dir or Path(__file__).parent / "catalog"
        self._skills: dict[str, dict] = {}
        self._load_catalog()

    def _load_catalog(self) -> None:
        if not self._catalog.exists():
            return
        for skill_dir in sorted(self._catalog.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if skill_dir.is_dir() and skill_md.exists():
                skill = self._parse_skill_md(skill_md)
                if skill and "name" in skill:
                    self._skills[skill["name"]] = skill

    def _parse_skill_md(self, path: Path) -> dict | None:
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
        try:
            frontmatter = yaml.safe_load(parts[1])
            if isinstance(frontmatter, dict):
                frontmatter.setdefault("tools", [])
                frontmatter.setdefault("source", "synthesized")
                frontmatter.setdefault("tags", [])
                return frontmatter
        except yaml.YAMLError:
            return None
        return None

    def _write_skill_md(self, skill: dict) -> None:
        dir_name = skill["name"].replace(" ", "_")
        skill_dir = self._catalog / dir_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = {
            "name": skill["name"],
            "description": skill.get("description", ""),
            "tools": skill.get("tools", []),
            "source": skill.get("source", "synthesized"),
            "tags": skill.get("tags", []),
        }
        content = f"---\n{yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)}---\n"
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    def available_names(self) -> list[str]:
        return list(self._skills.keys())

    def tools_for(self, skill_name: str) -> list[str]:
        return self._skills.get(skill_name, {}).get("tools", [])

    def tools_for_skills(self, skill_names: list[str]) -> list[str]:
        tools: set[str] = set()
        for name in skill_names:
            tools.update(self.tools_for(name))
        return sorted(tools)

    def descriptions_for_prompt(self) -> str:
        return "\n".join(
            f"- {name}: {skill['description']}"
            for name, skill in self._skills.items()
        )

    def has(self, skill_name: str) -> bool:
        return skill_name in self._skills

    def add_skills(self, skills: list[dict]) -> None:
        for skill in skills:
            self._skills[skill["name"]] = skill
            self._write_skill_md(skill)

    def save(self) -> None:
        # No-op: skills are written to SKILL.md immediately in add_skills().
        # Kept for interface compatibility during transition.
        pass
