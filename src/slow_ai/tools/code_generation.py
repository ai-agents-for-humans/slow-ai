from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent


class GeneratedCode(BaseModel):
    code: str  # the complete Python code
    filename: str  # suggested .py filename (e.g. "analyse_shapefile.py")
    description: str  # one-sentence description of what the code does


_CODE_GEN_PROMPT = """
You are a Python code generation specialist. Given a task description, write
complete, runnable Python code that accomplishes the task.

Rules:
- Always write Python. Never write shell scripts, pseudo-code, or other languages.
- Write complete, self-contained code. Import everything you need.
- Use print() to output results — stdout is the only output channel.
- Prefer standard library where possible. For data work: pandas, numpy, scipy.
  For geospatial: geopandas, shapely. For knowledge graphs / RDF: rdflib.
  For visualisation: matplotlib (save to file, do not show interactively).
- Handle errors gracefully with try/except and print useful error messages.
- Suggest a short, descriptive filename (snake_case, .py extension).
- Write a one-sentence description of what the code does.
"""


def _make_agent() -> Agent:
    from slow_ai.llm import ModelRegistry

    model = ModelRegistry().for_task("code_generation")
    return Agent(
        model=model,
        output_type=GeneratedCode,
        system_prompt=_CODE_GEN_PROMPT,
    )


async def generate_python_code(
    task_description: str,
    context: str = "",
    save_to_dir: str | None = None,
) -> GeneratedCode:
    """
    Generate Python code for a given task description using the configured
    code generation model. Optionally saves the .py file to save_to_dir.
    """
    agent = _make_agent()
    prompt = f"Task: {task_description}"
    if context:
        prompt += f"\n\nContext:\n{context}"

    result = await agent.run(prompt)
    generated: GeneratedCode = result.output

    if save_to_dir:
        path = Path(save_to_dir) / generated.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generated.code, encoding="utf-8")

    return generated
