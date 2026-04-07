import asyncio
import json
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

def _start_research(brief: ProblemBrief, project_id: str) -> str:
    """
    Write the brief to disk, record the run against the project, and launch
    a research subprocess.

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

    # Record this run against the project so it can be listed later
    runs_file = Path("output") / project_id / "runs.jsonl"
    with runs_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")

    subprocess.Popen(
        [sys.executable, "-m", "slow_ai.research", run_id],
        cwd=str(Path.cwd()),
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

# Milestone node type overrides (take precedence over status-based styles)
_MILESTONE_STYLE = {
    "background": "#312e81", "color": "#c7d2fe",
    "border": "2px solid #6366f1", "borderRadius": "8px",
    "fontSize": "13px", "padding": "10px 16px", "fontWeight": "bold",
}
_ASSESSMENT_STYLE = {
    "background": "#1c1917", "color": "#d6d3d1",
    "border": "1px dashed #78716c", "borderRadius": "6px",
    "fontSize": "12px", "padding": "8px 12px",
}


def _node_style(node: dict) -> dict:
    node_type = node.get("type", "")
    if node_type.startswith("wave_"):
        return _MILESTONE_STYLE
    if node_type == "assessment":
        return _ASSESSMENT_STYLE
    return _STATUS_STYLE.get(node["status"], _STATUS_STYLE["registered"])


_COVERAGE_STYLE = {
    "uncovered": {
        "background": "#1e293b", "color": "#94a3b8",
        "border": "1px solid #475569", "borderRadius": "6px",
        "fontSize": "12px", "padding": "8px 12px",
    },
    "in_progress": {
        "background": "#1e3a8a", "color": "#93c5fd",
        "border": "2px solid #3b82f6", "borderRadius": "6px",
        "fontSize": "12px", "padding": "8px 12px",
    },
    "covered": {
        "background": "#14532d", "color": "#86efac",
        "border": "1px solid #22c55e", "borderRadius": "6px",
        "fontSize": "12px", "padding": "8px 12px",
    },
    "partial": {
        "background": "#431407", "color": "#fdba74",
        "border": "1px solid #f97316", "borderRadius": "6px",
        "fontSize": "12px", "padding": "8px 12px",
    },
}
_COVERAGE_ICON = {
    "uncovered": "○", "in_progress": "◌", "covered": "●", "partial": "◑",
}


def _work_item_coverage(dag: dict, artefacts: dict) -> dict[str, tuple[str, float]]:
    """
    Returns {work_item_id: (coverage_status, max_confidence)} based on the
    current agent DAG and artefacts.
    coverage_status: "uncovered" | "in_progress" | "covered" | "partial"
    """
    # Collect per-work-item agent states and confidences
    states: dict[str, list] = {}
    for node in dag.get("nodes", []):
        wid = node.get("work_item_id")
        if not wid:
            continue
        conf = artefacts.get(node["id"], {}).get("envelope", {}).get("confidence", 0.0)
        states.setdefault(wid, []).append((node["status"], conf))

    result = {}
    for wid, entries in states.items():
        statuses = {s for s, _ in entries}
        max_conf = max(c for _, c in entries)
        if "running" in statuses:
            result[wid] = ("in_progress", max_conf)
        elif "completed" in statuses:
            result[wid] = ("covered" if max_conf >= 0.6 else "partial", max_conf)
        else:
            result[wid] = ("uncovered", 0.0)
    return result


def _build_context_graph_state(
    context_graph: dict, dag: dict, artefacts: dict
) -> StreamlitFlowState:
    coverage = _work_item_coverage(dag, artefacts)
    nodes = []
    for item in context_graph.get("nodes", []):
        wid = item["id"]
        cov_status, conf = coverage.get(wid, ("uncovered", 0.0))
        icon = _COVERAGE_ICON[cov_status]
        label_parts = [f"{icon}  {item['name']}"]
        if cov_status != "uncovered":
            label_parts.append(f"conf: {conf:.2f}")
        nodes.append(StreamlitFlowNode(
            id=wid,
            pos=(0, 0),
            data={"label": "\n".join(label_parts)},
            node_type="default",
            style=_COVERAGE_STYLE[cov_status],
            source_position="bottom",
            target_position="top",
            selectable=True,
        ))

    edges = [
        StreamlitFlowEdge(
            id=f"{e['source']}-{e['target']}",
            source=e["source"],
            target=e["target"],
            animated=False,
            marker_end={"type": "arrowclosed"},
        )
        for e in context_graph.get("edges", [])
    ]
    return StreamlitFlowState(nodes=nodes, edges=edges)


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
            style=_node_style(n),
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
        "current_project_id": None,
        "dag": None,
        "agent_artefacts": {},
        "flow_state": None,
        "flow_state_live": None,
        "context_graph": None,
        "context_graph_state": None,
        "context_graph_state_live": None,
        "latest_assessment": None,
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


def save_brief(brief: ProblemBrief) -> tuple[Path, str]:
    project_id = str(uuid.uuid4())
    project_dir = Path("output") / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    output_path = project_dir / "problem_brief.json"
    output_path.write_text(brief.model_dump_json(indent=2))
    return output_path, project_id


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
    st.session_state.current_project_id = project_id
    st.session_state.report = None
    st.session_state.research_log = []
    st.session_state.current_run_id = None
    st.session_state.dag = None
    st.session_state.agent_artefacts = {}
    st.session_state.flow_state = None
    st.session_state.flow_state_live = None
    st.session_state.context_graph = None
    st.session_state.context_graph_state = None
    st.session_state.context_graph_state_live = None
    st.session_state.latest_assessment = None


def load_project_runs(project_id: str) -> list[dict]:
    """Return all runs for a project, newest first, enriched with live status."""
    runs_file = Path("output") / project_id / "runs.jsonl"
    if not runs_file.exists():
        return []
    runs = []
    for line in runs_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        status_path = Path("runs") / entry["run_id"] / "live" / "status.json"
        if status_path.exists():
            try:
                entry["status"] = json.loads(status_path.read_text())["status"]
            except Exception:
                entry["status"] = "unknown"
        else:
            entry["status"] = "unknown"
        runs.append(entry)
    return list(reversed(runs))


def load_historical_run(run_id: str):
    """Load a completed run's artefacts into session state for viewing."""
    from slow_ai.execution.git_store import GitStore
    from slow_ai.models import ResearchReport as _Report

    store = GitStore(run_id)
    report_path = store.run_path / "report.json"
    st.session_state.report = None
    if report_path.exists():
        try:
            st.session_state.report = _Report.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except Exception:
            pass
    st.session_state.dag = store.read_live("dag.json", {"nodes": [], "edges": []})
    st.session_state.agent_artefacts = store.read_live("artefacts.json", {})
    st.session_state.context_graph = store.read_live("context_graph.json", None)
    st.session_state.latest_assessment = store.read_live("assessment.json", None)
    st.session_state.research_log = store.read_live_log()
    st.session_state.flow_state = None
    st.session_state.context_graph_state = None
    st.session_state.current_run_id = None  # not an active run
    st.session_state.saved = True


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

        # ── Previous runs for this project ────────────────────────────────────
        st.divider()
        st.caption("Previous runs")
        runs = load_project_runs(selected_id)
        if not runs:
            st.caption("No runs yet.")
        else:
            _STATUS_BADGE = {
                "completed": "🟢", "failed": "🔴",
                "waiting_for_human": "🟡", "running": "🔵",
            }
            for run in runs:
                badge = _STATUS_BADGE.get(run["status"], "⚪")
                ts = run.get("started_at", run["run_id"])[:16].replace("T", " ")
                col_label, col_btn = st.columns([3, 1])
                col_label.markdown(f"{badge} `{ts}`")
                if col_btn.button("View", key=f"view_{run['run_id']}"):
                    load_historical_run(run["run_id"])
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
        path, project_id = save_brief(st.session_state.brief)
        st.session_state.saved = True
        st.session_state.current_project_id = project_id
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

    # Start / re-run button
    if not st.session_state.current_run_id:
        btn_label = "Start New Run" if st.session_state.report else "Start Research"
        if st.button(btn_label, type="primary"):
            run_id = _start_research(
                st.session_state.brief,
                st.session_state.current_project_id,
            )
            st.session_state.current_run_id = run_id
            st.session_state.report = None
            st.session_state.dag = None
            st.session_state.agent_artefacts = {}
            st.session_state.context_graph = None
            st.session_state.flow_state = None
            st.session_state.flow_state_live = None
            st.session_state.context_graph_state = None
            st.session_state.context_graph_state_live = None
            st.session_state.latest_assessment = None
            st.rerun()

    # Live view — auto-refreshes every 2 s while a run is in progress
    if st.session_state.current_run_id:

        @st.fragment(run_every="5s")
        def _live_panel():
            from slow_ai.execution.git_store import GitStore
            from slow_ai.models import ResearchReport as _Report

            run_id = st.session_state.current_run_id
            store = GitStore(run_id)
            status_data = store.read_live("status.json", {"status": "initializing"})
            status = status_data.get("status", "initializing")

            if status == "completed":
                report_path = store.run_path / "report.json"
                if report_path.exists():
                    st.session_state.report = _Report.model_validate_json(
                        report_path.read_text(encoding="utf-8")
                    )
                st.session_state.dag = store.read_live(
                    "dag.json", {"nodes": [], "edges": []}
                )
                st.session_state.agent_artefacts = store.read_live("artefacts.json", {})
                st.session_state.context_graph = store.read_live("context_graph.json", None)
                st.session_state.latest_assessment = store.read_live("assessment.json", None)
                st.session_state.research_log = store.read_live_log()
                st.session_state.current_run_id = None
                st.session_state.flow_state = None
                st.session_state.flow_state_live = None
                st.session_state.context_graph_state = None
                st.session_state.context_graph_state_live = None
                st.rerun(scope="app")
                return

            if status == "failed":
                error = status_data.get("error", "unknown error")
                st.error(f"Research failed: {error}")
                if st.button("Reset", key="reset_btn"):
                    st.session_state.current_run_id = None
                    st.rerun()
                return

            # ── Progress log ──────────────────────────────────────────────────
            log = store.read_live_log()
            st.caption(f"● {status}")
            if log:
                st.markdown("\n".join(f"- {m}" for m in log))
            else:
                st.caption("Starting up…")

            # ── Latest orchestrator assessment ─────────────────────────────────
            assessment = store.read_live("assessment.json", None)
            if assessment:
                with st.expander(
                    f"Wave {assessment.get('wave', '?')} assessment — {assessment.get('action', '?')}",
                    expanded=False,
                ):
                    ac, pc, ec = st.columns(3)
                    ac.metric("Covered", len(assessment.get("work_items_covered", [])))
                    pc.metric("Pending", len(assessment.get("work_items_pending", [])))
                    ec.metric("Escalated", len(assessment.get("work_items_escalated", [])))
                    st.caption(assessment.get("reasoning", ""))

            # ── Context graph (blueprint) ──────────────────────────────────────
            cg = store.read_live("context_graph.json", None)
            if cg and cg.get("nodes"):
                st.subheader("Context Graph")
                current_cg_live = st.session_state.context_graph_state_live
                if (
                    current_cg_live is None
                    or len(current_cg_live.nodes) != len(cg["nodes"])
                ):
                    dag_for_cg = store.read_live("dag.json", {"nodes": [], "edges": []})
                    artefacts_for_cg = store.read_live("artefacts.json", {})
                    st.session_state.context_graph_state_live = _build_context_graph_state(
                        cg, dag_for_cg, artefacts_for_cg
                    )
                streamlit_flow(
                    "cg_live",
                    st.session_state.context_graph_state_live,
                    layout=TreeLayout(direction="down"),
                    fit_view=True,
                    height=350,
                )

            # ── Agent DAG (full width) ─────────────────────────────────────────
            dag = store.read_live("dag.json", {"nodes": [], "edges": []})
            if dag.get("nodes"):
                current_live = st.session_state.flow_state_live
                if (
                    current_live is None
                    or len(current_live.nodes) != len(dag["nodes"])
                ):
                    st.session_state.flow_state_live = _build_flow_state(dag)
                streamlit_flow(
                    "dag_live",
                    st.session_state.flow_state_live,
                    layout=TreeLayout(direction="down"),
                    fit_view=True,
                    height=550,
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

        # ── Final orchestrator assessment ──────────────────────────────────────
        assessment = st.session_state.latest_assessment
        if assessment:
            st.subheader("Orchestrator Assessment")
            ac, pc, ec = st.columns(3)
            ac.metric("Work items covered", len(assessment.get("work_items_covered", [])))
            pc.metric("Work items pending", len(assessment.get("work_items_pending", [])))
            ec.metric("Work items escalated", len(assessment.get("work_items_escalated", [])))
            st.caption(f"Final action: **{assessment.get('action', '?')}** — wave {assessment.get('wave', '?')}")
            with st.expander("Reasoning"):
                st.write(assessment.get("reasoning", ""))
            if assessment.get("work_items_pending"):
                with st.expander("Pending work items"):
                    for wid in assessment["work_items_pending"]:
                        st.markdown(f"- `{wid}`")
            if assessment.get("escalation_notes"):
                with st.expander("Escalation notes"):
                    for wid, note in assessment["escalation_notes"].items():
                        st.markdown(f"**{wid}**: {note}")

        # ── Context graph (static blueprint with final coverage) ───────────────
        cg = st.session_state.context_graph
        if cg and cg.get("nodes"):
            st.subheader("Context Graph")
            dag_final = st.session_state.dag or {"nodes": [], "edges": []}
            artefacts_final = st.session_state.agent_artefacts or {}
            if (
                st.session_state.context_graph_state is None
                or len(st.session_state.context_graph_state.nodes) != len(cg["nodes"])
            ):
                st.session_state.context_graph_state = _build_context_graph_state(
                    cg, dag_final, artefacts_final
                )
            new_cg_state = streamlit_flow(
                "context_graph_final",
                st.session_state.context_graph_state,
                layout=TreeLayout(direction="down"),
                fit_view=True,
                height=400,
                get_node_on_click=True,
            )
            st.session_state.context_graph_state = new_cg_state
            if new_cg_state.selected_id:
                selected = next(
                    (n for n in cg["nodes"] if n["id"] == new_cg_state.selected_id),
                    None,
                )
                if selected:
                    st.divider()
                    st.subheader(f"Work Item — {selected['name']}")
                    st.write(selected["description"])
                    if selected.get("success_criteria"):
                        st.markdown(
                            "**Success criteria:**\n"
                            + "\n".join(f"- {c}" for c in selected["success_criteria"])
                        )
                    # Show agents covering this work item
                    covering = [
                        n for n in dag_final.get("nodes", [])
                        if n.get("work_item_id") == selected["id"]
                    ]
                    if covering:
                        st.markdown(
                            "**Agents:** "
                            + "  ·  ".join(
                                f"`{n['id'].split('-')[-1]}` ({n['type']})" for n in covering
                            )
                        )

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
