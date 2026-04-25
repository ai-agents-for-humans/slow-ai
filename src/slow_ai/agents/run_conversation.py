"""
run_conversation — post-run analyst agent.

Reads from a completed run's artifacts and answers questions about what was found.
No new research agents are spawned. All tools are read-only.
"""
import json
import os
from pathlib import Path

from pydantic_ai import Agent

from slow_ai.config import settings
from slow_ai.llm import ModelRegistry
from slow_ai.tools.run_reader import make_run_reader_tools

os.environ["GEMINI_API_KEY"] = settings.gemini_key_slow_ai


def _build_system_prompt(run_id: str, run_path: Path) -> str:
    # Load brief goal if available
    brief_goal = "unknown"
    brief_path = run_path / "problem_brief.json"
    if brief_path.exists():
        try:
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            brief_goal = brief.get("goal", "unknown")
        except Exception:
            pass

    # Load phase overview
    phase_overview = ""
    summaries_path = run_path / "live" / "phase_summaries.json"
    if summaries_path.exists():
        try:
            summaries = json.loads(summaries_path.read_text(encoding="utf-8"))
            lines = []
            for s in summaries:
                covered = len(s.get("covered_item_ids", []))
                partial = len(s.get("partial_item_ids", []))
                uncovered = len(s.get("uncovered_item_ids", []))
                conf = s.get("mean_confidence", 0)
                lines.append(
                    f"  - {s['phase_name']} ({s['phase_id']}): "
                    f"conf {conf:.2f}, {covered} covered / {partial} partial / {uncovered} uncovered"
                )
            phase_overview = "Phases that ran:\n" + "\n".join(lines)
        except Exception:
            pass

    return f"""You are an analyst reviewing the results of a completed agent swarm run.

Run ID: {run_id}
Research goal: {brief_goal}

{phase_overview}

Your role:
- Answer questions about what the agents found, what worked, what didn't, and why
- Use your tools to fetch specific evidence — do not hallucinate findings
- Be concise and direct. Reference specific phase names, agent roles, and confidence scores
- If asked about a dataset or artefact, use read_artefact() to fetch it rather than guessing

Tools available:
- list_phases(): overview of all phases with confidence and coverage
- read_phase(phase_id): full synthesis narrative + envelope summaries for one phase
- read_envelope(agent_id): raw proof dict for a specific agent
- read_report(): the final synthesised report
- search_evidence(keyword): full-text search across all syntheses and envelopes
- read_artefact(relative_path): read a specific file produced during the run

Important: you are read-only. Do not suggest running new agents or fetching new data from the web.
If the user wants to continue the research, they can start a new run from the UI.
"""


def run_conversation_turn(
    user_message: str,
    run_id: str,
    message_history: list,
) -> tuple[str, list]:
    """
    Process one turn of post-run conversation (synchronous — safe to call from Streamlit).

    Returns (assistant_response, updated_message_history).
    The caller is responsible for persisting the response to conversation.jsonl.
    """
    run_path = Path("runs") / run_id
    tools = make_run_reader_tools(run_path)

    agent = Agent(
        model=ModelRegistry().for_task("report_synthesis"),
        output_type=str,
        system_prompt=_build_system_prompt(run_id, run_path),
    )

    @agent.tool_plain
    def list_phases() -> str:
        return tools["list_phases"]()

    @agent.tool_plain
    def read_phase(phase_id: str) -> str:
        return tools["read_phase"](phase_id)

    @agent.tool_plain
    def read_envelope(agent_id: str) -> str:
        return tools["read_envelope"](agent_id)

    @agent.tool_plain
    def read_report() -> str:
        return tools["read_report"]()

    @agent.tool_plain
    def search_evidence(keyword: str) -> str:
        return tools["search_evidence"](keyword)

    @agent.tool_plain
    def read_artefact(relative_path: str) -> str:
        return tools["read_artefact"](relative_path)

    result = agent.run_sync(user_message, message_history=message_history)
    return result.output, result.all_messages()
