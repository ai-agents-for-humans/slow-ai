import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

from pydantic_ai import Agent

from slow_ai.agents.orchestrator import handle_spawn_request, run_context_planner, run_orchestrator
from slow_ai.agents.specialist import run_specialist
from slow_ai.config import settings
from slow_ai.execution.git_store import GitStore
from slow_ai.execution.registry import AgentRegistry
from slow_ai.models import (
    AgentContext,
    EvidenceEnvelope,
    ProblemBrief,
    ResearchPlan,
    ResearchReport,
    SpawnRequest,
)

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key


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

        # ── Step 1: Orchestrator plans ────────────────────────────────────────
        orc_reg = registry.register(
            agent_type="orchestrator",
            parent_agent_id=None,
            task_id=f"orchestration-{run_id}",
        )
        orchestrator_id = orc_reg.agent_id
        registry.update_status(orchestrator_id, "running")
        _emit(store, registry, artefacts)

        _log(store, "Orchestrator assigning specialists to work items...")
        plan: ResearchPlan = await run_orchestrator(brief, context_graph, run_id)

        # Register specialists using the IDs the orchestrator already assigned,
        # parented to the orchestrator. Pass work_item_id so the DAG carries
        # the blueprint linkage through to the UI.
        for ctx in plan.specialists:
            registry.register(
                agent_type=ctx.role,
                parent_agent_id=orchestrator_id,
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
        _log(store, f"Plan ready — {len(plan.specialists)} specialists assigned.")
        store.write_live("status.json", {"status": "running"})

        # ── Step 2: Specialists run in parallel ───────────────────────────────
        _log(store, "Launching specialists in parallel...")

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
            *[run_with_spawn(ctx) for ctx in plan.specialists],
            return_exceptions=True,
        )

        envelopes: list[EvidenceEnvelope] = []
        updated_contexts: list[AgentContext] = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                _log(store, f"Specialist {plan.specialists[i].agent_id} failed: {result}")
                store.record_skipped_path(
                    f"specialist-failed-{plan.specialists[i].agent_id}",
                    reason=str(result),
                    triggered_by="runner",
                )
            else:
                envelope, updated_ctx = result
                envelopes.append(envelope)
                updated_contexts.append(updated_ctx)
                artefacts[updated_ctx.agent_id] = {
                    "envelope": envelope.model_dump(),
                    "memory": updated_ctx.memory.model_dump(),
                }
                _log(store, f"{updated_ctx.role}: {envelope.status} (confidence {envelope.confidence:.2f})")
            _emit(store, registry, artefacts)

        # Commit M1 — all envelopes and memory stores
        m1_artefacts = {}
        for envelope, ctx in zip(envelopes, updated_contexts):
            m1_artefacts[f"envelopes/{envelope.agent_id}.json"] = envelope.model_dump()
            m1_artefacts[f"memory/{ctx.agent_id}.json"] = ctx.memory.model_dump()

        store.commit_milestone("M1-source-discovery", m1_artefacts, registry.snapshot())
        _log(store, f"M1 committed — {len(envelopes)} envelopes.")

        for envelope in envelopes:
            if envelope.verdict == "stop":
                store.record_skipped_path(
                    f"stop-verdict-{envelope.agent_id}",
                    reason="agent returned stop verdict",
                    triggered_by=envelope.agent_id,
                )

        # ── Step 3: Synthesis ─────────────────────────────────────────────────
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


async def _synthesise(
    run_id: str,
    brief: ProblemBrief,
    envelopes: list[EvidenceEnvelope],
    store: GitStore,
    registry: AgentRegistry,
) -> ResearchReport:

    synthesis_agent = Agent(
        model="google-gla:gemini-2.0-flash",
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
        "M2-final-report",
        {"report.json": report.model_dump()},
        registry.snapshot(),
    )

    return report


def _log(store: GitStore, msg: str) -> None:
    store.append_live_log(msg)


def _emit(store: GitStore, registry: AgentRegistry, artefacts: dict) -> None:
    """Write the current DAG and artefacts snapshots to live files."""
    store.write_live("dag.json", registry.get_dag())
    store.write_live("artefacts.json", artefacts)
