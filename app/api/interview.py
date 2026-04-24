import uuid
from pathlib import Path

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic_ai import messages as _pai_messages

from slow_ai.agents.interviewer import interviewer
from slow_ai.models import ProblemBrief

router = APIRouter()
_templates = Jinja2Templates(directory=Path(__file__).parents[1] / "templates")

# In-memory session store: session_id -> {history, brief}
_sessions: dict[str, dict] = {}


def _get_or_create_session(session_id: str | None) -> tuple[str, dict]:
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]
    sid = str(uuid.uuid4())
    _sessions[sid] = {"history": [], "brief": None}
    return sid, _sessions[sid]


def _bubble(role: str, content: str) -> str:
    """Render a single chat bubble as HTML."""
    import html as _html
    if role == "agent":
        # data-markdown lets the client render markdown safely
        escaped = _html.escape(content, quote=True)
        return (
            f'<div class="d-flex mb-3">'
            f'<div class="chat-bubble-agent" data-markdown="{escaped}"></div>'
            f'</div>'
        )
    escaped = _html.escape(content)
    return (
        f'<div class="d-flex mb-3 justify-content-end">'
        f'<div class="chat-bubble-user">{escaped}</div>'
        f'</div>'
    )


@router.get("/interview", response_class=HTMLResponse)
async def interview_page(request: Request):
    return _templates.TemplateResponse("views/interview.html", {"request": request})


@router.post("/api/interview/start", response_class=HTMLResponse)
async def interview_start(request: Request, session_id: str | None = Cookie(default=None)):
    sid, session = _get_or_create_session(session_id)

    result = await interviewer.run("Hello, I'm ready to start.", message_history=session["history"])
    session["history"] = result.all_messages()
    response_text = result.output if isinstance(result.output, str) else str(result.output)

    html = _bubble("agent", response_text)
    response = HTMLResponse(content=html)
    response.set_cookie("session_id", sid, httponly=True)
    return response


@router.post("/api/interview/message", response_class=HTMLResponse)
async def interview_message(
    request: Request,
    message: str = Form(...),
    session_id: str | None = Cookie(default=None),
):
    sid, session = _get_or_create_session(session_id)

    result = await interviewer.run(message, message_history=session["history"])
    session["history"] = result.all_messages()
    output = result.output

    if isinstance(output, ProblemBrief):
        session["brief"] = output
        agent_html = _templates.TemplateResponse(
            "partials/brief_ready.html",
            {"request": request, "brief": output},
        ).body.decode()
        html = agent_html
    else:
        html = _bubble("agent", output)

    response = HTMLResponse(content=html)
    response.set_cookie("session_id", sid, httponly=True)
    return response
