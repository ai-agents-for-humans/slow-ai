import html as _html
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessagesTypeAdapter

from slow_ai.agents.interviewer import interviewer
from slow_ai.models import ContextGraph, ProblemBrief

router = APIRouter()
_templates = Jinja2Templates(directory=Path(__file__).parents[1] / "templates")

_sessions: dict[str, dict] = {}
_INTERVIEWS_DIR = Path("output") / "interviews"


def _session_dir(sid: str) -> Path:
    return _INTERVIEWS_DIR / sid


def _save_session(sid: str, session: dict) -> None:
    d = _session_dir(sid)
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "session_id": sid,
        "created_at": session.get("created_at", datetime.now(timezone.utc).isoformat()),
        "status": session.get("status", "interviewing"),
        "brief": session["brief"].model_dump() if session.get("brief") else None,
        "project_id": session.get("project_id"),
        "preview": session.get("preview", ""),
    }
    (d / "session.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if session.get("history"):
        try:
            (d / "messages.json").write_bytes(
                ModelMessagesTypeAdapter.dump_json(session["history"])
            )
        except Exception:
            pass
    if session.get("conversation_log"):
        (d / "conversation_log.json").write_text(
            json.dumps(session["conversation_log"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_all_sessions() -> None:
    if not _INTERVIEWS_DIR.exists():
        return
    for session_file in _INTERVIEWS_DIR.glob("*/session.json"):
        try:
            meta = json.loads(session_file.read_text(encoding="utf-8"))
            sid = meta["session_id"]
            if sid in _sessions:
                continue
            history = []
            messages_file = session_file.parent / "messages.json"
            if messages_file.exists():
                try:
                    history = ModelMessagesTypeAdapter.validate_json(messages_file.read_bytes())
                except Exception:
                    pass
            log = []
            log_file = session_file.parent / "conversation_log.json"
            if log_file.exists():
                try:
                    log = json.loads(log_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            brief = ProblemBrief.model_validate(meta["brief"]) if meta.get("brief") else None
            draft_graph = None
            graph_file = session_file.parent / "draft_graph.json"
            if graph_file.exists():
                try:
                    draft_graph = ContextGraph.model_validate_json(
                        graph_file.read_text(encoding="utf-8")
                    )
                except Exception:
                    pass
            _sessions[sid] = {
                "history": history,
                "brief": brief,
                "draft_graph": draft_graph,
                "project_id": meta.get("project_id"),
                "status": meta.get("status", "interviewing"),
                "created_at": meta.get("created_at", ""),
                "preview": meta.get("preview", ""),
                "conversation_log": log,
            }
        except Exception:
            continue


def _make_session(sid: str) -> dict:
    return {
        "history": [],
        "brief": None,
        "draft_graph": None,
        "project_id": None,
        "status": "interviewing",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preview": "",
        "conversation_log": [],
    }


def _bubble(role: str, content: str) -> str:
    """Render a single chat bubble as HTML."""

    if role == "agent":
        escaped = _html.escape(content, quote=True)
        return (
            f'<div class="d-flex mb-3">'
            f'<div class="chat-bubble-agent" data-markdown="{escaped}"></div>'
            f"</div>"
        )
    escaped = _html.escape(content)
    return (
        f'<div class="d-flex mb-3 justify-content-end">'
        f'<div class="chat-bubble-user">{escaped}</div>'
        f"</div>"
    )


def _render_history_html(request: Request, session: dict, sid: str) -> str:
    parts = []
    for entry in session.get("conversation_log", []):
        parts.append(_bubble(entry["role"], entry["text"]))
    if session.get("brief") and not session.get("project_id"):
        partial = _templates.TemplateResponse(
            "partials/brief_ready.html",
            {"request": request, "brief": session["brief"], "session_id": sid},
        ).body.decode()
        parts.append(partial)
    return "".join(parts)


def _read_pdf(data: bytes, name: str) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    return f"[PDF: {name}]\n" + "\n\n".join(pages).strip()


def _read_csv(data: bytes, name: str) -> str:
    import pandas as pd

    df = pd.read_csv(io.BytesIO(data))
    summary = (
        f"Rows: {len(df)}, Columns: {list(df.columns)}\n"
        f"Sample (first 5 rows):\n{df.head().to_string()}"
    )
    return f"[CSV: {name}]\n{summary}"


def _read_docx(data: bytes, name: str) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return f"[DOCX: {name}]\n{text}"


async def _build_prompt(message: str, files: list[UploadFile]):
    text_parts: list[str] = []
    binary_parts: list[BinaryContent] = []

    for f in files:
        data = await f.read()
        name = f.filename or "upload"
        ct = f.content_type or ""

        if ct.startswith("image/"):
            binary_parts.append(BinaryContent(data=data, media_type=ct))
        elif ct == "application/pdf" or name.lower().endswith(".pdf"):
            text_parts.append(_read_pdf(data, name))
        elif ct in ("text/csv", "application/csv") or name.lower().endswith(".csv"):
            text_parts.append(_read_csv(data, name))
        elif name.lower().endswith(".docx"):
            text_parts.append(_read_docx(data, name))
        else:
            try:
                text_parts.append(
                    f"[File: {name}]\n{data.decode('utf-8', errors='replace')[:4000]}"
                )
            except Exception:
                pass

    user_text = message or "(User attached file(s) — no additional text)"
    if text_parts:
        ctx = "\n\n---\n\n".join(text_parts)
        user_text = f"[Uploaded context]\n{ctx}\n\n[User message]\n{user_text}"

    if binary_parts:
        return [user_text, *binary_parts]
    return user_text


def _conversation_text_for_graph(session: dict) -> str:
    log = session.get("conversation_log", [])
    return "\n".join(
        f"{e['role'].upper()}: {e['text'][:400]}" for e in log[-20:]
    )


async def _rebuild_draft_graph(sid: str, session: dict) -> None:
    from slow_ai.agents.orchestrator import run_draft_context_graph
    log = session.get("conversation_log", [])
    if len(log) < 3:
        return
    text = _conversation_text_for_graph(session)
    graph = await run_draft_context_graph(text)
    if graph:
        session["draft_graph"] = graph
        d = _session_dir(sid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "draft_graph.json").write_text(
            graph.model_dump_json(indent=2), encoding="utf-8"
        )


def _graph_for_cytoscape(graph: ContextGraph) -> list[dict]:
    elements = []
    for phase in graph.phases:
        elements.append({
            "data": {
                "id": phase.id,
                "label": phase.name,
                "node_type": "phase",
                "description": phase.purpose,
            },
            "classes": "phase-node",
        })
        for wi in phase.work_items:
            elements.append({
                "data": {
                    "id": wi.id,
                    "label": wi.name,
                    "node_type": "work_item",
                    "description": wi.description,
                    "parent_phase": phase.id,
                    "skills": ", ".join(wi.required_skills),
                },
                "classes": "work-item-node",
            })
            elements.append({
                "data": {
                    "source": wi.id,
                    "target": phase.id,
                    "edge_type": "belongs_to",
                },
                "classes": "belongs-edge",
            })
        for dep in phase.depends_on_phases:
            elements.append({
                "data": {
                    "source": dep,
                    "target": phase.id,
                    "edge_type": "phase_depends",
                },
                "classes": "depends-edge",
            })
    return elements


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/interview", response_class=HTMLResponse)
async def interview_new():
    """Create a new interview session and redirect to it."""
    sid = str(uuid.uuid4())
    session = _make_session(sid)
    _sessions[sid] = session
    _save_session(sid, session)
    return RedirectResponse(url=f"/interview/{sid}", status_code=303)


@router.get("/interview/{session_id}", response_class=HTMLResponse)
async def interview_page(request: Request, session_id: str):
    session = _sessions.get(session_id)
    if session is None:
        return RedirectResponse(url="/interview", status_code=303)
    if session.get("project_id"):
        return RedirectResponse(url=f"/graph/{session['project_id']}", status_code=303)

    has_history = bool(session.get("conversation_log"))
    history_html = _render_history_html(request, session, session_id) if has_history else ""

    return _templates.TemplateResponse(
        "views/interview.html",
        {
            "request": request,
            "session_id": session_id,
            "has_history": has_history,
            "history_html": history_html,
        },
    )


@router.post("/api/interview/{session_id}/start", response_class=HTMLResponse)
async def interview_start(
    request: Request,
    session_id: str,
    background_tasks: BackgroundTasks,
):
    session = _sessions.get(session_id)
    if session is None:
        return HTMLResponse("<p class='text-danger'>Session not found.</p>", status_code=404)

    result = await interviewer.run("Hello, I'm ready to start.", message_history=session["history"])
    session["history"] = result.all_messages()
    response_text = result.output if isinstance(result.output, str) else str(result.output)

    session["conversation_log"].append({"role": "agent", "text": response_text})
    session["preview"] = response_text[:80]
    background_tasks.add_task(_save_session, session_id, session)

    return HTMLResponse(content=_bubble("agent", response_text))


@router.post("/api/interview/{session_id}/message", response_class=HTMLResponse)
async def interview_message(
    request: Request,
    session_id: str,
    background_tasks: BackgroundTasks,
    message: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
):
    session = _sessions.get(session_id)
    if session is None:
        return HTMLResponse("<p class='text-danger'>Session not found.</p>", status_code=404)

    prompt = await _build_prompt(message, files)
    result = await interviewer.run(prompt, message_history=session["history"])
    session["history"] = result.all_messages()
    output = result.output

    user_text = message or "(file upload)"
    session["conversation_log"].append({"role": "user", "text": user_text})

    if isinstance(output, ProblemBrief):
        session["brief"] = output
        session["conversation_log"].append({"role": "agent", "text": "[Brief produced]"})
        agent_html = _templates.TemplateResponse(
            "partials/brief_ready.html",
            {"request": request, "brief": output, "session_id": session_id},
        ).body.decode()
        html = agent_html
    else:
        session["conversation_log"].append({"role": "agent", "text": output})
        session["preview"] = output[:80]
        html = _bubble("agent", output)

    background_tasks.add_task(_save_session, session_id, session)
    background_tasks.add_task(_rebuild_draft_graph, session_id, session)

    return HTMLResponse(content=html)


@router.get("/api/interview/{session_id}/draft-graph")
async def draft_graph(session_id: str):
    session = _sessions.get(session_id)
    if session is None:
        return {"elements": [], "phase_count": 0, "item_count": 0, "ready": False}

    graph = session.get("draft_graph")
    if graph is None:
        return {"elements": [], "phase_count": 0, "item_count": 0, "ready": False}

    return {
        "elements": _graph_for_cytoscape(graph),
        "phase_count": len(graph.phases),
        "item_count": sum(len(p.work_items) for p in graph.phases),
        "goal": graph.goal,
        "ready": True,
        "launch_ready": session.get("status") == "confirmed",
        "project_id": session.get("project_id"),
    }
