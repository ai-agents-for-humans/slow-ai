from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import brief, graph, interview, projects, runs

app = FastAPI(title="Slow AI")

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
    return templates.TemplateResponse("views/home.html", {"request": request})
