import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic_ai import Agent

from slow_ai.llm import ModelRegistry
from slow_ai.models import AgentContext, EvidenceEnvelope, MemoryEntry
from slow_ai.tools.browser_use_tool import browser_use as _browser_use
from slow_ai.tools.code_execution import code_execution as _code_execution
from slow_ai.tools.code_generation import generate_python_code
from slow_ai.tools.perplexity import perplexity_search
from slow_ai.tools.url_fetch import url_fetch as _url_fetch
from slow_ai.tools.web_browse import web_browse

logger = logging.getLogger(__name__)


def _tool_descriptions(tools_available: list[str]) -> str:
    descriptions = {
        "perplexity_search": (
            "search(query): search the web for information — returns a synthesised "
            "answer plus source citations"
        ),
        "web_browse": ("browse(url): navigate to a URL and extract its full text content"),
        "code_execution": (
            "generate_code(task_description): generate Python code for a task using "
            "a code-specialist LLM — returns the code and saves a .py file. "
            "Always call this first to produce well-structured Python.\n"
            "- execute(code): run Python code in an isolated subprocess and return "
            "stdout/stderr. Always print() results you want to capture."
        ),
        "url_fetch": (
            "fetch_url(url): download a file from a URL and inspect its contents. "
            "Returns schema + sample rows for CSV/Parquet/Excel, full text for PDFs, "
            "structure + sample for JSON. Use this to look inside actual datasets and "
            "research papers — not just their landing pages."
        ),
        "read_prior_evidence": (
            "read_prior_evidence(topic): search prior run evidence for a topic or keyword. "
            "Use this FIRST to avoid repeating work already done in previous runs."
        ),
        "browser_use": (
            "browse_interactive(task): drive a real browser with an LLM agent to complete "
            "an interactive web task — use for JS-rendered SPAs, login flows, form submission, "
            "and infinite scroll that static web_browse cannot reach. Describe the task in "
            "full detail including the starting URL and what to extract."
        ),
    }
    lines = [descriptions[t] for t in tools_available if t in descriptions]
    return "\n".join(f"- {line}" for line in lines) if lines else "No tools available."


def build_system_prompt(ctx: AgentContext) -> str:
    skill_section = ""
    if ctx.skill_instructions:
        skill_section = f"""
Skill playbooks active for this task:
{ctx.skill_instructions}

Follow these playbooks. They define how to execute, what to produce, and what
quality bar you must clear. Do not skip steps or omit required artefacts.
"""

    return f"""
You are a {ctx.role}.

Your expertise: {", ".join(ctx.expertise) if ctx.expertise else "research and analysis"}

Your task:
{ctx.task.goal}

Research constraints:
{json.dumps(ctx.constraints, indent=2)}

Context budget: {ctx.memory.context_budget} tokens. Currently used: {ctx.memory.total_tokens}.
Budget remaining: {ctx.memory.budget_remaining()} tokens.
{skill_section}
Available tools:
{_tool_descriptions(ctx.tools_available)}

Research process:
1. Use the tools available to you to investigate your task
2. After each tool call, note key findings (you will write these to memory)
3. If your budget is running low and there is more to investigate, note remaining
   work in your evidence envelope — the runner will spawn workers for it

Evidence required:
{
        json.dumps(ctx.evidence_required, indent=2)
        if ctx.evidence_required
        else "sources_checked, findings, confidence_rationale"
    }

Return an EvidenceEnvelope with:
- status: completed / partial / failed
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
    Run a specialist agent with only the tools its work item requires.
    Returns the evidence envelope AND the updated context (with populated memory).
    """

    agent = Agent(
        model=ModelRegistry().for_task("specialist_research"),
        output_type=EvidenceEnvelope,
        system_prompt=build_system_prompt(ctx),
    )

    # Register only the tools this agent has been granted
    if "perplexity_search" in ctx.tools_available:

        @agent.tool_plain
        async def search(query: str) -> str:
            result = await perplexity_search(query)
            entry = MemoryEntry(
                key=f"search_{uuid.uuid4().hex[:4]}",
                value={
                    "query": query,
                    "answer": result.answer,
                    "citations": result.citations,
                },
                source="perplexity_search",
                confidence=0.8,
                created_at=datetime.now(UTC).isoformat(),
                tokens_consumed=len(result.answer.split()) * 2,
            )
            ctx.memory.add(entry)
            return json.dumps({"answer": result.answer, "citations": result.citations})

    if "web_browse" in ctx.tools_available:

        @agent.tool_plain
        async def browse(url: str) -> str:
            result = await web_browse(url)
            entry = MemoryEntry(
                key=f"browse_{uuid.uuid4().hex[:4]}",
                value={"url": url, "title": result.title, "text": result.text[:500]},
                source="web_browse",
                confidence=0.9 if result.success else 0.1,
                created_at=datetime.now(UTC).isoformat(),
                tokens_consumed=len(result.text.split()) * 2 if result.text else 10,
            )
            ctx.memory.add(entry)
            if not result.success:
                return json.dumps({"error": result.error})
            return json.dumps({"title": result.title, "text": result.text})

    if "browser_use" in ctx.tools_available:

        @agent.tool_plain
        async def browse_interactive(task: str) -> str:
            result = await _browser_use(task)
            entry = MemoryEntry(
                key=f"browser_{uuid.uuid4().hex[:4]}",
                value={"task": task[:200], "result": result.result[:500], "success": result.success},
                source="browser_use",
                confidence=0.85 if result.success else 0.1,
                created_at=datetime.now(UTC).isoformat(),
                tokens_consumed=len(result.result.split()) * 2 if result.result else 10,
            )
            ctx.memory.add(entry)
            if not result.success:
                return json.dumps({"error": result.error})
            return json.dumps({"result": result.result})

    if "url_fetch" in ctx.tools_available:

        @agent.tool_plain
        async def fetch_url(url: str) -> str:
            result = await _url_fetch(url)
            entry = MemoryEntry(
                key=f"fetch_{uuid.uuid4().hex[:4]}",
                value={
                    "url": url,
                    "content_type": result.content_type,
                    "summary": result.summary,
                    "success": result.success,
                    "error": result.error,
                },
                source="url_fetch",
                confidence=0.95 if result.success else 0.1,
                created_at=datetime.now(UTC).isoformat(),
                tokens_consumed=len(str(result.data)) // 4,
            )
            ctx.memory.add(entry)
            if not result.success:
                return json.dumps({"error": result.error})
            return json.dumps(
                {
                    "content_type": result.content_type,
                    "summary": result.summary,
                    "data": result.data,
                }
            )

    if "code_execution" in ctx.tools_available:

        @agent.tool_plain
        async def generate_code(task_description: str) -> str:
            """Generate Python code for the given task using a code-specialist LLM."""
            generated = await generate_python_code(
                task_description,
                save_to_dir=ctx.artefacts_dir,
            )
            entry = MemoryEntry(
                key=f"codegen_{uuid.uuid4().hex[:4]}",
                value={
                    "filename": generated.filename,
                    "description": generated.description,
                    "code_preview": generated.code[:300],
                },
                source="code_generation",
                confidence=0.9,
                created_at=datetime.now(UTC).isoformat(),
                tokens_consumed=len(generated.code.split()) * 2,
            )
            ctx.memory.add(entry)
            return json.dumps(
                {
                    "code": generated.code,
                    "filename": generated.filename,
                    "description": generated.description,
                }
            )

        @agent.tool_plain
        async def execute(code: str) -> str:
            result = await _code_execution(
                code, working_dir=ctx.artefacts_dir, venv_path=ctx.venv_path
            )
            entry = MemoryEntry(
                key=f"exec_{uuid.uuid4().hex[:4]}",
                value={
                    "success": result["success"],
                    "stdout": result["stdout"][:1000],
                    "stderr": result["stderr"][:500] if result["stderr"] else "",
                },
                source="code_execution",
                confidence=0.95 if result["success"] else 0.1,
                created_at=datetime.now(UTC).isoformat(),
                tokens_consumed=len(result["stdout"].split()) * 2 + 20,
            )
            ctx.memory.add(entry)
            return json.dumps(result)

    if ctx.prior_run_ids:

        @agent.tool_plain
        async def read_prior_evidence(topic: str) -> str:
            """Search prior run evidence for a topic. Call this first to avoid repeating work."""
            from slow_ai.tools.run_reader import search_across_runs

            run_paths = [Path("runs") / rid for rid in ctx.prior_run_ids]
            return search_across_runs(run_paths, topic)

    if registry:
        registry.update_status(ctx.agent_id, "running")

    logger.info("Specialist %s (%s) starting.", ctx.agent_id, ctx.role)
    try:
        result = await agent.run(
            "Begin research for your assigned task using the tools available to you."
        )
    except Exception as exc:
        logger.error(
            "Specialist %s (%s) raised an exception: %s",
            ctx.agent_id,
            ctx.role,
            exc,
            exc_info=True,
        )
        raise

    envelope: EvidenceEnvelope = result.output
    envelope.agent_id = ctx.agent_id
    envelope.cost_tokens = ctx.memory.total_tokens

    logger.info(
        "Specialist %s (%s) finished — status=%s confidence=%.2f verdict=%s",
        ctx.agent_id,
        ctx.role,
        envelope.status,
        envelope.confidence,
        envelope.verdict,
    )

    if registry:
        registry.update_status(ctx.agent_id, "completed", tokens_used=ctx.memory.total_tokens)
        registry.set_memory_path(ctx.agent_id, f"memory/{ctx.agent_id}.json")

    return envelope, ctx
