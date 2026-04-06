import json
import os
import uuid

from pydantic_ai import Agent

from slow_ai.config import settings
from slow_ai.execution.registry import AgentRegistry
from slow_ai.models import (
    AgentContext,
    AgentMemory,
    AgentTask,
    ContextGraph,
    ProblemBrief,
    ResearchPlan,
    SpawnRequest,
)

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

# ── Context planner ───────────────────────────────────────────────────────────

_CONTEXT_PLANNER_PROMPT = """
You are a research planner. Given a problem brief, decompose the goal into a directed
graph of work items — a blueprint of everything that needs to happen for the goal to
be considered complete.

Guidelines:
- Create 3-8 work items depending on scope (fewer for narrow goals, more for broad ones)
- Each work item should be atomic enough for a single specialist agent to address
- Give each item a short, clear name (5-10 words) and a description of what research
  needs to happen
- List 1-3 concrete success criteria per item (what "done" looks like)
- Add dependency edges where one item's findings are genuinely required before another
  can proceed: edge source depends on edge target
- Assign ids as "wi-1", "wi-2", etc.
- The depends_on field on each WorkItem should mirror the edges

Return a ContextGraph.
"""

_context_planner = Agent(
    model="google-gla:gemini-3-flash-preview",
    output_type=ContextGraph,
    system_prompt=_CONTEXT_PLANNER_PROMPT,
)


async def run_context_planner(brief: ProblemBrief, run_id: str) -> ContextGraph:
    result = await _context_planner.run(
        f"Run ID: {run_id}\n\nProblem brief:\n{json.dumps(brief.model_dump(), indent=2)}"
    )
    graph: ContextGraph = result.output
    graph.goal = brief.goal
    # Rebuild edges from depends_on so the two representations stay consistent
    edges = []
    for node in graph.nodes:
        for dep_id in node.depends_on:
            edges.append({"source": node.id, "target": dep_id})
    graph.edges = edges
    return graph


# ── Orchestrator ──────────────────────────────────────────────────────────────

# TODO: replace this static prompt with an LLM-generated one derived from the
# project brief — the brief's domain, constraints and milestone_flags should
# drive which specialist types are selected and how budgets are allocated.
_SYSTEM_PROMPT = """
You are a research orchestrator for earth observation data.

You will receive a problem brief and a context graph of work items. Your job is to
produce a ResearchPlan that assigns specialist agents to cover those work items.

Always consider these specialist types for earth observation:
- copernicus_specialist: Sentinel-2, Sentinel-1 SAR, ESA Open Access Hub, free optical data
- nasa_earthdata_specialist: MODIS, Landsat, SRTM, NASA CMR search API
- google_earth_engine_specialist: GEE data catalogue, cloud-based processing, STAC APIs
- open_data_specialist: national agencies, data.gov, OpenAfrica, RCMRD, regional portals

For each specialist:
- Set work_item_id to the id of the work item from the context graph this specialist
  will address (e.g. "wi-1"). Each work item should have at least one specialist.
- Assign a specific task based on brief constraints (region, time range, resolution)
- Set evidence_required: what proof they must return (sources_checked, datasets_found,
  coverage_pct, license, resolution, format, download_url)
- Set context_budget based on task complexity:
  - Single country, single time range: 6000 tokens
  - Multiple countries or long time range: 4000 tokens (expect decomposition)
  - Broad survey: 3000 tokens (will need workers)

Return run_id and milestone_flags from the brief.
"""

_orchestrator = Agent(
    model="google-gla:gemini-3-flash-preview",
    output_type=ResearchPlan,
    system_prompt=_SYSTEM_PROMPT,
)


async def run_orchestrator(
    brief: ProblemBrief, context_graph: ContextGraph, run_id: str
) -> ResearchPlan:
    result = await _orchestrator.run(
        f"Run ID: {run_id}\n\n"
        f"Problem brief:\n{json.dumps(brief.model_dump(), indent=2)}\n\n"
        f"Context graph (work items to address):\n"
        f"{json.dumps(context_graph.model_dump(), indent=2)}"
    )
    plan: ResearchPlan = result.output
    plan.run_id = run_id
    plan.context_graph = context_graph

    for ctx in plan.specialists:
        task_id = f"task-{uuid.uuid4().hex[:6]}"
        agent_id = f"{ctx.role.replace(' ', '_').lower()}-{uuid.uuid4().hex[:6]}"
        ctx.agent_id = agent_id
        ctx.task = AgentTask(
            task_id=task_id,
            parent_task_id=None,
            agent_type=ctx.role,
            goal=ctx.task.goal if isinstance(ctx.task, AgentTask) else str(ctx.task),
            context_budget=ctx.memory.context_budget if ctx.memory else 8000,
        )
        ctx.memory = AgentMemory(
            agent_id=agent_id,
            agent_type=ctx.role,
            context_budget=ctx.task.context_budget,
        )

    return plan


async def handle_spawn_request(
    request: SpawnRequest,
    registry: AgentRegistry,
) -> AgentContext:
    """
    Called when an agent requests a worker mid-execution.
    Registers the worker in the registry and returns its context.
    """
    task_id = f"task-{uuid.uuid4().hex[:6]}"
    reg = registry.register(
        agent_type=request.agent_type,
        parent_agent_id=request.requested_by,
        task_id=task_id,
    )
    task = AgentTask(
        task_id=task_id,
        parent_task_id=request.requested_by,
        agent_type=request.agent_type,
        goal=request.goal,
        context_budget=request.context_budget,
    )
    memory = AgentMemory(
        agent_id=reg.agent_id,
        agent_type=request.agent_type,
        context_budget=request.context_budget,
    )
    return AgentContext(
        agent_id=reg.agent_id,
        role=request.agent_type,
        expertise=[],
        task=task,
        memory=memory,
        constraints={},
        tools_available=request.tools,
        evidence_required={},
    )
