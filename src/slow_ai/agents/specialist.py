import json
import os
import uuid
from datetime import datetime, timezone

from pydantic_ai import Agent

from slow_ai.config import settings
from slow_ai.models import AgentContext, EvidenceEnvelope, MemoryEntry, SpawnRequest
from slow_ai.tools.perplexity import perplexity_search
from slow_ai.tools.web_browse import web_browse

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key


def build_system_prompt(ctx: AgentContext) -> str:
    return f"""
You are a {ctx.role}.

Your expertise: {', '.join(ctx.expertise) if ctx.expertise else 'earth observation data research'}

Your task:
{ctx.task.goal}

Research constraints:
{json.dumps(ctx.constraints, indent=2)}

Context budget: {ctx.memory.context_budget} tokens. Currently used: {ctx.memory.total_tokens}.
Budget remaining: {ctx.memory.budget_remaining()} tokens.

You have two tools:
- search: find datasets, get relevant URLs and a synthesised answer
- browse: read a specific URL and extract detailed information

Research process:
1. Use search with a precise query tailored to your task and constraints
2. From citations returned, use browse on each URL to get actual dataset details
3. After each tool call, note key findings (you will write these to memory)
4. If your budget is running low and you have more URLs to check, note them in
   your evidence envelope — the runner will spawn workers for the remaining URLs

Evidence required:
{json.dumps(ctx.evidence_required, indent=2) if ctx.evidence_required else
"sources_checked, datasets_found, coverage_pct, license, resolution, download_url"}

Return an EvidenceEnvelope with:
- status: completed / partial / faileds
- role: your role name
- proof: everything you found, structured
- verdict: continue (found useful data) / escalate (needs human review) / stop (nothing found)
- confidence: 0.0 to 1.0
- artefacts: list of filenames to save (include agent_id in name)
- workers_spawned: leave empty — the runner fills this in
"""


async def run_specialist(
    ctx: AgentContext,
    registry=None,
    spawn_handler=None,
) -> tuple[EvidenceEnvelope, AgentContext]:
    """
    Run a specialist agent.
    Returns the evidence envelope AND the updated context (with populated memory).
    """

    agent = Agent(
        model="google-gla:gemini-3-pro-preview",
        output_type=EvidenceEnvelope,
        system_prompt=build_system_prompt(ctx),
    )

    @agent.tool_plain
    async def search(query: str) -> str:
        result = await perplexity_search(query)
        entry = MemoryEntry(
            key=f"search_{uuid.uuid4().hex[:4]}",
            value={"query": query, "answer": result.answer, "citations": result.citations},
            source="perplexity_search",
            confidence=0.8,
            created_at=datetime.now(timezone.utc).isoformat(),
            tokens_consumed=len(result.answer.split()) * 2,
        )
        ctx.memory.add(entry)
        return json.dumps({"answer": result.answer, "citations": result.citations})

    @agent.tool_plain
    async def browse(url: str) -> str:
        result = await web_browse(url)
        entry = MemoryEntry(
            key=f"browse_{uuid.uuid4().hex[:4]}",
            value={"url": url, "title": result.title, "text": result.text[:500]},
            source="web_browse",
            confidence=0.9 if result.success else 0.1,
            created_at=datetime.now(timezone.utc).isoformat(),
            tokens_consumed=len(result.text.split()) * 2 if result.text else 10,
        )
        ctx.memory.add(entry)
        if not result.success:
            return json.dumps({"error": result.error})
        return json.dumps({"title": result.title, "text": result.text})

    if registry:
        registry.update_status(ctx.agent_id, "running")

    result = await agent.run(
        "Begin research for your assigned task. "
        "Start with a search, then browse key URLs from the citations."
    )

    envelope: EvidenceEnvelope = result.output
    envelope.agent_id = ctx.agent_id
    envelope.cost_tokens = ctx.memory.total_tokens

    if registry:
        registry.update_status(ctx.agent_id, "completed", tokens_used=ctx.memory.total_tokens)
        registry.set_memory_path(ctx.agent_id, f"memory/{ctx.agent_id}.json")

    return envelope, ctx
