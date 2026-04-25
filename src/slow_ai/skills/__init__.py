from pathlib import Path

import yaml


# Sections written into and parsed from a SKILL.md body
_BODY_SECTIONS = {
    "## When to use":       "when_to_use",       # str
    "## How to execute":    "how_to_execute",     # list[str]
    "## Output contract":   "output_contract",    # str
    "## Quality bar":       "quality_bar",        # list[str]
    "## Pairs well with":   "pairs_with",         # list[str]
}
_LIST_FIELDS = {"how_to_execute", "quality_bar", "pairs_with"}


class SkillRegistry:
    """
    Loads skills from catalog/{skill_name}/SKILL.md — the Anthropic Agent Skills
    standard format. Each skill directory contains a SKILL.md with YAML frontmatter
    (name, description, tools, source, tags) and a structured markdown body
    (When to use, How to execute, Output contract, Quality bar, Pairs well with).

    Synthesized skills are written as new SKILL.md directories immediately on add,
    so they are available to all future runs without a separate save() call.
    """

    def __init__(self, catalog_dir: Path | None = None):
        self._catalog = catalog_dir or Path(__file__).parent / "catalog"
        self._skills: dict[str, dict] = {}
        self._load_catalog()

    # ── Loading ───────────────────────────────────────────────────────────────

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
            if not isinstance(frontmatter, dict):
                return None
            frontmatter.setdefault("tools", [])
            frontmatter.setdefault("source", "synthesized")
            frontmatter.setdefault("tags", [])
            body = parts[2].strip()
            if body:
                frontmatter.update(self._parse_body(body))
            return frontmatter
        except yaml.YAMLError:
            return None

    def _parse_body(self, body: str) -> dict:
        """Extract structured sections from the SKILL.md markdown body."""
        result: dict = {}
        current_key: str | None = None
        buf: list[str] = []

        def flush() -> None:
            if current_key is None or not buf:
                return
            text = "\n".join(buf).strip()
            if current_key in _LIST_FIELDS:
                items = [
                    ln.lstrip("-•0123456789. \t").strip()
                    for ln in text.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
                result[current_key] = [i for i in items if i]
            else:
                result[current_key] = text

        for line in body.splitlines():
            if line in _BODY_SECTIONS:
                flush()
                buf = []
                current_key = _BODY_SECTIONS[line]
            elif current_key is not None:
                buf.append(line)
        flush()
        return result

    # ── Writing ───────────────────────────────────────────────────────────────

    def _write_skill_md(self, skill: dict) -> None:
        dir_name = skill["name"].replace(" ", "_")
        skill_dir = self._catalog / dir_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        frontmatter = {
            "name":        skill["name"],
            "description": skill.get("description", ""),
            "tools":       skill.get("tools", []),
            "source":      skill.get("source", "synthesized"),
            "tags":        skill.get("tags", []),
        }
        content = f"---\n{yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)}---\n"

        if skill.get("when_to_use"):
            content += f"\n## When to use\n{skill['when_to_use']}\n"

        if skill.get("how_to_execute"):
            steps = "\n".join(
                f"{i + 1}. {s}" for i, s in enumerate(skill["how_to_execute"])
            )
            content += f"\n## How to execute\n{steps}\n"

        if skill.get("output_contract"):
            content += f"\n## Output contract\n{skill['output_contract']}\n"

        if skill.get("quality_bar"):
            criteria = "\n".join(f"- {c}" for c in skill["quality_bar"])
            content += f"\n## Quality bar\n{criteria}\n"

        if skill.get("pairs_with"):
            pairs = "\n".join(f"- {p}" for p in skill["pairs_with"])
            content += f"\n## Pairs well with\n{pairs}\n"

        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    # ── Query API ─────────────────────────────────────────────────────────────

    def available_names(self) -> list[str]:
        return list(self._skills.keys())

    def has(self, skill_name: str) -> bool:
        return skill_name in self._skills

    def tools_for(self, skill_name: str) -> list[str]:
        return self._skills.get(skill_name, {}).get("tools", [])

    def tools_for_skills(self, skill_names: list[str]) -> list[str]:
        tools: set[str] = set()
        for name in skill_names:
            tools.update(self.tools_for(name))
        return sorted(tools)

    def descriptions_for_prompt(self) -> str:
        """One-liner per skill — used by the context planner."""
        return "\n".join(
            f"- {name}: {skill['description']}"
            for name, skill in self._skills.items()
        )

    def instructions_for_skills(self, skill_names: list[str]) -> str:
        """
        Return compiled playbook text for a list of skills.
        Only skills that have body content are included — skills with nothing
        beyond a description are silently skipped.
        """
        sections: list[str] = []
        for name in skill_names:
            skill = self._skills.get(name)
            if not skill:
                continue
            # Skip skills with no body content — just a description
            has_body = any(
                skill.get(k)
                for k in ("when_to_use", "how_to_execute", "output_contract",
                          "quality_bar", "pairs_with")
            )
            if not has_body:
                continue

            lines = [f"### {name}", skill.get("description", "")]

            if skill.get("when_to_use"):
                lines += ["", "**When to use**", skill["when_to_use"]]

            if skill.get("how_to_execute"):
                steps = "\n".join(
                    f"{i + 1}. {s}"
                    for i, s in enumerate(skill["how_to_execute"])
                )
                lines += ["", "**How to execute**", steps]

            if skill.get("output_contract"):
                lines += ["", "**Output contract**", skill["output_contract"]]

            if skill.get("quality_bar"):
                criteria = "\n".join(f"- {c}" for c in skill["quality_bar"])
                lines += ["", "**Quality bar**", criteria]

            if skill.get("pairs_with"):
                lines += ["", "**Pairs well with**", ", ".join(skill["pairs_with"])]

            sections.append("\n".join(lines))

        return "\n\n---\n\n".join(sections)

    # ── Mutation ──────────────────────────────────────────────────────────────

    def add_skills(self, skills: list[dict]) -> None:
        for skill in skills:
            self._skills[skill["name"]] = skill
            self._write_skill_md(skill)

    def save(self) -> None:
        # No-op: skills are written to SKILL.md immediately in add_skills().
        # Kept for interface compatibility during transition.
        pass
