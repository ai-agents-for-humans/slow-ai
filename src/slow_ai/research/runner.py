import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

from pydantic_ai import Agent

from slow_ai.agents.orchestrator import (
    handle_spawn_request,
    orchestrator_assess,
    run_context_planner,
    run_orchestrator,
)
from slow_ai.agents.specialist import run_specialist
from slow_ai.config import settings
from slow_ai.execution.git_store import GitStore
from slow_ai.execution.registry import AgentRegistry
from slow_ai.models import (
    AgentContext,
    AgentMemory,
    AgentTask,
    ContextGraph,
    EvidenceEnvelope,
    ProblemBrief,
    ResearchReport,
    SpecialistAssignment,
    SpawnRequest,
    WorkItem,
)

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

_MAX_WAVES = 5


async def run_research(brief: ProblemBrief, run_id: str) -> ResearchReport:
    """
    Orchestrate a full research run.

    All progress and state is written to runs/{run_id}/live/ as plain files so
    any UI (Streamlit, React, CLI) can poll without being coupled to this code.
    Git commits capture durable milestones; live files capture real-time state.
    """
    store = GitStore(run_id=run_id)
    registry = AgentRegistry()
    artefacts: dict = {}
    envelopes: list[EvidenceEnvelope] = []

    store.write_live("status.json", {"status": "initializing"})

    try:
        store.commit_brief(brief.model_dump())
        _log(store, f"Run `{run_id}` initialised.")

        # ── Step 0: Context planning ──────────────────────────────────────────
        _log(store, "Building context graph...")
        context_graph = await run_context_planner(brief, run_id)
        store.write_live("context_graph.json", context_graph.model_dump())
        store.commit_milestone(
            "M-1-context",
            {"context_graph.json": context_graph.model_dump()},
            registry_snapshot=None,
        )
        _log(store, f"Context graph ready — {len(context_graph.nodes)} work items.")

        # ── Step 1: Orchestrator creates first wave ───────────────────────────
        orc_reg = registry.register(
            agent_type="orchestrator",
            parent_agent_id=None,
            task_id=f"orchestration-{run_id}",
        )
        orchestrator_id = orc_reg.agent_id
        registry.update_status(orchestrator_id, "running")
        _emit(store, registry, artefacts)

        # Wave 1: only work items with no upstream dependencies
        wave1_ready = _ready_work_items(context_graph, covered=set())
        _log(
            store,
            f"Orchestrator assigning first wave — "
            f"{len(wave1_ready)} unblocked work items: "
            f"{[w.id for w in wave1_ready]}",
        )
        plan = await run_orchestrator(brief, context_graph, wave1_ready, run_id)

        # Register wave 1 milestone node — specialists are children of it
        wave_node = registry.register(
            agent_type="wave_1",
            parent_agent_id=orchestrator_id,
            task_id=f"wave-1-{run_id}",
        )
        wave_node_id = wave_node.agent_id
        registry.update_status(wave_node_id, "running")

        for ctx in plan.specialists:
            registry.register(
                agent_type=ctx.role,
                parent_agent_id=wave_node_id,
                task_id=ctx.task.task_id,
                agent_id=ctx.agent_id,
                work_item_id=ctx.work_item_id,
            )

        _emit(store, registry, artefacts)
        store.commit_milestone(
            "M0-plan",
            {"research_plan.json": plan.model_dump()},
            registry_snapshot=registry.snapshot(),
        )
        _log(store, f"Wave 1 planned — {len(plan.specialists)} specialists.")
        store.write_live("status.json", {"status": "running"})

        current_wave_specialists = plan.specialists

        # ── Orchestrator loop ─────────────────────────────────────────────────
        # wave_node_id tracks the current wave milestone node for chaining
        assess_node_id = None  # tracks last assessment node for chaining next wave

        for wave in range(1, _MAX_WAVES + 1):
            _log(store, f"Wave {wave}: launching {len(current_wave_specialists)} specialists...")

            wave_envelopes = await _run_wave(
                current_wave_specialists, store, registry, artefacts
            )
            envelopes.extend(wave_envelopes)

            # Mark wave node completed
            registry.update_status(wave_node_id, "completed")

            # Commit wave milestone
            wave_artefacts = {}
            for env in wave_envelopes:
                wave_artefacts[f"envelopes/wave{wave}/{env.agent_id}.json"] = env.model_dump()
            store.commit_milestone(
                f"M{wave}-wave",
                wave_artefacts,
                registry_snapshot=registry.snapshot(),
            )
            _log(store, f"Wave {wave} complete — {len(wave_envelopes)} envelopes collected.")

            # Compute which work items are now unblocked for the next wave
            covered_ids = set(
                node.get("work_item_id")
                for node in registry.get_dag()["nodes"]
                if node.get("status") == "completed" and node.get("work_item_id")
            )
            next_ready = _ready_work_items(context_graph, covered=covered_ids)
            _log(
                store,
                f"Dependency check: {len(covered_ids)} covered, "
                f"{len(next_ready)} newly unblocked: {[w.id for w in next_ready]}",
            )

            # Orchestrator assesses coverage and decides next action
            _log(store, f"Orchestrator assessing coverage after wave {wave}...")
            decision = await orchestrator_assess(
                brief, context_graph, envelopes, next_ready, run_id, wave
            )

            # Register assessment node as child of the wave node
            assess_reg = registry.register(
                agent_type="assessment",
                parent_agent_id=wave_node_id,
                task_id=f"assessment-{wave}-{run_id}",
            )
            assess_node_id = assess_reg.agent_id
            registry.update_status(assess_node_id, "completed")

            # Commit assessment milestone — durable record of what's done / pending
            store.commit_milestone(
                f"M{wave}-assessment",
                {f"assessments/wave{wave}.json": decision.model_dump()},
                registry_snapshot=registry.snapshot(),
            )
            _log(
                store,
                f"Assessment: {len(decision.work_items_covered)} covered, "
                f"{len(decision.work_items_pending)} pending, "
                f"{len(decision.work_items_escalated)} escalated — {decision.action}",
            )
            store.write_live("assessment.json", decision.model_dump())
            _emit(store, registry, artefacts)

            if decision.action == "synthesize":
                _log(store, "All work items covered. Proceeding to synthesis.")
                break

            if decision.action == "escalate_to_human":
                _log(store, f"Escalating to human: {decision.reasoning}")
                store.write_live(
                    "human_checkpoint.json",
                    {
                        "wave": wave,
                        "escalated_items": decision.work_items_escalated,
                        "notes": decision.escalation_notes,
                        "reasoning": decision.reasoning,
                        "pending": decision.work_items_pending,
                    },
                )
                store.write_live("status.json", {"status": "waiting_for_human"})
                # Phase 3: block here and resume when human responds.
                # For now: synthesise with evidence collected so far.
                _log(store, "Synthesising with available evidence (human review pending).")
                break

            if decision.action == "spawn_specialists":
                if not decision.next_wave:
                    _log(store, "No new specialists assigned despite spawn decision — proceeding to synthesis.")
                    break
                # Register next wave node as child of the assessment node
                next_wave_num = wave + 1
                wave_node = registry.register(
                    agent_type=f"wave_{next_wave_num}",
                    parent_agent_id=assess_node_id,
                    task_id=f"wave-{next_wave_num}-{run_id}",
                )
                wave_node_id = wave_node.agent_id
                registry.update_status(wave_node_id, "running")
                current_wave_specialists = [
                    _assignment_to_context(a, wave_node_id, registry)
                    for a in decision.next_wave
                ]
                _emit(store, registry, artefacts)
                _log(store, f"Wave {next_wave_num} planned — {len(current_wave_specialists)} new specialists.")
                continue

            # Unexpected action value — treat as done
            break

        else:
            _log(store, f"Circuit breaker reached ({_MAX_WAVES} waves). Proceeding to synthesis.")

        # ── Synthesis ─────────────────────────────────────────────────────────
        registry.update_status(orchestrator_id, "completed")
        synth_reg = registry.register(
            agent_type="synthesizer",
            parent_agent_id=orchestrator_id,
            task_id=f"synthesis-{run_id}",
        )
        registry.update_status(synth_reg.agent_id, "running")
        _emit(store, registry, artefacts)

        _log(store, "Synthesising final report...")
        report = await _synthesise(run_id, brief, envelopes, store, registry)

        registry.update_status(synth_reg.agent_id, "completed")
        _emit(store, registry, artefacts)

        _log(store, f"Done. Report committed to runs/{run_id}/")
        store.write_live("status.json", {"status": "completed"})
        return report

    except Exception as exc:
        store.write_live("status.json", {"status": "failed", "error": str(exc)})
        raise


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _run_wave(
    specialists: list[AgentContext],
    store: GitStore,
    registry: AgentRegistry,
    artefacts: dict,
) -> list[EvidenceEnvelope]:
    """Run a wave of specialists in parallel and return their envelopes."""

    async def run_with_spawn(ctx: AgentContext):
        async def spawn_handler(request: SpawnRequest) -> AgentContext:
            worker_ctx = await handle_spawn_request(request, registry)
            _log(store, f"Worker spawned: {worker_ctx.agent_id} (parent: {request.requested_by})")
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
                f"{updated_ctx.role}: {envelope.status} (confidence {envelope.confidence:.2f})",
            )
        _emit(store, registry, artefacts)

    return wave_envelopes


def _assignment_to_context(
    assignment: SpecialistAssignment,
    wave_node_id: str,
    registry: AgentRegistry,
) -> AgentContext:
    """Convert an OrchestratorDecision SpecialistAssignment into a runnable AgentContext."""
    task_id = f"task-{uuid.uuid4().hex[:6]}"
    agent_id = f"{assignment.role.replace(' ', '_').lower()}-{uuid.uuid4().hex[:6]}"
    reg = registry.register(
        agent_type=assignment.role,
        parent_agent_id=wave_node_id,
        task_id=task_id,
        agent_id=agent_id,
        work_item_id=assignment.work_item_id,
    )
    task = AgentTask(
        task_id=task_id,
        parent_task_id=None,
        agent_type=assignment.role,
        goal=assignment.goal,
        context_budget=assignment.context_budget,
    )
    memory = AgentMemory(
        agent_id=agent_id,
        agent_type=assignment.role,
        context_budget=assignment.context_budget,
    )
    return AgentContext(
        agent_id=agent_id,
        role=assignment.role,
        expertise=[],
        task=task,
        memory=memory,
        constraints={},
        tools_available=["perplexity_search", "web_browse"],
        evidence_required=assignment.evidence_required,
        work_item_id=assignment.work_item_id,
    )


async def _synthesise(
    run_id: str,
    brief: ProblemBrief,
    envelopes: list[EvidenceEnvelope],
    store: GitStore,
    registry: AgentRegistry,
) -> ResearchReport:

    synthesis_agent = Agent(
        model="google-gla:gemini-3-flash-preview",
        output_type=ResearchReport,
        system_prompt="""
You are a research synthesiser. You receive evidence envelopes from multiple
specialist agents and produce a final ranked research report.

For each dataset found across all envelopes:
- Deduplicate by name and source
- Assign a quality_score (0.0 to 1.0) based on coverage, resolution, license, completeness
- Rank datasets by quality_score descending
- Note paths not taken (failed agents, stop verdicts)
- Write a short summary of the overall findings

Return a ResearchReport.
""",
    )

    envelope_data = json.dumps([e.model_dump() for e in envelopes], indent=2)
    result = await synthesis_agent.run(
        f"Run ID: {run_id}\n\nGoal: {brief.goal}\n\nEvidence envelopes:\n{envelope_data}"
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


def _ready_work_items(context_graph: ContextGraph, covered: set[str]) -> list[WorkItem]:
    """
    Return work items that are ready to be worked on:
    - not yet covered
    - all upstream dependencies are in the covered set
    """
    return [
        item for item in context_graph.nodes
        if item.id not in covered
        and all(dep in covered for dep in item.depends_on)
    ]


def _log(store: GitStore, msg: str) -> None:
    store.append_live_log(msg)


def _emit(store: GitStore, registry: AgentRegistry, artefacts: dict) -> None:
    """Write the current DAG and artefacts snapshots to live files."""
    store.write_live("dag.json", registry.get_dag())
    store.write_live("artefacts.json", artefacts)
