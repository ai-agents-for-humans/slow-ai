import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Cookie
from fastapi.responses import HTMLResponse

from .interview import _sessions

router = APIRouter()


@router.post("/api/brief/confirm", response_class=HTMLResponse)
async def brief_confirm(session_id: str | None = Cookie(default=None)):
    import logging

    log = logging.getLogger(__name__)
    log.warning(
        "brief/confirm: session_id=%s known_sessions=%s",
        session_id,
        list(_sessions.keys()),
    )

    if not session_id or session_id not in _sessions:
        return HTMLResponse(
            f"<p class='text-danger'>Session expired (id={session_id}). Start a new interview.</p>",
            status_code=400,
        )

    session = _sessions[session_id]
    brief = session.get("brief")
    log.warning("brief/confirm: brief=%s", brief)
    if brief is None:
        return HTMLResponse(
            "<p class='text-danger'>No brief in session yet — keep chatting.</p>",
            status_code=400,
        )

    project_id = str(uuid.uuid4())
    project_dir = Path("output") / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    brief_data = brief.model_dump()
    (project_dir / "problem_brief.json").write_text(
        json.dumps(brief_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Store project_id in session for graph review
    session["project_id"] = project_id

    response = HTMLResponse(content="", status_code=200)
    response.headers["HX-Redirect"] = f"/graph/{project_id}"
    return response
