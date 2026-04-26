import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai import Agent

from slow_ai.agents.orchestrator import (
    handle_spawn_request,
    orchestrator_assess,
    run_context_planner,
    run_orchestrator,
    synthesise_phase,
)
from slow_ai.agents.report_agent import generate_final_report
from slow_ai.agents.specialist import run_specialist
from slow_ai.execution.git_store import GitStore
from slow_ai.execution.registry import AgentRegistry
from slow_ai.models import (
    AgentContext,
    AgentMemory,
    AgentTask,
    ContextGraph,
    EvidenceEnvelope,
    Phase,
    PhaseSummary,
    ProblemBrief,
    ResearchReport,
    SpecialistAssignment,
    SpawnRequest,
    WorkItem,
)
from slow_ai.llm import ModelRegistry
from slow_ai.skills import SkillRegistry
from slow_ai.skills.resolver import resolve_skills, viability_assess
from slow_ai.skills.synthesizer import synthesize_skills
from slow_ai.tools.code_execution import setup_run_venv

logger = logging.getLogger(__name__)

_MAX_PHASES = 8   # circuit breaker: never run more than this many phases


async def run_research(brief: ProblemBrief, run_id: str) -> ResearchReport | None:
    """
    Orchestrate a full research run using the phase-based execution model.

    Phases execute sequentially. Within each phase all work items run in parallel.
    After each phase: synthesise → assess → proceed / circuit_break / escalate.
    """
    store = GitStore(run_id=run_id)
    registry = AgentRegistry()
    all_envelopes: list[EvidenceEnvelope] = []
    phase_summaries: list[PhaseSummary] = []
    artefacts: dict = {}

    store.write_live("status.json", {"status": "initializing"})

    # ── Sandboxed venv for this run ────────────────────────────────────────────
    venv_path = setup_run_venv(run_id)
    logger.info("Run venv ready: %s", venv_path)
    _log(store, f"Run venv ready: {venv_path}")

    try:
        store.commit_brief(brief.model_dump())
        logger.info("Run %s initialised.", run_id)
        _log(store, f"Run `{run_id}` initialised.")

        # ── Context planning ──────────────────────────────────────────────────
        approved_graph_path = store.run_path / "approved_graph.json"
        if approved_graph_path.exists():
            context_graph = ContextGraph.model_validate_json(
                approved_graph_path.read_text(encoding="utf-8")
            )
            context_graph.goal = brief.goal
            logger.info("Using approved context graph from workflow review.")
            _log(store, "Using approved context graph from workflow review.")
        else:
            logger.info("Building context graph for run %s…", run_id)
            _log(store, "Building context graph...")
            prior_context = _load_prior_context(brief.prior_run_ids)
            context_graph = await run_context_planner(brief, run_id, prior_context=prior_context)

        store.write_live("context_graph.json", _graph_for_ui(context_graph))
        store.commit_milestone(
            "M-1-context",
            {"context_graph.json": context_graph.model_dump()},
            registry_snapshot=None,
        )
        total_items = sum(len(p.work_items) for p in context_graph.phases)
        logger.info(
            "Context graph ready — %d phases, %d work items.",
            len(context_graph.phases), total_items,
        )
        _log(
            store,
            f"Context graph ready — {len(context_graph.phases)} phases, "
            f"{total_items} work items.",
        )

        # ── Viability gate ────────────────────────────────────────────────────
        _log(store, "Checking skill viability...")
        skill_registry = SkillRegistry()
        executable_ids, blocked_ids, skill_gaps = resolve_skills(context_graph, skill_registry)

        synthesis_result = None
        if skill_gaps:
            _log(store, f"{len(skill_gaps)} skill gap(s) found — attempting synthesis...")
            synthesis_result = await synthesize_skills(skill_gaps, skill_registry)
            if synthesis_result.synthesized:
                names = [s.name for s in synthesis_result.synthesized]
                _log(store, f"Synthesized {len(synthesis_result.synthesized)} skill(s): {names}.")
            if synthesis_result.needs_new_tool:
                _log(store, f"{len(synthesis_result.needs_new_tool)} skill(s) need new tools.")
            executable_ids, blocked_ids, skill_gaps = resolve_skills(context_graph, skill_registry)

        viability = await viability_assess(brief, context_graph, executable_ids, blocked_ids, skill_gaps)

        milestone_artefacts: dict = {"viability.json": viability.model_dump()}
        if synthesis_result:
            milestone_artefacts["skill_synthesis.json"] = synthesis_result.model_dump()
            store.write_live("synthesis.json", synthesis_result.model_dump())

        store.write_live("viability.json", viability.model_dump())
        store.commit_milestone("M-1-viability", milestone_artefacts, registry_snapshot=None)
        _log(
            store,
            f"Viability: {viability.action} — "
            f"{viability.coverage_ratio:.0%} executable "
            f"({len(skill_gaps)} remaining gap(s)). {viability.reasoning}",
        )

        if viability.action == "no_go":
            logger.warning("Run %s blocked on capabilities — %d gap(s).", run_id, len(viability.skill_gaps))
            store.write_live("capability_checkpoint.json", {
                "gaps": [g.model_dump() for g in viability.skill_gaps],
                "blocked_work_items": viability.blocked_work_items,
                "reasoning": viability.reasoning,
            })
            store.write_live("status.json", {"status": "blocked_on_capabilities"})
            _log(store, "Run blocked — resolve skill gaps before retrying.")
            return None

        # Build working graph: filter blocked items from phases
        working_graph = _build_working_graph(context_graph, viability.executable_work_items, viability.action)
        if viability.action == "degraded":
            for item_id in viability.blocked_work_items:
                missing = [g.skill for g in viability.skill_gaps if item_id in g.required_by]
                store.record_skipped_path(
                    f"skill-gap-{item_id}",
                    reason=f"Missing skills: {missing or ['upstream dependency on blocked item']}",
                    triggered_by="skill_resolver",
                )
            _log(
                store,
                f"Degraded run — {len(viability.blocked_work_items)} items skipped, "
                f"{sum(len(p.work_items) for p in working_graph.phases)} proceeding.",
            )

        # ── Orchestrator registration ─────────────────────────────────────────
        orc_reg = registry.register(
            agent_type="orchestrator",
            parent_agent_id=None,
            task_id=f"orchestration-{run_id}",
        )
        orchestrator_id = orc_reg.agent_id
        registry.update_status(orchestrator_id, "running")
        _emit(store, registry, artefacts)
        store.write_live("status.json", {"status": "running"})

        # ── Phase loop ────────────────────────────────────────────────────────
        completed_phase_ids: set[str] = set()
        phases_run = 0

        for phase in _phases_in_order(working_graph):
            if phases_run >= _MAX_PHASES:
                _log(store, f"Circuit breaker: max phases ({_MAX_PHASES}) reached.")
                break

            logger.info("Phase '%s' (%s): planning specialists…", phase.name, phase.id)
            _log(store, f"Phase '{phase.name}' ({phase.id}): planning specialists...")

            # Plan specialists for this phase
            plan = await run_orchestrator(brief, phase, working_graph, run_id)

            # Register phase node
            phase_node = registry.register(
                agent_type=f"phase_{phase.name.lower().replace(' ', '_')}",
                parent_agent_id=orchestrator_id,
                task_id=f"{phase.id}-{run_id}",
            )
            phase_node_id = phase_node.agent_id
            registry.update_status(phase_node_id, "running")

            # Register and configure each specialist
            for ctx in plan.specialists:
                registry.register(
                    agent_type=ctx.role,
                    parent_agent_id=phase_node_id,
                    task_id=ctx.task.task_id,
                    agent_id=ctx.agent_id,
                    work_item_id=ctx.work_item_id,
                )
                # Resolve tools and playbook instructions from the work item's required_skills
                work_item = _find_work_item(phase, ctx.work_item_id)
                if work_item and work_item.required_skills:
                    ctx.tools_available = skill_registry.tools_for_skills(work_item.required_skills)
                    ctx.skill_instructions = skill_registry.instructions_for_skills(work_item.required_skills)
                else:
                    ctx.tools_available = ["perplexity_search", "web_browse"]
                    ctx.skill_instructions = ""
                ctx.artefacts_dir = str(
                    Path("runs") / run_id / "artefacts" / phase.id / ctx.agent_id
                )
                ctx.venv_path = str(venv_path)
                ctx.prior_run_ids = brief.prior_run_ids

            store.commit_milestone(
                f"M-{phase.id}-plan",
                {f"plans/{phase.id}.json": plan.model_dump()},
                registry_snapshot=registry.snapshot(),
            )
            _emit(store, registry, artefacts)
            logger.info(
                "Phase '%s': running %d specialists in parallel…",
                phase.name, len(plan.specialists),
            )
            _log(store, f"Phase '{phase.name}': running {len(plan.specialists)} specialists in parallel...")

            # Run all specialists in the phase in parallel
            phase_envelopes = await _run_wave(plan.specialists, store, registry, artefacts)
            all_envelopes.extend(phase_envelopes)
            registry.update_status(phase_node_id, "completed")

            # Commit phase evidence
            phase_artefacts: dict = {}
            for env in phase_envelopes:
                phase_artefacts[f"envelopes/{phase.id}/{env.agent_id}.json"] = env.model_dump()
                agent_dir = store.run_path / "artefacts" / phase.id / env.agent_id
                for filename in env.artefacts:
                    safe_name = Path(filename).name
                    rel_path = f"artefacts/{phase.id}/{env.agent_id}/{safe_name}"
                    existing = agent_dir / safe_name
                    if existing.exists():
                        try:
                            content = json.loads(existing.read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            content = {"raw": existing.read_text(encoding="utf-8", errors="replace")}
                    else:
                        content = env.proof
                    phase_artefacts[rel_path] = content
                if agent_dir.exists():
                    for code_file in agent_dir.glob("*.py"):
                        rel_path = f"artefacts/{phase.id}/{env.agent_id}/{code_file.name}"
                        if rel_path not in phase_artefacts:
                            phase_artefacts[rel_path] = {"raw": code_file.read_text(encoding="utf-8", errors="replace")}

            store.commit_milestone(
                f"M-{phase.id}-evidence",
                phase_artefacts,
                registry_snapshot=registry.snapshot(),
            )
            _log(
                store,
                f"Phase '{phase.name}' evidence committed — "
                f"{len(phase_envelopes)} envelopes.",
            )

            # Phase synthesis (always)
            _log(store, f"Phase '{phase.name}': synthesising...")
            store.write_live("status.json", {"status": "running", "phase_status": f"synthesising_{phase.id}"})
            summary = await synthesise_phase(phase, phase_envelopes, brief)
            phase_summaries.append(summary)

            store.commit_milestone(
                f"M-{phase.id}-synthesis",
                {f"syntheses/{phase.id}.json": summary.model_dump()},
                registry_snapshot=registry.snapshot(),
            )
            _log(
                store,
                f"Phase '{phase.name}' synthesis complete — "
                f"confidence {summary.mean_confidence:.2f} "
                f"({len(summary.covered_item_ids)} covered, "
                f"{len(summary.partial_item_ids)} partial, "
                f"{len(summary.uncovered_item_ids)} uncovered).",
            )

            # Update UI with phase summary
            store.write_live("phase_summaries.json", [s.model_dump() for s in phase_summaries])
            _emit(store, registry, artefacts)

            # Phase assessment (circuit breaker check)
            _log(store, f"Phase '{phase.name}': assessing...")
            decision = await orchestrator_assess(brief, working_graph, phase, summary, run_id)

            store.commit_milestone(
                f"M-{phase.id}-assessment",
                {f"assessments/{phase.id}.json": decision.model_dump()},
                registry_snapshot=registry.snapshot(),
            )
            store.write_live("assessment.json", decision.model_dump())
            _log(
                store,
                f"Phase '{phase.name}' assessment: {decision.action} — {decision.reasoning[:120]}",
            )

            phases_run += 1
            completed_phase_ids.add(phase.id)

            if decision.action == "circuit_break":
                logger.warning("Circuit breaker fired for phase '%s': %s", phase.name, decision.circuit_break_reason)
                _log(store, f"Circuit breaker: {decision.circuit_break_reason}")
                break

            if decision.action == "synthesize":
                logger.info("Assessment: all key questions answered — proceeding to final synthesis.")
                _log(store, "Assessment: all key questions answered — proceeding to final synthesis.")
                break

            if decision.action == "escalate_to_human":
                store.write_live("human_checkpoint.json", {
                    "phase_id": phase.id,
                    "phase_name": phase.name,
                    "escalation_notes": decision.escalation_notes,
                    "reasoning": decision.reasoning,
                })
                store.write_live("status.json", {"status": "waiting_for_human"})
                _log(store, "Escalated to human — synthesising with evidence collected so far.")
                break

            # decision.action == "proceed" — continue to next phase

        # ── Final synthesis ───────────────────────────────────────────────────
        registry.update_status(orchestrator_id, "completed")
        synth_reg = registry.register(
            agent_type="synthesizer",
            parent_agent_id=orchestrator_id,
            task_id=f"synthesis-{run_id}",
        )
        registry.update_status(synth_reg.agent_id, "running")
        _emit(store, registry, artefacts)

        _log(store, "Synthesising final report across all phases...")
        report = await _synthesise(run_id, brief, phase_summaries, all_envelopes, store, registry)

        registry.update_status(synth_reg.agent_id, "completed")
        _emit(store, registry, artefacts)

        # ── Final report (mandatory last step) ────────────────────────────────
        _log(store, "Generating final research report…")
        try:
            document = await generate_final_report(brief, phase_summaries, all_envelopes)
            store.write_live("final_report.md", document)
            store.commit_document(document)
            store.append_conversation("assistant", document)
            logger.info("Final report generated and committed for run %s.", run_id)
        except Exception as report_exc:
            logger.error("Failed to generate final report: %s", report_exc, exc_info=True)
            # Non-fatal — run data is still accessible without the document

        _log(store, f"Done. Report committed to runs/{run_id}/")
        logger.info("Run %s completed successfully.", run_id)
        store.write_live("status.json", {"status": "completed"})
        return report

    except Exception as exc:
        logger.error("Run %s failed: %s", run_id, exc, exc_info=True)
        store.write_live("status.json", {"status": "failed", "error": str(exc)})
        raise


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_prior_context(prior_run_ids: list[str]) -> str:
    """
    Build a summary of prior runs to inject into the context planner prompt.
    Returns an empty string if there are no prior runs or none have summaries.
    """
    if not prior_run_ids:
        return ""
    sections = []
    for run_id in prior_run_ids:
        summaries_path = Path("runs") / run_id / "live" / "phase_summaries.json"
        if not summaries_path.exists():
            continue
        try:
            summaries = json.loads(summaries_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in summaries:
            covered = s.get("covered_item_ids", [])
            partial = s.get("partial_item_ids", [])
            uncovered = s.get("uncovered_item_ids", [])
            conf = s.get("mean_confidence", 0)
            synthesis = s.get("synthesis", "")[:600]
            sections.append(
                f"[Run {run_id}] Phase '{s['phase_name']}' (conf {conf:.2f}):\n"
                f"  Covered: {covered}\n  Partial: {partial}\n  Uncovered: {uncovered}\n"
                f"  Summary: {synthesis}"
            )
    return "\n\n".join(sections) if sections else ""


def _phases_in_order(graph: ContextGraph) -> list[Phase]:
    """
    Return phases in topological order (phases whose dependencies are satisfied first).
    For most graphs this is just the declared order, but we resolve properly.
    """
    completed: set[str] = set()
    ordered: list[Phase] = []
    remaining = list(graph.phases)

    while remaining:
        progress = False
        for phase in list(remaining):
            if all(dep in completed for dep in phase.depends_on_phases):
                ordered.append(phase)
                completed.add(phase.id)
                remaining.remove(phase)
                progress = True
        if not progress:
            # Cycle or unresolvable dependency — append remaining as-is
            ordered.extend(remaining)
            break

    return ordered


def _build_working_graph(
    graph: ContextGraph,
    executable_ids: list[str],
    action: str,
) -> ContextGraph:
    """Build a working graph filtered to executable work items only."""
    if action != "degraded":
        return graph

    executable_set = set(executable_ids)
    working_phases = []
    for phase in graph.phases:
        executable_items = [wi for wi in phase.work_items if wi.id in executable_set]
        if executable_items:
            from slow_ai.models import Phase as PhaseModel
            working_phases.append(PhaseModel(
                id=phase.id,
                name=phase.name,
                purpose=phase.purpose,
                work_items=executable_items,
                depends_on_phases=phase.depends_on_phases,
                synthesis_instruction=phase.synthesis_instruction,
            ))
    return ContextGraph(goal=graph.goal, phases=working_phases)


def _find_work_item(phase: Phase, work_item_id: str | None) -> WorkItem | None:
    if not work_item_id:
        return None
    return next((wi for wi in phase.work_items if wi.id == work_item_id), None)


def _graph_for_ui(graph: ContextGraph) -> dict:
    """
    Produce a UI-friendly representation of the phase-based context graph.
    Includes flat nodes/edges for the existing graph renderer, plus phases metadata.
    """
    nodes = []
    edges = []
    for phase in graph.phases:
        # Add a phase header node
        nodes.append({
            "id": phase.id,
            "name": phase.name,
            "description": phase.purpose,
            "node_type": "phase",
            "required_skills": [],
            "success_criteria": [],
        })
        # Add work item nodes
        for wi in phase.work_items:
            nodes.append({
                "id": wi.id,
                "name": wi.name,
                "description": wi.description,
                "node_type": "work_item",
                "required_skills": wi.required_skills,
                "success_criteria": wi.success_criteria,
                "phase_id": phase.id,
            })
            edges.append({"source": wi.id, "target": phase.id, "edge_type": "belongs_to"})
        # Phase dependencies as edges
        for dep_phase_id in phase.depends_on_phases:
            edges.append({"source": phase.id, "target": dep_phase_id, "edge_type": "phase_depends"})

    return {
        "goal": graph.goal,
        "phases": [p.model_dump() for p in graph.phases],
        "nodes": nodes,
        "edges": edges,
    }


async def _run_wave(
    specialists: list[AgentContext],
    store: GitStore,
    registry: AgentRegistry,
    artefacts: dict,
) -> list[EvidenceEnvelope]:
    """Run a set of specialists in parallel and return their envelopes."""

    async def run_with_spawn(ctx: AgentContext):
        async def spawn_handler(request: SpawnRequest) -> AgentContext:
            worker_ctx = await handle_spawn_request(request, registry)
            _log(store, f"Worker spawned: {worker_ctx.agent_id}")
            _emit(store, registry, artefacts)
            worker_envelope, worker_ctx = await run_specialist(worker_ctx, registry, None)
            artefacts[worker_ctx.agent_id] = {
                "envelope": worker_envelope.model_dump(),
                "memory": worker_ctx.memory.model_dump(),
            }
            _emit(store, registry, artefacts)
            return worker_ctx

        registry.update_status(ctx.agent_id, "running")
        _emit(store, registry, artefacts)
        return await run_specialist(ctx, registry, spawn_handler)

    results = await asyncio.gather(
        *[run_with_spawn(ctx) for ctx in specialists],
        return_exceptions=True,
    )

    wave_envelopes = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                "Specialist %s (%s) failed: %s",
                specialists[i].agent_id, specialists[i].role, result,
                exc_info=result,
            )
            _log(store, f"Specialist {specialists[i].agent_id} failed: {result}")
            store.record_skipped_path(
                f"specialist-failed-{specialists[i].agent_id}",
                reason=str(result),
                triggered_by="runner",
            )
        else:
            envelope, updated_ctx = result
            wave_envelopes.append(envelope)
            artefacts[updated_ctx.agent_id] = {
                "envelope": envelope.model_dump(),
                "memory": updated_ctx.memory.model_dump(),
            }
            _log(
                store,
                f"  {updated_ctx.role}: {envelope.status} (confidence {envelope.confidence:.2f})",
            )
        _emit(store, registry, artefacts)

    return wave_envelopes


async def _synthesise(
    run_id: str,
    brief: ProblemBrief,
    phase_summaries: list[PhaseSummary],
    all_envelopes: list[EvidenceEnvelope],
    store: GitStore,
    registry: AgentRegistry,
) -> ResearchReport:

    synthesis_agent = Agent(
        model=ModelRegistry().for_task("report_synthesis"),
        output_type=ResearchReport,
        system_prompt="""
You are producing a final report from a multi-phase investigation.

You receive:
- Phase summaries: a synthesised narrative per phase, with confidence breakdowns
- All evidence envelopes: the raw findings from every agent across every phase

Your job:
- Produce a coherent final report that draws across all phases
- Deduplicate findings across phases
- For each dataset or key finding, assign a quality_score (0.0-1.0)
- Note what was not resolved (paths_not_taken)
- Write a summary that a decision-maker could act on

Return a ResearchReport.
""",
    )

    phases_data = json.dumps([s.model_dump() for s in phase_summaries], indent=2)
    envelope_data = json.dumps([e.model_dump() for e in all_envelopes], indent=2)
    result = await synthesis_agent.run(
        f"Run ID: {run_id}\nGoal: {brief.goal}\n\n"
        f"Phase summaries:\n{phases_data}\n\n"
        f"All evidence envelopes:\n{envelope_data}"
    )
    report: ResearchReport = result.output
    report.run_id = run_id
    report.brief_goal = brief.goal
    report.generated_at = datetime.now(timezone.utc).isoformat()

    store.commit_milestone(
        "M-final-report",
        {"report.json": report.model_dump()},
        registry.snapshot(),
    )

    return report


def _log(store: GitStore, msg: str) -> None:
    store.append_live_log(msg)


def _emit(store: GitStore, registry: AgentRegistry, artefacts: dict) -> None:
    store.write_live("dag.json", registry.get_dag())
    store.write_live("artefacts.json", artefacts)
