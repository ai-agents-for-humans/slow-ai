import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from .interview import _sessions, _save_session

router = APIRouter()


@router.post("/api/brief/confirm", response_class=HTMLResponse)
async def brief_confirm(session_id: str = Form(...)):
    if not session_id or session_id not in _sessions:
        return HTMLResponse(
            "<p class='text-danger'>Session expired. Start a new interview.</p>",
            status_code=400,
        )

    session = _sessions[session_id]
    brief = session.get("brief")
    if brief is None:
        return HTMLResponse(
            "<p class='text-danger'>No brief in session yet — keep chatting.</p>",
            status_code=400,
        )
        return HTMLResponse(
            "<p class='text-danger'>No brief in session yet — keep chatting.</p>",
            status_code=400,
        )

    project_id = str(uuid.uuid4())
    project_dir = Path("output") / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "problem_brief.json").write_text(
        json.dumps(brief.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    draft_graph = session.get("draft_graph")
    if draft_graph is not None:
        (project_dir / "context_graph.json").write_text(
            draft_graph.model_dump_json(indent=2), encoding="utf-8"
        )

    session["project_id"] = project_id
    session["status"] = "confirmed"
    _save_session(session_id, session)

    confirmation_html = (
        '<div class="d-flex mb-3">'
        '<div class="chat-bubble-agent">'
        '<div class="fw-semibold mb-1">Brief confirmed.</div>'
        '<div class="text-muted" style="font-size:0.85rem;">'
        'Your context graph is ready. Launch the agent swarm from the panel on the right.'
        '</div>'
        '</div>'
        '</div>'
    )
    return HTMLResponse(content=confirmation_html)
