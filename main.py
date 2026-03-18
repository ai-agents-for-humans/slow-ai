import json
import uuid
from pathlib import Path

import streamlit as st

from slow_ai.agents.interviewer import interviewer
from slow_ai.models import ProblemBrief

st.set_page_config(page_title="Slow AI", layout="centered")
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


init_state()

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
    st.success("Brief confirmed and saved. You're done!")

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
