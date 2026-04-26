import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git import Actor, Repo

_LIVE_DIR = "live"

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

    # ── Live files (not committed, read by UI while run is in progress) ───────

    def write_live(self, filename: str, content) -> None:
        """Write a live state file to runs/{run_id}/live/. Not committed to git."""
        live_dir = self.run_path / _LIVE_DIR
        live_dir.mkdir(exist_ok=True)
        data = (
            json.dumps(content, default=str)
            if isinstance(content, (dict, list))
            else str(content)
        )
        (live_dir / filename).write_text(data, encoding="utf-8")

    def read_live(self, filename: str, default=None):
        """Read a live state file. Returns parsed JSON, or default if missing."""
        path = self.run_path / _LIVE_DIR / filename
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def append_live_log(self, msg: str) -> None:
        """Append a message line to the live log."""
        live_dir = self.run_path / _LIVE_DIR
        live_dir.mkdir(exist_ok=True)
        with (live_dir / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"msg": msg}) + "\n")

    def append_conversation(self, role: str, content: str) -> None:
        """Append one turn to the post-run conversation log."""
        live_dir = self.run_path / _LIVE_DIR
        live_dir.mkdir(exist_ok=True)
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with (live_dir / "conversation.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def read_conversation(self) -> list[dict]:
        """Return all conversation turns as {role, content, timestamp} dicts."""
        path = self.run_path / _LIVE_DIR / "conversation.jsonl"
        if not path.exists():
            return []
        messages = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return messages

    def commit_document(self, document: str) -> str:
        """Write and commit the final research report as final_report.md."""
        full_path = self.run_path / "final_report.md"
        full_path.write_text(document, encoding="utf-8")
        return self._commit("[M-final-document] research report", ["final_report.md"])

    def read_live_log(self) -> list[str]:
        """Return all live log messages in order."""
        path = self.run_path / _LIVE_DIR / "log.jsonl"
        if not path.exists():
            return []
        try:
            return [
                json.loads(line)["msg"]
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (json.JSONDecodeError, OSError):
            return []
