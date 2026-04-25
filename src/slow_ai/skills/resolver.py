import json
import os

from pydantic_ai import Agent

from slow_ai.config import settings
from slow_ai.models import ContextGraph, ProblemBrief, SkillGap, ViabilityDecision, WorkItem
from slow_ai.skills import SkillRegistry

os.environ["GEMINI_API_KEY"] = settings.gemini_key_slow_ai


def _all_work_items(graph: ContextGraph) -> list[WorkItem]:
    """Flatten all work items across all phases."""
    return [wi for phase in graph.phases for wi in phase.work_items]


def resolve_skills(
    graph: ContextGraph,
    registry: SkillRegistry,
) -> tuple[list[str], list[str], list[SkillGap]]:
    """
    Pure structural analysis — no LLM.

    Within a phase, all work items are parallel and independent.
    Blocking is per-work-item based on missing skills only (no intra-phase
    dependency propagation — that concept no longer exists in the model).

    Returns:
        executable_item_ids: work items where all required skills are available
        blocked_item_ids:    items with at least one missing skill
        gaps:                one SkillGap per missing skill
    """
    all_items = _all_work_items(graph)
    total = len(all_items)

    missing_skill_to_items: dict[str, list[str]] = {}
    direct_gap_items: set[str] = set()

    for item in all_items:
        for skill in item.required_skills:
            if not registry.has(skill):
                missing_skill_to_items.setdefault(skill, []).append(item.id)
                direct_gap_items.add(item.id)

    executable = [item.id for item in all_items if item.id not in direct_gap_items]

    gaps: list[SkillGap] = []
    for skill, required_by in missing_skill_to_items.items():
        gaps.append(SkillGap(
            skill=skill,
            required_by=required_by,
            downstream_blocked=len(required_by),
            is_critical_path=(len(required_by) / total > 0.5) if total > 0 else False,
        ))

    return executable, list(direct_gap_items), gaps


# ── Viability assessor ────────────────────────────────────────────────────────

_VIABILITY_PROMPT = """
You are assessing whether a research run is viable given skill gaps.

You receive:
1. The problem brief — goal, domain, success criteria
2. The context graph — all planned work items with their required skills
3. Skill gap analysis — which skills are missing, which items are blocked,
   structural impact (downstream blocked count, critical path flags)
4. Coverage ratio — what percentage of work items can execute

Decide:
- "go": all required skills exist — proceed normally (no gaps)
- "degraded": some skills are missing, but the remaining executable work is still
  sufficient to meaningfully address the brief's goal and success criteria.
  The run should proceed; blocked items will be recorded as skipped paths.
- "no_go": the missing skills block work that is so central to the brief's goal
  that the run would produce a meaningless result. Abort; resolve skill gaps first.

Key principle: judge by WHAT is blocked, not HOW MANY items are blocked.
A single missing skill that blocks the core research question is "no_go".
Several missing skills that only affect peripheral enrichment are "degraded".
Always include clear reasoning referencing the brief's success criteria.
"""

def _make_viability_agent() -> Agent:
    from slow_ai.llm import ModelRegistry
    return Agent(
        model=ModelRegistry().for_task("viability_assess"),
        output_type=ViabilityDecision,
        system_prompt=_VIABILITY_PROMPT,
    )


async def viability_assess(
    brief: ProblemBrief,
    graph: ContextGraph,
    executable_item_ids: list[str],
    blocked_item_ids: list[str],
    gaps: list[SkillGap],
) -> ViabilityDecision:
    """
    If there are no gaps, return "go" immediately without an LLM call.
    Otherwise, ask the LLM to make the semantic judgment.
    """
    all_items = _all_work_items(graph)
    total = len(all_items)

    if not gaps:
        return ViabilityDecision(
            action="go",
            skill_gaps=[],
            blocked_work_items=[],
            executable_work_items=[n.id for n in all_items],
            coverage_ratio=1.0,
            reasoning="All required skills are available.",
        )

    coverage_ratio = len(executable_item_ids) / total if total > 0 else 0.0

    # Hard rule: if nothing is executable, no_go without asking the LLM.
    if coverage_ratio == 0.0:
        return ViabilityDecision(
            action="no_go",
            skill_gaps=gaps,
            blocked_work_items=blocked_item_ids,
            executable_work_items=[],
            coverage_ratio=0.0,
            reasoning="No work items are executable — all require missing skills.",
        )

    # Hard rule: if anything is executable, degrade and run rather than block.
    # Partial results are always more useful than no results. The LLM only
    # decides the action label; the structural override enforces minimum "degraded".
    gap_summary = "\n".join(
        f"- '{g.skill}': required by {g.required_by}, "
        f"blocks {g.downstream_blocked} items total"
        f"{', IS ON CRITICAL PATH (>50% of graph)' if g.is_critical_path else ''}"
        for g in gaps
    )

    prompt = (
        f"Problem brief:\n{json.dumps(brief.model_dump(), indent=2)}\n\n"
        f"Context graph:\n{json.dumps(graph.model_dump(), indent=2)}\n\n"
        f"Skill gap analysis:\n"
        f"  Total work items: {total}\n"
        f"  Executable: {len(executable_item_ids)} ({coverage_ratio:.0%})\n"
        f"  Blocked: {len(blocked_item_ids)}\n\n"
        f"Missing skills:\n{gap_summary}\n\n"
        f"Blocked work item ids: {blocked_item_ids}\n"
        f"Executable work item ids: {executable_item_ids}"
    )

    result = await _make_viability_agent().run(prompt)
    decision: ViabilityDecision = result.output

    # Structural overrides — the LLM cannot override these
    decision.skill_gaps = gaps
    decision.blocked_work_items = blocked_item_ids
    decision.executable_work_items = executable_item_ids
    decision.coverage_ratio = coverage_ratio
    # Enforce: coverage > 0 always means at least degraded
    if decision.action == "no_go":
        decision.action = "degraded"
        decision.reasoning = (
            f"[Overridden to degraded — {len(executable_item_ids)} item(s) are executable "
            f"and partial results are more useful than none.] {decision.reasoning}"
        )

    return decision
