import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from slow_ai.agents.orchestrator import run_context_planner, run_graph_editor
from slow_ai.models import ContextGraph, ProblemBrief

router = APIRouter()
_templates = Jinja2Templates(directory=Path(__file__).parents[1] / "templates")

# In-memory graph sessions: project_id -> ContextGraph
_graph_sessions: dict[str, ContextGraph] = {}


def _graph_for_cytoscape(graph: ContextGraph) -> list[dict]:
    """Convert ContextGraph to Cytoscape elements array."""
    elements = []
    for phase in graph.phases:
        elements.append(
            {
                "data": {
                    "id": phase.id,
                    "label": phase.name,
                    "node_type": "phase",
                    "description": phase.purpose,
                },
                "classes": "phase-node",
            }
        )
        for wi in phase.work_items:
            elements.append(
                {
                    "data": {
                        "id": wi.id,
                        "label": wi.name,
                        "node_type": "work_item",
                        "description": wi.description,
                        "parent_phase": phase.id,
                        "skills": ", ".join(wi.required_skills),
                    },
                    "classes": "work-item-node",
                }
            )
            elements.append(
                {
                    "data": {
                        "source": wi.id,
                        "target": phase.id,
                        "edge_type": "belongs_to",
                    },
                    "classes": "belongs-edge",
                }
            )
        for dep in phase.depends_on_phases:
            elements.append(
                {
                    "data": {
                        "source": dep,
                        "target": phase.id,
                        "edge_type": "phase_depends",
                    },
                    "classes": "depends-edge",
                }
            )
    return elements


def _load_brief(project_id: str) -> ProblemBrief | None:
    brief_path = Path("output") / project_id / "problem_brief.json"
    if not brief_path.exists():
        return None
    return ProblemBrief.model_validate_json(brief_path.read_text(encoding="utf-8"))


def _save_graph(project_id: str, graph: ContextGraph) -> None:
    path = Path("output") / project_id / "context_graph.json"
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")


def _load_graph(project_id: str) -> ContextGraph | None:
    path = Path("output") / project_id / "context_graph.json"
    if not path.exists():
        return None
    try:
        return ContextGraph.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/graph/{project_id}", response_class=HTMLResponse)
async def graph_review_page(request: Request, project_id: str):
    brief = _load_brief(project_id)
    if brief is None:
        return HTMLResponse("Project not found", status_code=404)
    return _templates.TemplateResponse(
        "views/graph_review.html",
        {"request": request, "project_id": project_id, "brief": brief},
    )


@router.get("/api/graph/{project_id}")
async def get_graph(project_id: str):
    """Generate or load the context graph. Called via htmx on page load."""
    brief = _load_brief(project_id)
    if brief is None:
        return JSONResponse({"error": "Project not found"}, status_code=404)

    # Return cached graph if already generated this session
    if project_id in _graph_sessions:
        graph = _graph_sessions[project_id]
    else:
        # Check disk
        graph = _load_graph(project_id)
        if graph is None:
            run_id = str(uuid.uuid4())
            graph = await run_context_planner(brief, run_id)
            _save_graph(project_id, graph)
        _graph_sessions[project_id] = graph

    return {
        "goal": graph.goal,
        "elements": _graph_for_cytoscape(graph),
        "phase_count": len(graph.phases),
        "item_count": sum(len(p.work_items) for p in graph.phases),
    }


@router.post("/api/graph/{project_id}", response_class=HTMLResponse)
async def refine_graph(request: Request, project_id: str, message: str = Form(...)):
    """Refine the context graph based on user feedback, return agent bubble HTML."""
    brief = _load_brief(project_id)
    if brief is None:
        return HTMLResponse("<p class='text-danger'>Project not found.</p>", status_code=404)

    current_graph = _graph_sessions.get(project_id) or _load_graph(project_id)
    if current_graph is None:
        return HTMLResponse(
            "<p class='text-danger'>No graph yet — refresh the page.</p>",
            status_code=400,
        )

    run_id = str(uuid.uuid4())
    updated = await run_graph_editor(brief, current_graph, message, run_id)
    _graph_sessions[project_id] = updated
    _save_graph(project_id, updated)

    phase_count = len(updated.phases)
    item_count = sum(len(p.work_items) for p in updated.phases)
    reply = f"Updated — {phase_count} phases, {item_count} work items. The graph on the left has been refreshed."

    return _templates.TemplateResponse(
        "partials/graph_agent_reply.html",
        {"request": request, "message": reply},
    )
