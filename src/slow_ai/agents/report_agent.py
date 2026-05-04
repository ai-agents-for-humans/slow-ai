"""
report_agent — final research report synthesis.

Reads all phase summaries and agent evidence from a completed run and produces
a single long-form markdown document following the report_synthesis skill playbook.
Invoked as the mandatory last step of every run.
"""
import json
from pathlib import Path

from pydantic_ai import Agent

from slow_ai.llm import ModelRegistry
from slow_ai.models import EvidenceEnvelope, PhaseSummary, ProblemBrief

_SKILL_PATH = (
    Path(__file__).parents[1] / "skills" / "catalog" / "report_synthesis" / "SKILL.md"
)


def _load_system_prompt() -> str:
    content = _SKILL_PATH.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    return parts[2].strip() if len(parts) >= 3 else content


report_agent = Agent(
    model=ModelRegistry().for_task("orchestration"),
    output_type=str,
    system_prompt=_load_system_prompt(),
)


def _format_proof(proof: dict) -> str:
    """Render an agent's proof dict as readable structured text."""
    parts = []
    for key, value in proof.items():
        heading = key.replace("_", " ").title()
        if isinstance(value, str):
            parts.append(f"**{heading}:**\n{value.strip()}")
        elif isinstance(value, list):
            items = "\n".join(f"  - {item}" for item in value)
            parts.append(f"**{heading}:**\n{items}")
        elif isinstance(value, dict):
            items = "\n".join(f"  - {k}: {v}" for k, v in value.items())
            parts.append(f"**{heading}:**\n{items}")
        else:
            parts.append(f"**{heading}:** {value}")
    return "\n\n".join(parts)


def _build_context(brief: ProblemBrief, phase_summaries: list[PhaseSummary]) -> str:
    lines = [
        "# Research Brief\n",
        f"**Goal:** {brief.goal}",
        f"**Domain:** {brief.domain}",
    ]
    if brief.constraints:
        lines.append(f"**Constraints:** {json.dumps(brief.constraints)}")
    if brief.unknowns:
        lines.append("**Unknowns to resolve:**")
        for u in brief.unknowns:
            lines.append(f"  - {u}")
    if brief.success_criteria:
        lines.append("**Success criteria:**")
        for sc in brief.success_criteria:
            lines.append(f"  - {sc}")
    if brief.excluded_paths:
        lines.append("**Excluded paths:**")
        for ep in brief.excluded_paths:
            lines.append(f"  - {ep}")

    lines.append("\n---\n")
    lines.append("# Full Phase Evidence\n")
    lines.append(
        "Everything below is the complete output of every agent in every phase. "
        "Include all of this detail in the final report — do not drop or compress findings.\n"
    )

    for ps in phase_summaries:
        conf_pct = f"{ps.mean_confidence:.0%}" if ps.mean_confidence is not None else "unknown"
        lines.append(f"\n## Phase: {ps.phase_name}  (mean confidence: {conf_pct})\n")
        lines.append(f"### Phase Synthesis (orchestrator assessment)\n\n{ps.synthesis}\n")

        if ps.envelopes:
            lines.append("### Agent Findings\n")
            for env in ps.envelopes:
                short_id = env.agent_id[:8]
                conf_str = f"{env.confidence:.0%}" if env.confidence is not None else "unknown"
                lines.append(f"#### [{short_id}] {env.role}")
                lines.append(
                    f"- **Status:** {env.status}  "
                    f"**Verdict:** {env.verdict}  "
                    f"**Confidence:** {conf_str}"
                )
                if env.proof:
                    lines.append("\n" + _format_proof(env.proof))
                if env.artefacts:
                    lines.append(f"\n**Artefacts produced:** {', '.join(env.artefacts)}")
                lines.append("")

    return "\n".join(lines)


async def generate_final_report(
    brief: ProblemBrief,
    phase_summaries: list[PhaseSummary],
    all_envelopes: list[EvidenceEnvelope],
) -> str:
    context = _build_context(brief, phase_summaries)
    result = await report_agent.run(context)
    return result.output
