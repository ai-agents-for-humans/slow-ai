import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

from pydantic_ai import Agent

from slow_ai.agents.orchestrator import handle_spawn_request, run_orchestrator
from slow_ai.agents.specialist import run_specialist
from slow_ai.config import settings
from slow_ai.execution.git_store import GitStore
from slow_ai.execution.registry import AgentRegistry
from slow_ai.models import (
    AgentContext,
    DatasetCandidate,
    EvidenceEnvelope,
    ProblemBrief,
    ResearchPlan,
    ResearchReport,
    SpawnRequest,
)

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key


async def run_research(
    brief: ProblemBrief,
    on_progress: callable = None,
) -> ResearchReport:

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    store = GitStore(run_id=run_id)
    registry = AgentRegistry()

    store.commit_brief(brief.model_dump())
    _progress(on_progress, f"Run `{run_id}` initialised.")

    # Step 1: Orchestrator plans
    _progress(on_progress, "Orchestrator planning research...")
    plan: ResearchPlan = await run_orchestrator(brief, run_id)

    # Register all specialists
    for ctx in plan.specialists:
        registry.register(
            agent_type=ctx.role,
            parent_agent_id=None,
            task_id=ctx.task.task_id,
        )

    store.commit_milestone(
        "M0-plan",
        {"research_plan.json": plan.model_dump()},
        registry_snapshot=registry.snapshot(),
    )
    _progress(on_progress, f"Plan ready — {len(plan.specialists)} specialists assigned.")

    # Step 2: Specialists run in parallel
    _progress(on_progress, "Launching specialists in parallel...")

    async def run_with_spawn(ctx: AgentContext):
        async def spawn_handler(request: SpawnRequest) -> AgentContext:
            worker_ctx = await handle_spawn_request(request, registry)
            _progress(on_progress, f"Worker spawned: {worker_ctx.agent_id} (parent: {request.requested_by})")
            worker_envelope, worker_ctx = await run_specialist(worker_ctx, registry, None)
            return worker_ctx
        return await run_specialist(ctx, registry, spawn_handler)

    results = await asyncio.gather(
        *[run_with_spawn(ctx) for ctx in plan.specialists],
        return_exceptions=True,
    )

    envelopes: list[EvidenceEnvelope] = []
    updated_contexts: list[AgentContext] = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            _progress(on_progress, f"Specialist {plan.specialists[i].agent_id} failed: {result}")
            store.record_skipped_path(
                f"specialist-failed-{plan.specialists[i].agent_id}",
                reason=str(result),
                triggered_by="runner",
            )
        else:
            envelope, updated_ctx = result
            envelopes.append(envelope)
            updated_contexts.append(updated_ctx)
            _progress(on_progress, f"{updated_ctx.role}: {envelope.status} (confidence {envelope.confidence:.2f})")

    # Commit M1 — all envelopes and memory stores
    m1_artefacts = {}
    for envelope, ctx in zip(envelopes, updated_contexts):
        m1_artefacts[f"envelopes/{envelope.agent_id}.json"] = envelope.model_dump()
        m1_artefacts[f"memory/{ctx.agent_id}.json"] = ctx.memory.model_dump()

    store.commit_milestone("M1-source-discovery", m1_artefacts, registry.snapshot())
    _progress(on_progress, f"M1 committed — {len(envelopes)} envelopes.")

    # Record stop verdicts
    for envelope in envelopes:
        if envelope.verdict == "stop":
            store.record_skipped_path(
                f"stop-verdict-{envelope.agent_id}",
                reason="agent returned stop verdict",
                triggered_by=envelope.agent_id,
            )

    # Step 3: Synthesis
    _progress(on_progress, "Synthesising final report...")
    report = await _synthesise(run_id, brief, envelopes, store, registry, on_progress)
    _progress(on_progress, f"Done. Report committed to runs/{run_id}/")

    return report


async def _synthesise(
    run_id: str,
    brief: ProblemBrief,
    envelopes: list[EvidenceEnvelope],
    store: GitStore,
    registry: AgentRegistry,
    on_progress: callable,
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


def _progress(callback: callable, message: str) -> None:
    if callback:
        callback(message)
