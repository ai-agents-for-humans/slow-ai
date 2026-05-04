import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_templates = Jinja2Templates(directory=Path(__file__).parents[1] / "templates")

router = APIRouter()

_STATUS_LABEL = {
    "completed": "completed",
    "failed": "failed",
    "running": "running",
    "initializing": "running",
    "waiting_for_human": "waiting",
    "blocked_on_capabilities": "blocked",
}

_STATUS_BADGE = {
    "completed": "success",
    "failed": "danger",
    "running": "primary",
    "waiting": "warning",
    "blocked": "warning",
    "unknown": "secondary",
}


def _run_status(run_id: str) -> str:
    status_path = Path("runs") / run_id / "live" / "status.json"
    if not status_path.exists():
        return "unknown"
    try:
        return _STATUS_LABEL.get(json.loads(status_path.read_text())["status"], "unknown")
    except Exception:
        return "unknown"


def _project_goal(project_id: str) -> str:
    brief_path = Path("output") / project_id / "problem_brief.json"
    if not brief_path.exists():
        return "Untitled project"
    try:
        data = json.loads(brief_path.read_text())
        return data.get("goal", "Untitled project")
    except Exception:
        return "Untitled project"


def _project_runs(project_id: str) -> list[dict]:
    runs_file = Path("output") / project_id / "runs.jsonl"
    if not runs_file.exists():
        return []
    runs = []
    for line in runs_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            status = _run_status(entry["run_id"])
            runs.append(
                {
                    "run_id": entry["run_id"],
                    "started_at": entry.get("started_at", "")[:16].replace("T", " "),
                    "status": status,
                    "badge": _STATUS_BADGE.get(status, "secondary"),
                }
            )
        except Exception:
            continue
    return list(reversed(runs))


def _all_projects() -> list[dict]:
    output_dir = Path("output")
    if not output_dir.exists():
        return []
    projects = []
    for brief_path in sorted(output_dir.glob("*/problem_brief.json"), reverse=True):
        project_id = brief_path.parent.name
        projects.append(
            {
                "project_id": project_id,
                "goal": _project_goal(project_id),
                "runs": _project_runs(project_id),
            }
        )
    return projects


def _all_interviews() -> list[dict]:
    interviews_dir = Path("output") / "interviews"
    if not interviews_dir.exists():
        return []
    interviews = []
    for session_file in sorted(
        interviews_dir.glob("*/session.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        try:
            meta = json.loads(session_file.read_text(encoding="utf-8"))
            if meta.get("status") == "confirmed":
                continue
            if meta.get("project_id"):
                continue
            interviews.append({
                "session_id": meta["session_id"],
                "created_at": meta.get("created_at", "")[:16].replace("T", " "),
                "preview": meta.get("preview", ""),
            })
        except Exception:
            continue
    return interviews


@router.get("/api/projects")
def list_projects_json():
    return _all_projects()


@router.get("/api/projects-html", response_class=HTMLResponse)
def list_projects_html(request: Request):
    return _templates.TemplateResponse(
        "partials/sidebar_projects.html",
        {
            "request": request,
            "projects": _all_projects(),
            "interviews": _all_interviews(),
        },
    )
