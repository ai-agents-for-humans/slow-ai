import asyncio
import json
import uuid
from pathlib import Path

import nest_asyncio
import streamlit as st

from slow_ai.agents.interviewer import interviewer
from slow_ai.models import ProblemBrief

nest_asyncio.apply()

st.set_page_config(page_title="Slow AI", layout="wide")
st.title("Slow AI — Problem Brief Interview")


def init_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []        # {role, content} for display
    if "history" not in st.session_state:
        st.session_state.history = []         # pydantic-ai message history
    if "brief" not in st.session_state:
        st.session_state.brief = None
    if "saved" not in st.session_state:
        st.session_state.saved = False
    if "report" not in st.session_state:
        st.session_state.report = None
    if "research_log" not in st.session_state:
        st.session_state.research_log = []


def call_agent(user_msg: str):
    result = interviewer.run_sync(user_msg, message_history=st.session_state.history)
    st.session_state.history = result.all_messages()
    return result.output


def display_brief(brief: ProblemBrief):
    st.subheader("Problem Brief")
    st.markdown(f"**Goal:** {brief.goal}")
    st.markdown(f"**Domain:** {brief.domain}")
    with st.expander("Constraints"):
        st.json(brief.constraints)
    with st.expander("Unknowns"):
        for item in brief.unknowns:
            st.markdown(f"- {item}")
    with st.expander("Success Criteria"):
        for item in brief.success_criteria:
            st.markdown(f"- {item}")
    with st.expander("Milestone Flags"):
        for item in brief.milestone_flags:
            st.markdown(f"- {item}")
    with st.expander("Excluded Paths"):
        for item in brief.excluded_paths:
            st.markdown(f"- {item}")


def save_brief(brief: ProblemBrief):
    project_id = str(uuid.uuid4())
    project_dir = Path("output") / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    output_path = project_dir / "problem_brief.json"
    output_path.write_text(brief.model_dump_json(indent=2))
    return output_path


def load_saved_briefs() -> list[tuple[str, ProblemBrief]]:
    """Return list of (project_id, brief) for all saved briefs."""
    output_dir = Path("output")
    if not output_dir.exists():
        return []
    results = []
    for brief_path in sorted(output_dir.glob("*/problem_brief.json"), reverse=True):
        try:
            brief = ProblemBrief.model_validate_json(brief_path.read_text())
            results.append((brief_path.parent.name, brief))
        except Exception:
            pass
    return results


def load_brief_into_session(project_id: str, brief: ProblemBrief):
    st.session_state.brief = brief
    st.session_state.saved = True
    st.session_state.report = None
    st.session_state.research_log = []


init_state()

# Sidebar — load a saved brief and re-run research
with st.sidebar:
    st.header("Saved Projects")
    saved_briefs = load_saved_briefs()
    if not saved_briefs:
        st.caption("No saved briefs yet.")
    else:
        options = {pid: f"{brief.goal[:60]}…" if len(brief.goal) > 60 else brief.goal
                   for pid, brief in saved_briefs}
        selected_id = st.selectbox(
            "Select a project",
            options=list(options.keys()),
            format_func=lambda pid: options[pid],
        )
        selected_brief = next(b for pid, b in saved_briefs if pid == selected_id)
        with st.expander("Brief details"):
            st.markdown(f"**Goal:** {selected_brief.goal}")
            st.markdown(f"**Domain:** {selected_brief.domain}")
        if st.button("Load & Re-run Research", type="primary"):
            load_brief_into_session(selected_id, selected_brief)
            st.rerun()

# Kick off the conversation on first load
if not st.session_state.messages:
    response = call_agent("Hello, I'm ready to start.")
    if isinstance(response, str):
        st.session_state.messages.append({"role": "assistant", "content": response})
    elif isinstance(response, ProblemBrief):
        st.session_state.brief = response

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Show brief + confirm if we have one
if st.session_state.brief and not st.session_state.saved:
    display_brief(st.session_state.brief)
    col1, col2 = st.columns(2)
    if col1.button("Confirm & Save", type="primary"):
        path = save_brief(st.session_state.brief)
        st.session_state.saved = True
        st.success(f"Saved to `{path}`")
        st.rerun()
    if col2.button("Not quite — continue"):
        st.session_state.messages.append({
            "role": "assistant",
            "content": "No problem — what would you like to change?",
        })
        st.session_state.brief = None
        st.rerun()

if st.session_state.saved:
    st.success("Brief confirmed and saved.")
    st.divider()
    st.subheader("Research")

    if not st.session_state.report:
        if st.button("Start Research", type="primary"):
            from slow_ai.research.runner import run_research

            log_placeholder = st.empty()
            log: list[str] = []

            def on_progress(msg: str):
                log.append(msg)
                log_placeholder.markdown("\n".join(f"- {m}" for m in log))

            with st.spinner("Research in progress..."):
                report = asyncio.run(
                    run_research(st.session_state.brief, on_progress=on_progress)
                )

            st.session_state.report = report
            st.session_state.research_log = log
            st.rerun()

    if st.session_state.report:
        report = st.session_state.report

        for msg in st.session_state.research_log:
            st.markdown(f"- {msg}")

        st.divider()
        st.subheader("Datasets found")
        for ds in report.datasets:
            with st.expander(f"{ds.name} — quality: {ds.quality_score:.2f}"):
                st.json(ds.model_dump())

        st.subheader("Summary")
        st.write(report.summary)

        st.subheader("Git log")
        from slow_ai.execution.git_store import GitStore
        store = GitStore(run_id=report.run_id)
        for entry in store.get_log():
            st.text(f"{entry['sha']}  {entry['message']}  {entry['timestamp']}")

# Chat input
if not st.session_state.saved:
    user_input = st.chat_input("Your response...")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        response = call_agent(user_input)
        if isinstance(response, ProblemBrief):
            st.session_state.brief = response
        else:
            st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()


def main():
    pass
