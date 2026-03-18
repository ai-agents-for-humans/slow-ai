import json
from pathlib import Path
from typing import Any

from git import Actor, Repo

AUTHOR = Actor("SlowAI", "slowai@local")


class GitStore:
    def __init__(self, run_id: str, base_path: Path = Path("runs")):
        self.run_id = run_id
        self.run_path = base_path / run_id
        self.run_path.mkdir(parents=True, exist_ok=True)
        self.repo = Repo.init(self.run_path)

    def _write(self, relative_path: str, content: Any) -> Path:
        """Write JSON content to a file inside the run repo."""
        full_path = self.run_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(
            json.dumps(content, indent=2, default=str), encoding="utf-8"
        )
        return full_path

    def _commit(self, message: str, paths: list[str]) -> str:
        """Stage specific files and commit. Returns commit sha."""
        self.repo.index.add(paths)
        commit = self.repo.index.commit(
            message, author=AUTHOR, committer=AUTHOR
        )
        return commit.hexsha

    def commit_brief(self, brief: dict) -> str:
        self._write("problem_brief.json", brief)
        return self._commit("[init] problem brief", ["problem_brief.json"])

    def commit_milestone(
        self,
        milestone: str,
        artefacts: dict[str, Any],   # relative_path → content
        registry_snapshot: dict | None = None,
    ) -> str:
        paths = []
        for rel_path, content in artefacts.items():
            self._write(rel_path, content)
            paths.append(rel_path)

        if registry_snapshot:
            self._write("registry.json", registry_snapshot)
            paths.append("registry.json")

        return self._commit(f"[{milestone}]", paths)

    def record_skipped_path(
        self, path_id: str, reason: str, triggered_by: str
    ) -> str:
        content = {
            "path_id": path_id,
            "reason": reason,
            "triggered_by": triggered_by,
        }
        rel = f"paths/not_taken/{path_id}.json"
        self._write(rel, content)
        return self._commit(f"[skipped] {path_id}", [rel])

    def get_log(self) -> list[dict]:
        return [
            {
                "sha": c.hexsha[:8],
                "message": c.message.strip(),
                "timestamp": c.committed_datetime.isoformat(),
            }
            for c in self.repo.iter_commits()
        ]
