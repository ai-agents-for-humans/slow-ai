import json

from pydantic_ai import Agent

from slow_ai.models import SkillGap, SkillSynthesisResult, SynthesizedSkill
from slow_ai.skills import SkillRegistry

_SYNTHESIZER_PROMPT = """
You are a skill synthesizer for a multi-agent research system.

When skill gaps are detected in a research plan, your job is to resolve them by
mapping each missing skill to a combination of tools that already exist in the
registry, and to write a complete, actionable skill playbook for each one.

────────────────────────────────────────────────────────────────
STEP 1 — CLASSIFY

For each missing skill, decide:

A) SYNTHESIZABLE — the skill can be satisfied by one or more existing tools.
   → Produce a SynthesizedSkill entry with tools + full body content.

B) NEEDS_NEW_TOOL — the skill genuinely requires a new tool that doesn't exist.
   → Add the skill name to needs_new_tool.
   → Add a GitHub search query that would find a suitable open source tool.

Tool rules:
- "code_execution" covers any Python-based task: data transformation, statistical
  analysis, geospatial processing (geopandas/rasterio), ontology/RDF (rdflib),
  visualisation (matplotlib), document parsing (pypdf), economic modelling, etc.
- "web_search" + "web_browse" cover information-retrieval skills: domain analysis,
  literature review, source discovery, regulatory research, etc.
- Be generous — if a skill CAN be implemented with existing tools (even imperfectly),
  synthesize it. Reserve needs_new_tool for genuine impossibilities.

────────────────────────────────────────────────────────────────
STEP 2 — WRITE THE PLAYBOOK

For every SYNTHESIZABLE skill, produce a rich playbook in the body fields:

when_to_use (str)
  One concise paragraph describing when an agent should activate this skill.
  What signals in the work item description indicate this skill is right?
  What problems does it solve?

how_to_execute (list of strings — ordered steps)
  Step-by-step instructions the agent follows to execute this skill.
  Be concrete and specific. Include: where to start, what to look for,
  how to structure the intermediate work, what to check before finishing.
  Typically 4–8 steps.

output_contract (str)
  One paragraph describing exactly what the agent must produce.
  Specify: artefact types (e.g. ".py file + .md summary"), required fields,
  required structure, and any naming conventions.

quality_bar (list of strings — pass/fail criteria)
  Hard requirements for a good execution of this skill.
  Each criterion should be checkable: a reviewer can read it and decide
  pass or fail. Include things that commonly go wrong.
  Typically 3–6 criteria.

pairs_with (list of skill name strings)
  Other skills from the registry that are commonly combined with this one.
  Only list skills that genuinely add value alongside this one.

────────────────────────────────────────────────────────────────
EXAMPLE OUTPUT for skill "economic_modeling":

  name: economic_modeling
  description: Build quantitative economic models to evaluate costs, trade-offs, and
    decision thresholds using Python-based simulation and statistical analysis.
  tools: [code_execution, statistical_analysis, data_transformation]
  when_to_use: Apply when a work item requires quantitative economic reasoning —
    cost-benefit analysis, threshold modelling, sensitivity analysis, or ROI
    estimation. Signals include words like "cost", "trade-off", "break-even",
    "penalty", "economic impact", or "financial model" in the task description.
  how_to_execute:
    - Identify the key economic variables and their relationships from the task.
    - Define the mathematical structure: what is being optimised, what are the inputs,
      what are the outputs.
    - Write Python code using numpy/scipy for numerical computation and pandas for
      tabular output.
    - Run sensitivity analysis over key input parameters (e.g. sample size, cost per
      unit, penalty rate) to show how the output changes.
    - Produce a summary table: baseline scenario + at least two sensitivity scenarios.
    - Interpret the results in plain language: what does the model recommend?
  output_contract: Produce one .py artefact implementing the model, and one .md
    summary containing: model description, input assumptions, results table,
    sensitivity analysis, and a plain-language recommendation.
  quality_bar:
    - All assumptions must be stated explicitly with numeric values.
    - Sensitivity analysis must cover at least two input dimensions.
    - Code must run without errors and produce deterministic output.
    - Results must be interpretable without reading the code.
  pairs_with: [statistical_analysis, data_transformation, web_search]

Always include reasoning explaining your synthesis decisions.
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
