import json
import os

from pydantic_ai import Agent

from slow_ai.config import settings
from slow_ai.models import SkillGap, SkillSynthesisResult, SynthesizedSkill
from slow_ai.skills import SkillRegistry

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

_SYNTHESIZER_PROMPT = """
You are a skill synthesizer for a multi-agent research system.

When skill gaps are detected in a research plan, your job is to resolve them by
mapping each missing skill to a combination of tools that already exist in the
registry.

For each missing skill, decide:

1. SYNTHESIZABLE — the skill can be satisfied by one or more existing tools.
   Example: "statistical_analysis" can be implemented with "code_execution"
   (the agent writes Python with pandas/scipy and executes it).
   Example: "domain_analysis" can be implemented with "web_search" + "web_browse"
   (the agent searches for domain knowledge and reasons over results).
   → Produce a SynthesizedSkill entry with the tools that implement it.

2. NEEDS_NEW_TOOL — the skill genuinely requires a new tool that doesn't exist.
   Example: "real_time_satellite_stream" cannot be faked with general code execution
   — it needs a specific API integration.
   → Add the skill name to needs_new_tool.
   → Add a GitHub search query that would find a suitable open source tool.

Rules:
- "code_execution" is a Python subprocess tool. It can implement any skill that
  amounts to "write and run Python code": data transformation, statistical analysis,
  geospatial processing (if libraries installed), ontology/RDF work (rdflib),
  visualization (matplotlib), document parsing (pypdf, docling), etc.
- "web_search" + "web_browse" can implement skills that amount to "find information
  and reason over it": domain analysis, literature review, source discovery, etc.
- Be generous with synthesis — if a skill CAN be implemented with existing tools
  (even imperfectly), synthesize it. Flag needs_new_tool only when existing tools
  genuinely cannot do the job.
- For needs_new_tool entries, write GitHub search queries like:
  "python satellite imagery API open source tool"
  "python PDF document parser library"

Always include reasoning explaining your decisions.
"""

def _make_synthesizer_agent() -> Agent:
    from slow_ai.llm import ModelRegistry
    return Agent(
        model=ModelRegistry().for_task("skill_synthesis"),
        output_type=SkillSynthesisResult,
        system_prompt=_SYNTHESIZER_PROMPT,
    )


async def synthesize_skills(
    gaps: list[SkillGap],
    registry: SkillRegistry,
) -> SkillSynthesisResult:
    """
    Attempt to synthesize missing skills from available tools.
    Persists synthesized skills to the registry immediately.
    """
    available_tools = "\n".join(
        f"- {name}: {registry._skills[name]['description']}"
        for name in registry.available_names()
    )
    gap_descriptions = "\n".join(
        f"- '{g.skill}': required by work items {g.required_by}, "
        f"blocks {g.downstream_blocked} item(s)"
        f"{', CRITICAL PATH' if g.is_critical_path else ''}"
        for g in gaps
    )

    prompt = (
        f"Available tools/skills in registry:\n{available_tools}\n\n"
        f"Missing skills to resolve:\n{gap_descriptions}"
    )

    result = await _make_synthesizer_agent().run(prompt)
    synthesis: SkillSynthesisResult = result.output

    # Persist synthesized skills to the registry so future runs benefit
    if synthesis.synthesized:
        new_entries = [s.model_dump() for s in synthesis.synthesized]
        registry.add_skills(new_entries)
        registry.save()

    return synthesis
