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
    EvidenceEnvelope,
    OrchestratorDecision,
    ProblemBrief,
    ResearchPlan,
    SpawnRequest,
    WorkItem,
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

You will receive a problem brief, the full context graph, and a list of READY work
items — those whose upstream dependencies are already satisfied and can be worked on
now. Your job is to assign specialist agents only to the ready work items.

Do NOT assign specialists to work items that are not in the ready list — their
dependencies have not been met yet and they will be dispatched in a later wave.

Always consider these specialist types for earth observation:
- copernicus_specialist: Sentinel-2, Sentinel-1 SAR, ESA Open Access Hub, free optical data
- nasa_earthdata_specialist: MODIS, Landsat, SRTM, NASA CMR search API
- google_earth_engine_specialist: GEE data catalogue, cloud-based processing, STAC APIs
- open_data_specialist: national agencies, data.gov, OpenAfrica, RCMRD, regional portals

For each specialist:
- Set work_item_id to the id of one of the READY work items (e.g. "wi-1")
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
    brief: ProblemBrief,
    context_graph: ContextGraph,
    ready_work_items: list[WorkItem],
    run_id: str,
) -> ResearchPlan:
    ready_data = json.dumps([w.model_dump() for w in ready_work_items], indent=2)
    result = await _orchestrator.run(
        f"Run ID: {run_id}\n\n"
        f"Problem brief:\n{json.dumps(brief.model_dump(), indent=2)}\n\n"
        f"Full context graph:\n{json.dumps(context_graph.model_dump(), indent=2)}\n\n"
        f"READY work items (assign specialists only to these):\n{ready_data}"
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


_ASSESS_PROMPT = """
You are a research orchestrator assessing progress after a wave of specialist agents.

You receive:
1. The full context graph — the complete blueprint with all work items and dependencies
2. Evidence envelopes collected so far — what specialists have found and at what confidence
3. The original problem brief
4. READY work items — those whose dependencies are now satisfied and can be worked on next

Your job is to assess coverage of the work items worked so far and decide the next action.

Coverage rules (for items that have been worked):
- A work item is COVERED if at least one envelope maps to it with confidence >= 0.6
- A work item is PARTIAL if the best envelope confidence is 0.3–0.59
- A work item is UNCOVERED if no envelope exists for it, or best confidence < 0.3

Then decide:
- "synthesize": all work items across the entire context graph are covered (>= 0.6),
  OR no ready items remain and everything possible has been addressed.
- "spawn_specialists": there are ready work items that still need to be addressed.
  Provide next_wave with assignments ONLY for items in the READY list.
  Do not re-assign work items that are already covered.
- "escalate_to_human": a ready work item requires human judgement before it can proceed —
  ambiguous requirements, conflicting evidence, or decisions outside research scope.
  Document each escalation in escalation_notes.

IMPORTANT: Only include work_item_ids from the provided context graph in your lists.
Only assign next_wave specialists to items in the READY list.
Always include reasoning explaining your assessment.
"""

_assess_agent = Agent(
    model="google-gla:gemini-3-flash-preview",
    output_type=OrchestratorDecision,
    system_prompt=_ASSESS_PROMPT,
)


async def orchestrator_assess(
    brief: ProblemBrief,
    context_graph: ContextGraph,
    envelopes: list[EvidenceEnvelope],
    ready_work_items: list[WorkItem],
    run_id: str,
    wave: int,
) -> OrchestratorDecision:
    envelope_data = json.dumps([e.model_dump() for e in envelopes], indent=2)
    ready_data = json.dumps([w.model_dump() for w in ready_work_items], indent=2)
    result = await _assess_agent.run(
        f"Run ID: {run_id} | Wave: {wave}\n\n"
        f"Problem brief:\n{json.dumps(brief.model_dump(), indent=2)}\n\n"
        f"Full context graph:\n{json.dumps(context_graph.model_dump(), indent=2)}\n\n"
        f"Evidence envelopes collected so far:\n{envelope_data}\n\n"
        f"READY work items (unblocked, can be worked on now):\n{ready_data}"
    )
    decision: OrchestratorDecision = result.output
    decision.wave = wave
    return decision


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
