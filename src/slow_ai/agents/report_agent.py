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


def _build_context(brief: ProblemBrief, phase_summaries: list[PhaseSummary]) -> str:
    lines = [
        "## Research Brief",
        f"Goal: {brief.goal}",
        f"Domain: {brief.domain}",
    ]
    if brief.constraints:
        lines.append(f"Constraints: {json.dumps(brief.constraints)}")
    if brief.unknowns:
        lines.append("Unknowns to resolve:")
        for u in brief.unknowns:
            lines.append(f"  - {u}")
    if brief.success_criteria:
        lines.append("Success criteria:")
        for sc in brief.success_criteria:
            lines.append(f"  - {sc}")
    if brief.excluded_paths:
        lines.append("Excluded paths:")
        for ep in brief.excluded_paths:
            lines.append(f"  - {ep}")

    lines.append("\n## Phase Findings")

    for ps in phase_summaries:
        lines.append(f"\n### {ps.phase_name}  (mean confidence: {ps.mean_confidence:.0%})")
        lines.append(f"\n**Phase synthesis:**\n{ps.synthesis}")

        if ps.envelopes:
            lines.append("\n**Agent evidence:**")
            for env in ps.envelopes:
                short_id = env.agent_id[:8]
                lines.append(f"\n**[{short_id}] {env.role}**")
                lines.append(
                    f"- Status: {env.status} | Verdict: {env.verdict} "
                    f"| Confidence: {env.confidence:.0%}"
                )
                if env.proof:
                    proof_str = json.dumps(env.proof, ensure_ascii=False)
                    if len(proof_str) > 2000:
                        proof_str = proof_str[:2000] + "…"
                    lines.append(f"- Findings: {proof_str}")
                if env.artefacts:
                    lines.append(f"- Artefacts: {', '.join(env.artefacts)}")

    return "\n".join(lines)


async def generate_final_report(
    brief: ProblemBrief,
    phase_summaries: list[PhaseSummary],
    all_envelopes: list[EvidenceEnvelope],
) -> str:
    context = _build_context(brief, phase_summaries)
    result = await report_agent.run(context)
    return result.output
