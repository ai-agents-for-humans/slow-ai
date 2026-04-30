import html as _html
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Cookie, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic_ai import BinaryContent

from slow_ai.agents.interviewer import interviewer
from slow_ai.models import ProblemBrief

router = APIRouter()
_templates = Jinja2Templates(directory=Path(__file__).parents[1] / "templates")

_sessions: dict[str, dict] = {}


def _get_or_create_session(session_id: str | None) -> tuple[str, dict]:
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]
    sid = str(uuid.uuid4())
    _sessions[sid] = {"history": [], "brief": None}
    return sid, _sessions[sid]


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
    message: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
    session_id: str | None = Cookie(default=None),
):
    sid, session = _get_or_create_session(session_id)

    prompt = await _build_prompt(message, files)
    result = await interviewer.run(prompt, message_history=session["history"])
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
