import json
import os
import uuid
from datetime import datetime, timezone

from pydantic_ai import Agent

from slow_ai.config import settings
from slow_ai.execution.registry import AgentRegistry
from slow_ai.llm import ModelRegistry
from slow_ai.models import (
    AgentContext,
    AgentMemory,
    AgentTask,
    ContextGraph,
    EvidenceEnvelope,
    OrchestratorDecision,
    Phase,
    PhaseSummary,
    ProblemBrief,
    ResearchPlan,
    SkillGap,
    ViabilityDecision,
    SpawnRequest,
    WorkItem,
)
from typing import Any

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

# ── Context planner ───────────────────────────────────────────────────────────

def _context_planner_prompt(skill_registry_description: str) -> str:
    return f"""
You are a work planner. Given a problem brief, decompose the goal into a structured
plan of phases — each phase containing parallel work items.

STRUCTURE:
- Design 2-5 phases in logical sequence (e.g. Explore → Investigate → Critique →
  Synthesise, or whatever fits the domain)
- Each phase has a clear purpose: what collectively needs to be true before the next
  phase can start
- Within each phase, all work items run in parallel — so they must be genuinely
  independent of each other
- Each work item is atomic enough for a single specialist agent to address

PHASE IDS: "phase-1", "phase-2", etc.
WORK ITEM IDS: "wi-{{phase_number}}-{{item_number}}" e.g. "wi-1-1", "wi-1-2", "wi-2-1"

PHASE FIELDS:
- id: "phase-1" etc.
- name: short descriptive name (e.g. "Landscape Scan", "Deep Investigation", "Quality Critique")
- purpose: 1-2 sentences on what this phase must achieve
- work_items: list of WorkItem objects
- depends_on_phases: list of phase ids that must complete first ([] for the first phase)
- synthesis_instruction: how to combine this phase's work item outputs (e.g.
  "Summarise findings by source, flag contradictions, identify gaps for the next phase")

WORK ITEM FIELDS:
- id, name, description, success_criteria
- required_skills: abstract skill names (NOT tool names). Examples:
  web_search, web_browse, pdf_extraction, code_execution, database_query,
  statistical_analysis, document_parsing, api_integration, data_transformation,
  image_analysis, geospatial_processing

Currently available skills:
{skill_registry_description}

IMPORTANT: Plan for the ideal methodology. Declare skills that do not yet exist if
the work genuinely requires them — gaps are surfaced and resolved before execution.
Do not constrain the plan to currently available skills.

Return a ContextGraph with phases.
"""


async def run_graph_editor(
    brief: ProblemBrief,
    current_graph: ContextGraph,
    feedback: str,
    run_id: str,
) -> ContextGraph:
    """Refine an existing context graph based on user feedback."""
    from slow_ai.skills import SkillRegistry
    skill_registry = SkillRegistry()
    editor = Agent(
        model=ModelRegistry().for_task("context_planning"),
        output_type=ContextGraph,
        system_prompt=_context_planner_prompt(skill_registry.descriptions_for_prompt()),
    )
    result = await editor.run(
        f"Run ID: {run_id}\n\n"
        f"Problem brief:\n{json.dumps(brief.model_dump(), indent=2)}\n\n"
        f"Current context graph (update this based on user feedback — preserve what is correct, "
        f"change only what the user requests):\n"
        f"{json.dumps(current_graph.model_dump(), indent=2)}\n\n"
        f"User feedback / requested changes:\n{feedback}\n\n"
        f"Return an updated ContextGraph."
    )
    graph: ContextGraph = result.output
    graph.goal = brief.goal
    return graph


async def run_context_planner(
    brief: ProblemBrief,
    run_id: str,
    prior_context: str = "",
) -> ContextGraph:
    from slow_ai.skills import SkillRegistry
    skill_registry = SkillRegistry()
    planner = Agent(
        model=ModelRegistry().for_task("context_planning"),
        output_type=ContextGraph,
        system_prompt=_context_planner_prompt(skill_registry.descriptions_for_prompt()),
    )
    prior_section = (
        f"\n\nPRIOR RUN CONTEXT (do not repeat work already covered — "
        f"focus new phases on what is missing or incomplete):\n{prior_context}"
        if prior_context else ""
    )
    result = await planner.run(
        f"Run ID: {run_id}\n\nProblem brief:\n{json.dumps(brief.model_dump(), indent=2)}"
        + prior_section
    )
    graph: ContextGraph = result.output
    graph.goal = brief.goal
    return graph


async def generate_follow_on_brief(
    original_brief: ProblemBrief,
    phase_summaries: list[dict[str, Any]],
    completed_run_id: str,
) -> ProblemBrief:
    """
    Generate a follow-on ProblemBrief targeting what the previous run left unfinished.
    The new brief includes completed_run_id in prior_run_ids so specialists can
    read prior evidence and avoid repeating covered ground.
    """
    agent = Agent(
        model=ModelRegistry().for_task("context_planning"),
        output_type=ProblemBrief,
        system_prompt="""
You are generating a follow-on research brief based on what a previous agent swarm
left unfinished.

You receive:
- The original brief (goal, domain, constraints, success criteria)
- Phase summaries from the completed run (what was covered, partial, uncovered)

Your job:
- Identify which work items had low confidence (partial or uncovered)
- Identify gaps and contradictions surfaced in phase syntheses
- Write a new ProblemBrief focused on resolving those specific gaps
- Inherit the original domain, constraints, and overall goal
- Set unknowns to the specific questions that remain unanswered
- Set success_criteria to the specific evidence that would resolve the gaps
- Leave prior_run_ids as [] — the caller will inject the correct run IDs

Do NOT repeat work that was already covered with high confidence.
Focus the new brief on what is genuinely unfinished.
""",
    )

    summaries_text = json.dumps(phase_summaries, indent=2)
    result = await agent.run(
        f"Original brief:\n{json.dumps(original_brief.model_dump(), indent=2)}\n\n"
        f"Completed run ID: {completed_run_id}\n\n"
        f"Phase summaries from that run:\n{summaries_text}\n\n"
        "Generate a follow-on brief targeting what was left unfinished."
    )
    brief: ProblemBrief = result.output
    # Inject prior run chain
    brief.prior_run_ids = original_brief.prior_run_ids + [completed_run_id]
    return brief


# ── Phase orchestrator ────────────────────────────────────────────────────────

def _phase_orchestrator_prompt(brief: ProblemBrief, phase: Phase, graph: ContextGraph) -> str:
    other_phases = [p.name for p in graph.phases if p.id != phase.id]
    return f"""
You are a work orchestrator assigning specialist agents to a specific phase of work.

OVERALL GOAL: {brief.goal}
DOMAIN: {brief.domain}

CURRENT PHASE: {phase.name}
PHASE PURPOSE: {phase.purpose}

OTHER PHASES (context only — do not assign work to these):
{', '.join(other_phases) if other_phases else 'None — this is the only phase.'}

YOUR JOB:
Assign one specialist agent per work item in this phase. All specialists will run
in parallel. For each work item, define:
- role: a descriptive specialist name matching the work (e.g. "market_analyst",
  "regulatory_researcher", "financial_data_specialist")
- goal: a specific, actionable instruction for what to find or produce
- evidence_required: what proof the agent must return (source-specific, measurable)
- context_budget: tokens (3000-8000 based on task complexity)

WORK ITEMS TO ASSIGN (one specialist each):
{json.dumps([wi.model_dump() for wi in phase.work_items], indent=2)}

CONSTRAINTS:
{json.dumps(brief.constraints, indent=2)}

SUCCESS CRITERIA:
{json.dumps(brief.success_criteria, indent=2)}

Return a ResearchPlan with phase_id="{phase.id}" and one specialist per work item.
"""


async def run_orchestrator(
    brief: ProblemBrief,
    phase: Phase,
    context_graph: ContextGraph,
    run_id: str,
) -> ResearchPlan:
    orchestrator = Agent(
        model=ModelRegistry().for_task("orchestration"),
        output_type=ResearchPlan,
        system_prompt=_phase_orchestrator_prompt(brief, phase, context_graph),
    )
    result = await orchestrator.run(
        f"Run ID: {run_id}\n\n"
        f"Assign specialists for phase '{phase.name}' ({phase.id}).\n"
        f"Work items:\n{json.dumps([wi.model_dump() for wi in phase.work_items], indent=2)}"
    )
    plan: ResearchPlan = result.output
    plan.run_id = run_id
    plan.phase_id = phase.id
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


# ── Phase synthesis ───────────────────────────────────────────────────────────

async def synthesise_phase(
    phase: Phase,
    envelopes: list[EvidenceEnvelope],
    brief: ProblemBrief,
) -> PhaseSummary:
    """
    Synthesise the results of a completed phase into a PhaseSummary.
    The summary includes both the LLM narrative AND the raw envelopes —
    nothing is abstracted away from downstream phases.
    """
    synthesis_agent = Agent(
        model=ModelRegistry().for_task("report_synthesis"),
        output_type=str,
        system_prompt=f"""
You are synthesising the results of a completed phase of work.

PHASE: {phase.name}
PHASE PURPOSE: {phase.purpose}
SYNTHESIS INSTRUCTION: {phase.synthesis_instruction or 'Summarise key findings, note gaps and contradictions.'}

You receive evidence envelopes from all agents that ran in this phase.
Produce a concise synthesis (3-8 paragraphs) that:
- Summarises what was found across all work items
- Notes contradictions or conflicts between agents
- Identifies what remains unclear or unresolved
- States what the next phase should know coming in

Do NOT hallucinate. Every claim must be grounded in the evidence provided.
If evidence is thin, say so clearly.
""",
    )

    envelope_data = json.dumps([e.model_dump() for e in envelopes], indent=2)
    result = await synthesis_agent.run(
        f"Phase: {phase.name}\nGoal context: {brief.goal}\n\n"
        f"Evidence envelopes:\n{envelope_data}"
    )
    synthesis_text: str = result.output

    # Classify work items by confidence
    envelope_by_item: dict[str, EvidenceEnvelope] = {}
    for env in envelopes:
        # match envelope to work item via agent registry's work_item_id
        # envelopes carry work_item_id indirectly through agent registration;
        # here we match by position (one specialist per work item)
        pass

    # Compute per-item confidence from envelopes
    # Since each work item gets one specialist, map by order
    covered, partial, uncovered = [], [], []
    for wi, env in zip(phase.work_items, envelopes):
        if env.confidence >= 0.6:
            covered.append(wi.id)
        elif env.confidence >= 0.3:
            partial.append(wi.id)
        else:
            uncovered.append(wi.id)

    # Handle case where envelope count doesn't match work item count
    # (failures, skips) — remaining items are uncovered
    for wi in phase.work_items[len(envelopes):]:
        uncovered.append(wi.id)

    mean_conf = sum(e.confidence for e in envelopes) / len(envelopes) if envelopes else 0.0
    total_tokens = sum(e.cost_tokens for e in envelopes)

    return PhaseSummary(
        phase_id=phase.id,
        phase_name=phase.name,
        synthesis=synthesis_text,
        envelopes=envelopes,
        covered_item_ids=covered,
        partial_item_ids=partial,
        uncovered_item_ids=uncovered,
        mean_confidence=mean_conf,
        total_tokens=total_tokens,
    )


# ── Phase assessment ──────────────────────────────────────────────────────────

_PHASE_ASSESS_PROMPT = """
You are assessing whether a phase of work is complete and whether to proceed.

You receive:
1. The phase that just completed — its name, purpose, work items
2. A phase summary — synthesis narrative + confidence breakdown
3. The full context graph — all phases and their purposes
4. The problem brief — goal, constraints, success criteria

Decide:
- "proceed": the phase produced sufficient evidence to meaningfully inform the next
  phase. Gaps are acceptable if they do not block the overall goal.
- "synthesize": skip remaining phases and produce the final output now. Use this
  when all important questions have been answered or no further phases can add value.
- "escalate_to_human": a critical finding is ambiguous, contradictory, or requires
  a human judgment call before the next phase can proceed.
- "circuit_break": the phase failed so badly (mean confidence < 0.2, all items
  uncovered) that continuing would waste resources and produce a meaningless result.

Include clear reasoning referencing the phase purpose and overall goal.
Note which work items were covered, partial, or uncovered.
"""

_phase_assess_agent = Agent(
    model=ModelRegistry().for_task("assessment"),
    output_type=OrchestratorDecision,
    system_prompt=_PHASE_ASSESS_PROMPT,
)


async def orchestrator_assess(
    brief: ProblemBrief,
    context_graph: ContextGraph,
    phase: Phase,
    phase_summary: PhaseSummary,
    run_id: str,
) -> OrchestratorDecision:
    result = await _phase_assess_agent.run(
        f"Run ID: {run_id}\n\n"
        f"Problem brief:\n{json.dumps(brief.model_dump(), indent=2)}\n\n"
        f"Full context graph:\n{json.dumps(context_graph.model_dump(), indent=2)}\n\n"
        f"Completed phase: {phase.name} ({phase.id})\n"
        f"Phase purpose: {phase.purpose}\n\n"
        f"Phase summary:\n"
        f"  Synthesis: {phase_summary.synthesis}\n"
        f"  Covered items: {phase_summary.covered_item_ids}\n"
        f"  Partial items: {phase_summary.partial_item_ids}\n"
        f"  Uncovered items: {phase_summary.uncovered_item_ids}\n"
        f"  Mean confidence: {phase_summary.mean_confidence:.2f}\n"
        f"  Total tokens used: {phase_summary.total_tokens}"
    )
    decision: OrchestratorDecision = result.output
    decision.phase_id = phase.id

    # Circuit breaker: enforce hard threshold regardless of LLM decision
    if phase_summary.mean_confidence < 0.15 and not phase_summary.covered_item_ids:
        decision.action = "circuit_break"
        decision.circuit_break_reason = (
            f"Phase '{phase.name}' mean confidence {phase_summary.mean_confidence:.2f} "
            f"with zero covered items — continuing would not add value."
        )

    return decision


# ── Spawn handler ─────────────────────────────────────────────────────────────

async def handle_spawn_request(
    request: SpawnRequest,
    registry: AgentRegistry,
) -> AgentContext:
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
