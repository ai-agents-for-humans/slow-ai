import asyncio
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import nest_asyncio
import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.layouts import TreeLayout
from streamlit_flow.state import StreamlitFlowState

from slow_ai.agents.interviewer import interviewer
from slow_ai.models import ProblemBrief

nest_asyncio.apply()

st.set_page_config(page_title="Slow AI", layout="wide")
st.title("Slow AI — Problem Brief Interview")


# ── Research subprocess ───────────────────────────────────────────────────────

def _start_research(brief: ProblemBrief) -> str:
    """
    Write the brief to disk and launch a research subprocess.

    The subprocess runs in its own Python process with its own event loop —
    no shared asyncio state, no Streamlit context, no threading issues.
    It writes all live state to runs/{run_id}/live/ as plain JSON files.
    Streamlit polls those files via a fragment.

    Returns the run_id so the caller can store it in session state.
    """
    run_id = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        f"-{uuid.uuid4().hex[:6]}"
    )
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input_brief.json").write_text(
        brief.model_dump_json(), encoding="utf-8"
    )

    subprocess.Popen(
        [sys.executable, "-m", "slow_ai.research", run_id],
        cwd=str(Path.cwd()),
        # stdout/stderr go to the terminal where Streamlit is running
    )
    return run_id


# ── DAG rendering helpers ─────────────────────────────────────────────────────

_STATUS_STYLE = {
    "registered": {
        "background": "#1e293b", "color": "#94a3b8",
        "border": "1px solid #475569", "borderRadius": "6px",
        "fontSize": "12px", "padding": "8px 12px",
    },
    "running": {
        "background": "#1e3a8a", "color": "#93c5fd",
        "border": "2px solid #3b82f6", "borderRadius": "6px",
        "fontSize": "12px", "padding": "8px 12px",
    },
    "completed": {
        "background": "#14532d", "color": "#86efac",
        "border": "1px solid #22c55e", "borderRadius": "6px",
        "fontSize": "12px", "padding": "8px 12px",
    },
    "failed": {
        "background": "#450a0a", "color": "#fca5a5",
        "border": "1px solid #ef4444", "borderRadius": "6px",
        "fontSize": "12px", "padding": "8px 12px",
    },
}
_STATUS_ICON = {
    "registered": "○", "running": "◌", "completed": "●", "failed": "✕",
}


def _duration_secs(spawned_at: str | None, completed_at: str | None) -> int | None:
    if not spawned_at or not completed_at:
        return None
    try:
        s = datetime.fromisoformat(spawned_at)
        e = datetime.fromisoformat(completed_at)
        return max(0, int((e - s).total_seconds()))
    except Exception:
        return None


def _build_flow_state(dag: dict) -> StreamlitFlowState:
    nodes = []
    for n in dag["nodes"]:
        role = n["type"].replace("_", " ")
        icon = _STATUS_ICON.get(n["status"], "○")
        parts = [f"{icon}  {role}"]
        if n["tokens"] > 0:
            parts.append(f"{n['tokens']:,} tok")
        secs = _duration_secs(n.get("spawned_at"), n.get("completed_at"))
        if secs is not None:
            parts.append(f"{secs}s")
        nodes.append(StreamlitFlowNode(
            id=n["id"],
            pos=(0, 0),
            data={"label": "\n".join(parts)},
            node_type="default",
            style=_STATUS_STYLE.get(n["status"], _STATUS_STYLE["registered"]),
            source_position="bottom",
            target_position="top",
            selectable=True,
        ))

    edges = [
        StreamlitFlowEdge(
            id=f"{e['source']}-{e['target']}",
            source=e["source"],
            target=e["target"],
            animated=True,
            marker_end={"type": "arrowclosed"},
        )
        for e in dag["edges"]
    ]

    return StreamlitFlowState(nodes=nodes, edges=edges)


def _render_agent_detail(agent_id: str, dag: dict, artefacts: dict):
    node = next((n for n in dag["nodes"] if n["id"] == agent_id), None)
    if not node:
        return

    st.divider()
    role = node["type"].replace("_", " ").title()
    st.subheader(f"Agent — {role}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Status", node["status"])
    col2.metric("ID", node["id"].split("-")[-1])
    col3.metric("Tokens", f"{node['tokens']:,}" if node["tokens"] else "—")
    secs = _duration_secs(node.get("spawned_at"), node.get("completed_at"))
    col4.metric("Duration", f"{secs}s" if secs is not None else "—")

    data = artefacts.get(agent_id, {})
    tab_envelope, tab_memory, tab_raw = st.tabs(["Envelope", "Memory", "Raw"])

    with tab_envelope:
        if "envelope" not in data:
            st.caption("No envelope data yet.")
        else:
            env = data["envelope"]
            vcol, ccol, scol = st.columns(3)
            vcol.metric("Verdict", env.get("verdict", "—"))
            ccol.metric("Confidence", f"{env.get('confidence', 0):.2f}")
            scol.metric("Status", env.get("status", "—"))
            if env.get("proof"):
                with st.expander("Proof"):
                    st.json(env["proof"])
            if env.get("artefacts"):
                st.markdown(
                    "**Artefacts:** " + "  ·  ".join(f"`{a}`" for a in env["artefacts"])
                )

    with tab_memory:
        if "memory" not in data:
            st.caption("No memory data yet.")
        else:
            mem = data["memory"]
            entries = mem.get("entries", [])
            st.caption(
                f"{len(entries)} entries · "
                f"{mem.get('total_tokens', 0):,} / {mem.get('context_budget', 0):,} tokens"
            )
            for entry in entries:
                header = (
                    f"{entry['key']}  —  {entry['source']}"
                    f"  (conf: {entry['confidence']:.2f})"
                )
                with st.expander(header):
                    st.json(entry.get("value", {}))

    with tab_raw:
        st.json(data)


# ── Session state ─────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "messages": [],
        "history": [],
        "brief": None,
        "saved": False,
        "report": None,
        "research_log": [],
        "current_run_id": None,
        "dag": None,
        "agent_artefacts": {},
        "flow_state": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


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
    st.session_state.current_run_id = None
    st.session_state.dag = None
    st.session_state.agent_artefacts = {}
    st.session_state.flow_state = None


# ── App ───────────────────────────────────────────────────────────────────────

init_state()

# Sidebar — saved projects
with st.sidebar:
    st.header("Saved Projects")
    saved_briefs = load_saved_briefs()
    if not saved_briefs:
        st.caption("No saved briefs yet.")
    else:
        options = {
            pid: f"{brief.goal[:60]}…" if len(brief.goal) > 60 else brief.goal
            for pid, brief in saved_briefs
        }
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

# Kick off interview on first load
if not st.session_state.messages:
    response = call_agent("Hello, I'm ready to start.")
    if isinstance(response, str):
        st.session_state.messages.append({"role": "assistant", "content": response})
    elif isinstance(response, ProblemBrief):
        st.session_state.brief = response

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Brief confirmation
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

# ── Research area ─────────────────────────────────────────────────────────────

if st.session_state.saved:
    st.success("Brief confirmed and saved.")
    st.divider()
    st.subheader("Research")

    # Start button — shown only when no run is active and no report exists
    if not st.session_state.current_run_id and not st.session_state.report:
        if st.button("Start Research", type="primary"):
            run_id = _start_research(st.session_state.brief)
            st.session_state.current_run_id = run_id
            st.rerun()

    # Live view — auto-refreshes every 2 s while a run is in progress
    if st.session_state.current_run_id:

        @st.fragment(run_every="2s")
        def _live_panel():
            from slow_ai.execution.git_store import GitStore
            from slow_ai.models import ResearchReport as _Report

            run_id = st.session_state.current_run_id
            store = GitStore(run_id)
            status_data = store.read_live("status.json", {"status": "initializing"})
            status = status_data.get("status", "initializing")

            if status == "completed":
                # Capture final state then hand off to the report view
                report_path = store.run_path / "report.json"
                if report_path.exists():
                    st.session_state.report = _Report.model_validate_json(
                        report_path.read_text(encoding="utf-8")
                    )
                st.session_state.dag = store.read_live(
                    "dag.json", {"nodes": [], "edges": []}
                )
                st.session_state.agent_artefacts = store.read_live("artefacts.json", {})
                st.session_state.research_log = store.read_live_log()
                st.session_state.current_run_id = None
                st.session_state.flow_state = None
                st.rerun(scope="app")
                return

            if status == "failed":
                error = status_data.get("error", "unknown error")
                st.error(f"Research failed: {error}")
                if st.button("Reset", key="reset_btn"):
                    st.session_state.current_run_id = None
                    st.rerun()
                return

            # Initializing / running
            log = store.read_live_log()
            dag = store.read_live("dag.json", {"nodes": [], "edges": []})

            col_log, col_dag = st.columns([1, 2])
            with col_log:
                st.caption(f"● {status}")
                if log:
                    st.markdown("\n".join(f"- {m}" for m in log))
                else:
                    st.caption("Starting up…")
            with col_dag:
                if dag.get("nodes"):
                    flow_state = _build_flow_state(dag)
                    streamlit_flow(
                        "dag_live",
                        flow_state,
                        layout=TreeLayout(direction="down"),
                        fit_view=True,
                        height=420,
                    )
                else:
                    st.caption("Waiting for agents…")

        _live_panel()

    # Report view — shown after a run completes
    if st.session_state.report:
        report = st.session_state.report

        with st.expander("Run log", expanded=False):
            for msg in st.session_state.research_log:
                st.markdown(f"- {msg}")

        st.subheader("Agent DAG")
        dag = st.session_state.dag or {"nodes": [], "edges": []}

        if dag.get("nodes"):
            if (
                st.session_state.flow_state is None
                or len(st.session_state.flow_state.nodes) != len(dag["nodes"])
            ):
                st.session_state.flow_state = _build_flow_state(dag)

            new_state = streamlit_flow(
                "agent_dag",
                st.session_state.flow_state,
                layout=TreeLayout(direction="down"),
                fit_view=True,
                height=500,
                get_node_on_click=True,
            )
            st.session_state.flow_state = new_state

            if new_state.selected_id:
                _render_agent_detail(
                    new_state.selected_id,
                    dag,
                    st.session_state.agent_artefacts,
                )

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

# Chat input — only during the interview phase
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
