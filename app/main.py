from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import brief, graph, interview, projects, runs
from .api.interview import load_all_sessions

app = FastAPI(title="Slow AI")


@app.on_event("startup")
async def startup():
    from slow_ai.logging_config import setup_logging
    from slow_ai.observability import setup_llm_logging

    setup_logging(log_file=Path("app.log"))
    setup_llm_logging()
    load_all_sessions()


# Static files and templates
_base = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_base / "static"), name="static")
templates = Jinja2Templates(directory=_base / "templates")

# Routers
app.include_router(projects.router)
app.include_router(interview.router)
app.include_router(brief.router)
app.include_router(graph.router)
app.include_router(runs.router)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "views/home.html")
