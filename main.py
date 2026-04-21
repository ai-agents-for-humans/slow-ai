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
st.title("Slow AI")
st.caption("Describe the problem or workflow you want to automate — we'll design a multi-agent workflow and run it for you.")


# ── Research subprocess ───────────────────────────────────────────────────────

def _start_research(brief: ProblemBrief, project_id: str, run_id: str | None = None, approved_graph: dict | None = None) -> str:
    """
    Write the brief to disk, record the run against the project, and launch
    the agent swarm subprocess.

    If run_id is provided (graph was pre-planned), reuse that directory.
    If approved_graph is provided, save it so the runner skips context planning.
    Returns the run_id.
    """
    if run_id is None:
        run_id = (
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
            f"-{uuid.uuid4().hex[:6]}"
        )
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input_brief.json").write_text(
        brief.model_dump_json(), encoding="utf-8"
    )

    if approved_graph is not None:
        import json as _json
        (run_dir / "approved_graph.json").write_text(
            _json.dumps(approved_graph), encoding="utf-8"
        )

    # Record this run against the project so it can be listed later
    runs_file = Path("output") / project_id / "runs.jsonl"
    # Avoid duplicate entry if run_id was pre-allocated during graph planning
    existing_ids: set[str] = set()
    if runs_file.exists():
        for line in runs_file.read_text(encoding="utf-8").splitlines():
            try:
                existing_ids.add(json.loads(line)["run_id"])
            except Exception:
                pass
    if run_id not in existing_ids:
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


# ── Workflow planning helpers ─────────────────────────────────────────────────

def _plan_workflow(brief: ProblemBrief, project_id: str):
    """Run context planner in the UI process and enter graph review mode."""
    from slow_ai.agents.orchestrator import generate_graph_summary, run_context_planner
    from slow_ai.research.runner import _graph_for_ui, _load_prior_context

    run_id = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        f"-{uuid.uuid4().hex[:6]}"
    )
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input_brief.json").write_text(brief.model_dump_json(), encoding="utf-8")

    runs_file = Path("output") / project_id / "runs.jsonl"
    with runs_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")

    prior_context = _load_prior_context(brief.prior_run_ids)
    loop = asyncio.get_event_loop()
    graph = loop.run_until_complete(
        run_context_planner(brief, run_id, prior_context=prior_context)
    )
    summary = loop.run_until_complete(generate_graph_summary(brief, graph))

    st.session_state.pending_run_id = run_id
    st.session_state.graph_pending_model = graph.model_dump()
    st.session_state.context_graph = _graph_for_ui(graph)
    st.session_state.context_graph_state = None
    st.session_state.graph_review_mode = True
    st.session_state.graph_review_messages = [{"role": "assistant", "content": summary}]
    st.session_state.graph_review_history = []


def _refine_graph(feedback: str):
    """Apply user feedback to the pending graph via the graph editor agent."""
    from slow_ai.agents.orchestrator import generate_graph_summary, run_graph_editor
    from slow_ai.models import ContextGraph as CG
    from slow_ai.research.runner import _graph_for_ui

    current = CG.model_validate(st.session_state.graph_pending_model)
    brief = st.session_state.brief
    run_id = st.session_state.pending_run_id

    loop = asyncio.get_event_loop()
    updated = loop.run_until_complete(run_graph_editor(brief, current, feedback, run_id))
    summary = loop.run_until_complete(generate_graph_summary(brief, updated))

    st.session_state.graph_pending_model = updated.model_dump()
    st.session_state.context_graph = _graph_for_ui(updated)
    st.session_state.context_graph_state = None

    return summary


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
_PHASE_NODE_STYLE = {
    "background": "#1e1b4b", "color": "#a5b4fc",
    "border": "2px solid #6366f1", "borderRadius": "8px",
    "fontSize": "13px", "padding": "12px 16px", "fontWeight": "bold",
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
    "missing_skill": {
        "background": "#1c0a0a", "color": "#fca5a5",
        "border": "2px dashed #ef4444", "borderRadius": "6px",
        "fontSize": "12px", "padding": "8px 12px",
    },
}
_COVERAGE_ICON = {
    "uncovered": "○", "in_progress": "◌", "covered": "●", "partial": "◑",
    "missing_skill": "⊘",
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
    context_graph: dict,
    dag: dict,
    artefacts: dict,
    blocked_skill_items: set[str] | None = None,
) -> StreamlitFlowState:
    coverage = _work_item_coverage(dag, artefacts)
    blocked_skill_items = blocked_skill_items or set()
    nodes = []
    for item in context_graph.get("nodes", []):
        node_type = item.get("node_type", "work_item")
        if node_type == "phase":
            nodes.append(StreamlitFlowNode(
                id=item["id"],
                pos=(0, 0),
                data={"label": f"▣  {item['name']}"},
                node_type="default",
                style=_PHASE_NODE_STYLE,
                source_position="bottom",
                target_position="top",
                selectable=False,
            ))
            continue

        wid = item["id"]
        if wid in blocked_skill_items:
            cov_status, conf = "missing_skill", 0.0
        else:
            cov_status, conf = coverage.get(wid, ("uncovered", 0.0))
        icon = _COVERAGE_ICON[cov_status]
        label_parts = [f"{icon}  {item['name']}"]
        if cov_status == "missing_skill":
            skills = item.get("required_skills", [])
            if skills:
                label_parts.append(f"needs: {', '.join(skills)}")
        elif cov_status != "uncovered":
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


def _render_phase_summaries(phase_summaries: list[dict], expanded: bool = False):
    """Render phase synthesis panels — one expander per completed phase."""
    if not phase_summaries:
        return
    st.markdown("**Phase Summaries**")
    for ps in phase_summaries:
        conf = ps.get("mean_confidence", 0.0)
        covered = len(ps.get("covered_item_ids", []))
        partial = len(ps.get("partial_item_ids", []))
        uncovered = len(ps.get("uncovered_item_ids", []))
        header = (
            f"{ps['phase_name']} — conf: {conf:.2f}  "
            f"({covered} covered · {partial} partial · {uncovered} uncovered)"
        )
        with st.expander(header, expanded=expanded):
            synthesis = ps.get("synthesis", "")
            if synthesis:
                st.write(synthesis)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Confidence", f"{conf:.2f}")
            c2.metric("Covered", covered)
            c3.metric("Partial", partial)
            c4.metric("Uncovered", uncovered)
            tokens = ps.get("total_tokens", 0)
            if tokens:
                st.caption(f"Tokens used: {tokens:,}")


def _extract_file_content(uploaded_file) -> str:
    """Extract text from an uploaded PDF or CSV file."""
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        import pdfplumber
        import io
        text_parts = []
        with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        return "\n\n".join(text_parts) if text_parts else "(no text found in PDF)"
    elif name.endswith(".csv"):
        import pandas as pd
        import io
        df = pd.read_csv(io.BytesIO(uploaded_file.read()))
        rows, cols = df.shape
        preview = df.head(20).to_string(index=False)
        return f"CSV with {rows} rows × {cols} columns:\n\n{preview}"
    else:
        return uploaded_file.read().decode("utf-8", errors="replace")


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
        "latest_viability": None,
        "phase_summaries": [],
        "processed_attachments": set(),
        "graph_review_mode": False,
        "pending_run_id": None,
        "graph_pending_model": None,
        "graph_review_messages": [],
        "graph_review_history": [],
        "conversation_messages": [],   # {role, content, timestamp} — display + persistence
        "conversation_history": [],    # pydantic-ai message history — current session only
        "conversation_run_id": None,   # which run the conversation is scoped to
        "dig_deeper_prior_run_id": None,  # set when "Dig deeper" was clicked
        "swarm_launching": False,         # True between click and actual subprocess launch
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
    st.session_state.phase_summaries = []
    st.session_state.graph_review_mode = False
    st.session_state.pending_run_id = None
    st.session_state.graph_pending_model = None
    st.session_state.graph_review_messages = []
    st.session_state.graph_review_history = []
    st.session_state.dig_deeper_prior_run_id = None


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
    st.session_state.latest_viability = store.read_live("viability.json", None)
    st.session_state.phase_summaries = store.read_live("phase_summaries.json", [])
    st.session_state.research_log = store.read_live_log()
    st.session_state.conversation_messages = store.read_conversation()
    st.session_state.conversation_history = []
    st.session_state.conversation_run_id = run_id
    st.session_state.flow_state = None
    st.session_state.context_graph_state = None
    st.session_state.current_run_id = None  # not an active run
    st.session_state.saved = True


# ── App ───────────────────────────────────────────────────────────────────────

init_state()

# Sidebar — saved projects
with st.sidebar:
    # ── Live run status (always visible while a run is active) ─────────────────
    if st.session_state.current_run_id:
        from slow_ai.execution.git_store import GitStore as _SidebarGS
        _sb_store = _SidebarGS(st.session_state.current_run_id)
        _sb_status_data = _sb_store.read_live("status.json", {"status": "initializing"})
        _sb_status = _sb_status_data.get("status", "initializing")
        _sb_log = _sb_store.read_live_log()
        _sb_summaries = _sb_store.read_live("phase_summaries.json", [])

        st.markdown("**⚡ Agent Swarm Running**")
        _badge = {
            "initializing": "🔵 Initializing",
            "running": "🔵 Running",
            "completed": "🟢 Completed",
            "failed": "🔴 Failed",
            "waiting_for_human": "🟡 Waiting",
            "blocked_on_capabilities": "🟠 Blocked",
        }
        st.caption(_badge.get(_sb_status, f"● {_sb_status}"))

        if _sb_summaries:
            st.caption(f"Phases done: {len(_sb_summaries)}")
            latest = _sb_summaries[-1]
            st.caption(f"Last: {latest['phase_name']} (conf {latest.get('mean_confidence', 0):.2f})")

        if _sb_log:
            st.caption(_sb_log[-1])

        st.divider()

    st.header("Projects")
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
        if st.button("Load Project", type="primary"):
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
                "blocked_on_capabilities": "🟠",
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
        brief_to_save = st.session_state.brief
        # Inject prior run ID if this is a "Dig deeper" follow-on
        if st.session_state.dig_deeper_prior_run_id:
            prior = st.session_state.dig_deeper_prior_run_id
            existing = brief_to_save.prior_run_ids or []
            if prior not in existing:
                brief_to_save = brief_to_save.model_copy(
                    update={"prior_run_ids": existing + [prior]}
                )
            st.session_state.dig_deeper_prior_run_id = None
        path, project_id = save_brief(brief_to_save)
        st.session_state.brief = brief_to_save
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

# ── Workflow area ──────────────────────────────────────────────────────────────

if st.session_state.saved:
    # ── Pending launch — processed before any UI is rendered ───────────────────
    # swarm_launching is set by the Launch button click. Handling it here (before
    # any st.xxx calls) means the transition render produces no UI output — the
    # browser goes straight from the graph-review render to the live-panel render,
    # with no window where the button can be clicked again.
    if st.session_state.swarm_launching:
        _launch_run_id = _start_research(
            st.session_state.brief,
            st.session_state.current_project_id,
            run_id=st.session_state.pending_run_id,
            approved_graph=st.session_state.graph_pending_model,
        )
        st.session_state.swarm_launching = False
        st.session_state.current_run_id = _launch_run_id
        st.session_state.graph_review_mode = False
        st.session_state.pending_run_id = None
        st.session_state.graph_pending_model = None
        st.session_state.graph_review_messages = []
        st.session_state.dag = None
        st.session_state.agent_artefacts = {}
        st.session_state.flow_state = None
        st.session_state.flow_state_live = None
        st.session_state.context_graph_state = None
        st.session_state.context_graph_state_live = None
        st.session_state.latest_assessment = None
        st.session_state.phase_summaries = []
        st.session_state.conversation_messages = []
        st.session_state.conversation_history = []
        st.session_state.conversation_run_id = None
        st.rerun()

    st.success("Brief confirmed and saved.")
    st.divider()

    # ── Graph review (HITL) ────────────────────────────────────────────────────
    if st.session_state.graph_review_mode:
        st.subheader("Workflow Design")
        st.caption("Review the workflow below. Chat to refine it, then launch when ready.")

        # Context graph preview
        cg = st.session_state.context_graph
        if cg and cg.get("nodes"):
            if st.session_state.context_graph_state is None:
                st.session_state.context_graph_state = _build_context_graph_state(
                    cg, {"nodes": [], "edges": []}, {}, set()
                )
            streamlit_flow(
                "cg_review",
                st.session_state.context_graph_state,
                layout=TreeLayout(direction="down"),
                fit_view=True,
                height=380,
            )

        # Graph review chat
        for msg in st.session_state.graph_review_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        graph_input = st.chat_input("Describe what you'd like to change…")

        if graph_input:
            st.session_state.graph_review_messages.append(
                {"role": "user", "content": graph_input}
            )
            with st.spinner("Updating workflow…"):
                reply = _refine_graph(graph_input)
            st.session_state.graph_review_messages.append(
                {"role": "assistant", "content": reply}
            )
            st.rerun()

        if st.button("Launch Agent Swarm ⚡", type="primary"):
            # Set the flag — the top-of-page handler (above) will process it on
            # the very next render before any UI is drawn, so the button is gone
            # before the user can click again.
            st.session_state.swarm_launching = True
            st.rerun()

    # ── Plan / re-plan trigger ─────────────────────────────────────────────────
    elif not st.session_state.current_run_id:
        if not st.session_state.report:
            display_brief(st.session_state.brief)
            st.divider()
            if st.button("Plan Workflow", type="primary"):
                with st.spinner("Designing your workflow…"):
                    _plan_workflow(
                        st.session_state.brief,
                        st.session_state.current_project_id,
                    )
                st.rerun()
        else:
            # Post-run continuation actions
            st.divider()
            st.markdown("**Continue this research:**")
            col_finish, col_deeper, col_new = st.columns(3)

            if col_finish.button("Do what we didn't finish", type="primary"):
                from slow_ai.agents.orchestrator import generate_follow_on_brief
                report = st.session_state.report
                phase_summaries = st.session_state.phase_summaries or []
                with st.spinner("Analysing gaps and planning follow-on workflow…"):
                    loop = asyncio.get_event_loop()
                    follow_on = loop.run_until_complete(
                        generate_follow_on_brief(
                            st.session_state.brief,
                            phase_summaries,
                            report.run_id,
                        )
                    )
                    path, project_id = save_brief(follow_on)
                    st.session_state.brief = follow_on
                    st.session_state.saved = True
                    st.session_state.current_project_id = project_id
                    st.session_state.report = None
                    st.session_state.conversation_messages = []
                    st.session_state.conversation_history = []
                    st.session_state.conversation_run_id = None
                    st.session_state.phase_summaries = []
                    with st.spinner("Designing follow-on workflow…"):
                        _plan_workflow(follow_on, project_id)
                st.rerun()

            if col_deeper.button("Dig deeper"):
                prior_run_id = st.session_state.report.run_id
                st.session_state.dig_deeper_prior_run_id = prior_run_id
                st.session_state.messages = [{
                    "role": "assistant",
                    "content": (
                        "Let's plan a deeper investigation, building on what was found. "
                        "Describe the direction you'd like to explore further — "
                        "the previous run's findings will be available to all agents."
                    ),
                }]
                st.session_state.history = []
                st.session_state.brief = None
                st.session_state.saved = False
                st.session_state.report = None
                st.session_state.conversation_messages = []
                st.session_state.conversation_history = []
                st.session_state.phase_summaries = []
                st.rerun()

            if col_new.button("Plan a New Workflow"):
                st.session_state.report = None
                with st.spinner("Designing your workflow…"):
                    _plan_workflow(
                        st.session_state.brief,
                        st.session_state.current_project_id,
                    )
                st.rerun()

    # ── Agent Swarm live view ──────────────────────────────────────────────────
    if st.session_state.current_run_id:
        st.subheader("Agent Swarm")

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
                st.session_state.latest_viability = store.read_live("viability.json", None)
                st.session_state.phase_summaries = store.read_live("phase_summaries.json", [])
                st.session_state.research_log = store.read_live_log()
                st.session_state.conversation_messages = store.read_conversation()
                st.session_state.conversation_history = []
                st.session_state.conversation_run_id = run_id
                st.session_state.current_run_id = None
                st.session_state.flow_state = None
                st.session_state.flow_state_live = None
                st.session_state.context_graph_state = None
                st.session_state.context_graph_state_live = None
                st.rerun(scope="app")
                return

            if status == "failed":
                error = status_data.get("error", "unknown error")
                st.error(f"Agent swarm failed: {error}")
                if st.button("Reset", key="reset_btn"):
                    st.session_state.current_run_id = None
                    st.rerun()
                return

            if status == "blocked_on_capabilities":
                st.warning("Run blocked — skill gaps must be resolved before this run can proceed.")
                checkpoint = store.read_live("capability_checkpoint.json", {})
                if checkpoint:
                    st.markdown(f"**Reason:** {checkpoint.get('reasoning', '')}")
                    gaps = checkpoint.get("gaps", [])
                    if gaps:
                        st.markdown("**Missing skills:**")
                        for g in gaps:
                            critical = " *(critical path)*" if g.get("is_critical_path") else ""
                            st.markdown(
                                f"- `{g['skill']}` — needed by {g['required_by']}, "
                                f"blocks {g['downstream_blocked']} item(s){critical}"
                            )

                # Show the context graph even when blocked — it's the most useful
                # thing to have visible when diagnosing what's missing and why
                cg = store.read_live("context_graph.json", None)
                if cg and cg.get("nodes"):
                    st.subheader("Context Graph")
                    viability = store.read_live("viability.json", None)
                    blocked_items = set(viability.get("blocked_work_items", [])) if viability else set()
                    if (
                        st.session_state.context_graph_state_live is None
                        or len(st.session_state.context_graph_state_live.nodes) != len(cg["nodes"])
                    ):
                        st.session_state.context_graph_state_live = _build_context_graph_state(
                            cg, {"nodes": [], "edges": []}, {}, blocked_items
                        )
                    streamlit_flow(
                        "cg_blocked",
                        st.session_state.context_graph_state_live,
                        layout=TreeLayout(direction="down"),
                        fit_view=True,
                        height=350,
                    )

                if st.button("Reset", key="reset_cap_btn"):
                    st.session_state.current_run_id = None
                    st.session_state.context_graph_state_live = None
                    st.rerun()
                return

            # ── Project brief ──────────────────────────────────────────────────
            brief = st.session_state.brief
            if brief:
                with st.expander(f"Project Brief — {brief.goal[:80]}", expanded=False):
                    st.markdown(f"**Goal:** {brief.goal}")
                    st.markdown(f"**Domain:** {brief.domain}")
                    if brief.success_criteria:
                        st.markdown("**Success criteria:** " + " · ".join(brief.success_criteria))
                    if brief.constraints:
                        st.json(brief.constraints)

            # ── Context graph ──────────────────────────────────────────────────
            cg = store.read_live("context_graph.json", None)
            if cg and cg.get("nodes"):
                st.subheader("Context Graph")
                viability = store.read_live("viability.json", None)
                blocked_items = set((viability or {}).get("blocked_work_items", [])) if viability else set()
                dag_for_cg = store.read_live("dag.json", {"nodes": [], "edges": []})
                artefacts_for_cg = store.read_live("artefacts.json", {})
                current_cg_live = st.session_state.context_graph_state_live
                if (
                    current_cg_live is None
                    or len(current_cg_live.nodes) != len(cg["nodes"])
                ):
                    st.session_state.context_graph_state_live = _build_context_graph_state(
                        cg, dag_for_cg, artefacts_for_cg, blocked_items
                    )
                streamlit_flow(
                    "cg_live",
                    st.session_state.context_graph_state_live,
                    layout=TreeLayout(direction="down"),
                    fit_view=True,
                    height=380,
                )
            else:
                viability = None

            # ── Agent DAG ──────────────────────────────────────────────────────
            st.subheader("Agent Swarm")
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

            st.divider()

            # ── Progress log ──────────────────────────────────────────────────
            log = store.read_live_log()
            st.caption(f"● {status}")
            if log:
                st.markdown("\n".join(f"- {m}" for m in log))
            else:
                st.caption("Starting up…")

            # ── Phase summaries (live) ─────────────────────────────────────────
            live_phase_summaries = store.read_live("phase_summaries.json", [])
            if live_phase_summaries:
                _render_phase_summaries(live_phase_summaries, expanded=False)

            # ── Latest orchestrator assessment ─────────────────────────────────
            assessment = store.read_live("assessment.json", None)
            if assessment:
                phase_label = assessment.get("phase_id", "?")
                with st.expander(
                    f"Phase {phase_label} assessment — {assessment.get('action', '?')}",
                    expanded=False,
                ):
                    ac, pc, ec = st.columns(3)
                    ac.metric("Covered", len(assessment.get("work_items_covered", [])))
                    pc.metric("Partial", len(assessment.get("work_items_partial", [])))
                    ec.metric("Uncovered", len(assessment.get("work_items_uncovered", [])))
                    st.caption(assessment.get("reasoning", ""))
                    if assessment.get("circuit_break_reason"):
                        st.error(f"Circuit break: {assessment['circuit_break_reason']}")

            # ── Skill synthesis results ────────────────────────────────────────
            synthesis = store.read_live("synthesis.json", None)
            if synthesis:
                synth_count = len(synthesis.get("synthesized", []))
                unresolved = synthesis.get("needs_new_tool", [])
                queries = synthesis.get("github_search_queries", [])
                with st.expander(
                    f"Skill synthesis — {synth_count} synthesized, {len(unresolved)} unresolved",
                    expanded=False,
                ):
                    if synthesis.get("synthesized"):
                        st.markdown("**Synthesized (added to registry):**")
                        for s in synthesis["synthesized"]:
                            st.markdown(f"- `{s['name']}` → tools: {s['tools']}")
                    if unresolved:
                        st.markdown("**Needs new tool:**")
                        for name in unresolved:
                            st.markdown(f"- `{name}`")
                    if queries:
                        st.markdown("**Suggested GitHub searches:**")
                        for q in queries:
                            st.markdown(f"- {q}")
                    st.caption(synthesis.get("reasoning", ""))

            # ── Viability decision ─────────────────────────────────────────────
            if viability is None:
                viability = store.read_live("viability.json", None)
            if viability and viability.get("action") in ("degraded", "no_go"):
                action = viability["action"]
                gaps = viability.get("skill_gaps", [])
                label = "Degraded run" if action == "degraded" else "Blocked — no_go"
                with st.expander(f"{label} — {len(gaps)} skill gap(s)", expanded=(action == "no_go")):
                    st.caption(viability.get("reasoning", ""))
                    for g in gaps:
                        critical = " *(critical path)*" if g.get("is_critical_path") else ""
                        st.markdown(
                            f"- `{g['skill']}` — needed by {g['required_by']}, "
                            f"blocks {g['downstream_blocked']} item(s){critical}"
                        )

            # Keep sidebar in sync — trigger full page rerun on the same 5s cycle
            st.rerun(scope="app")

        _live_panel()

    # Report view — shown after a run completes
    if st.session_state.report:
        report = st.session_state.report
        from slow_ai.execution.git_store import GitStore
        from slow_ai.agents.run_conversation import run_conversation_turn

        # Ensure conversation state is scoped to this run
        if st.session_state.conversation_run_id != report.run_id:
            _conv_store = GitStore(run_id=report.run_id)
            st.session_state.conversation_messages = _conv_store.read_conversation()
            st.session_state.conversation_history = []
            st.session_state.conversation_run_id = report.run_id

        tab_chat, tab_evidence, tab_report, tab_log = st.tabs([
            "💬 Conversation", "📊 Evidence", "📋 Report", "📝 Log"
        ])

        # ── Tab 1: Conversation ────────────────────────────────────────────────
        with tab_chat:
            st.caption(
                "Ask about what the agents found, why confidence was low, what was "
                "uncovered, or request a specific artefact. No new agents are spawned."
            )
            for msg in st.session_state.conversation_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            conv_input = st.chat_input("Ask about the run…")
            if conv_input:
                _conv_store = GitStore(run_id=report.run_id)
                _conv_store.append_conversation("user", conv_input)
                st.session_state.conversation_messages.append(
                    {"role": "user", "content": conv_input}
                )
                with st.spinner("Reading evidence…"):
                    response, updated_history = run_conversation_turn(
                        conv_input,
                        report.run_id,
                        st.session_state.conversation_history,
                    )
                _conv_store.append_conversation("assistant", response)
                st.session_state.conversation_messages.append(
                    {"role": "assistant", "content": response}
                )
                st.session_state.conversation_history = updated_history
                st.rerun()

        # ── Tab 2: Evidence ────────────────────────────────────────────────────
        with tab_evidence:
            # Viability warning
            viability = st.session_state.latest_viability
            if viability and viability.get("action") in ("degraded", "no_go"):
                action = viability["action"]
                gaps = viability.get("skill_gaps", [])
                with st.expander(
                    f"Skill gaps — {action} run ({len(gaps)} missing skill(s))",
                    expanded=False,
                ):
                    st.caption(viability.get("reasoning", ""))
                    for g in gaps:
                        critical = " *(critical path)*" if g.get("is_critical_path") else ""
                        st.markdown(
                            f"- `{g['skill']}` — needed by {g['required_by']}, "
                            f"blocks {g['downstream_blocked']} item(s){critical}"
                        )

            # Assessment
            assessment = st.session_state.latest_assessment
            if assessment:
                ac, pc, ec = st.columns(3)
                ac.metric("Covered", len(assessment.get("work_items_covered", [])))
                pc.metric("Partial", len(assessment.get("work_items_partial", [])))
                ec.metric("Uncovered", len(assessment.get("work_items_uncovered", [])))
                phase_label = assessment.get("phase_id", "?")
                st.caption(f"Final action: **{assessment.get('action', '?')}** — phase {phase_label}")
                if assessment.get("circuit_break_reason"):
                    st.error(f"Circuit break: {assessment['circuit_break_reason']}")
                with st.expander("Assessment reasoning"):
                    st.write(assessment.get("reasoning", ""))

            # Agent DAG
            dag = st.session_state.dag or {"nodes": [], "edges": []}
            if dag.get("nodes"):
                st.subheader("Agent DAG")
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
                        new_state.selected_id, dag, st.session_state.agent_artefacts
                    )

            # Phase summaries — after DAG
            _render_phase_summaries(st.session_state.phase_summaries or [], expanded=False)

            # Context graph
            cg = st.session_state.context_graph
            if cg and cg.get("nodes"):
                st.subheader("Workflow Graph")
                dag_final = st.session_state.dag or {"nodes": [], "edges": []}
                artefacts_final = st.session_state.agent_artefacts or {}
                blocked_final = set((viability or {}).get("blocked_work_items", []))
                if (
                    st.session_state.context_graph_state is None
                    or len(st.session_state.context_graph_state.nodes) != len(cg["nodes"])
                ):
                    st.session_state.context_graph_state = _build_context_graph_state(
                        cg, dag_final, artefacts_final, blocked_final
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
                        (n for n in cg["nodes"] if n["id"] == new_cg_state.selected_id), None
                    )
                    if selected:
                        st.divider()
                        st.subheader(f"Work Item — {selected['name']}")
                        st.write(selected["description"])
                        if selected.get("required_skills"):
                            skill_labels = []
                            for s in selected["required_skills"]:
                                marker = " ⊘" if selected["id"] in blocked_final else ""
                                skill_labels.append(f"`{s}`{marker}")
                            st.markdown("**Required skills:** " + "  ·  ".join(skill_labels))
                        covering = [
                            n for n in dag_final.get("nodes", [])
                            if n.get("work_item_id") == selected["id"]
                        ]
                        if covering:
                            st.markdown(
                                "**Agents:** "
                                + "  ·  ".join(
                                    f"`{n['id'].split('-')[-1]}` ({n['type']})"
                                    for n in covering
                                )
                            )

        # ── Tab 3: Report ──────────────────────────────────────────────────────
        with tab_report:
            st.subheader("Summary")
            st.write(report.summary)
            st.subheader("Outputs")
            for ds in report.datasets:
                with st.expander(f"{ds.name} — quality: {ds.quality_score:.2f}"):
                    st.json(ds.model_dump())

        # ── Tab 4: Log ─────────────────────────────────────────────────────────
        with tab_log:
            st.caption("Run log")
            for msg in st.session_state.research_log:
                st.markdown(f"- {msg}")
            st.divider()
            st.caption("Git commits")
            store = GitStore(run_id=report.run_id)
            for entry in store.get_log():
                st.text(f"{entry['sha']}  {entry['message']}  {entry['timestamp']}")

# Chat input — only during the interview phase
if not st.session_state.saved:
    # File attachment
    uploaded = st.file_uploader(
        "Attach a file for context (PDF or CSV)",
        type=["pdf", "csv"],
        key="file_uploader",
        label_visibility="collapsed",
        help="Attach a PDF or CSV to give the interviewer additional context",
    )
    if uploaded and uploaded.name not in st.session_state.processed_attachments:
        st.session_state.processed_attachments.add(uploaded.name)
        try:
            content = _extract_file_content(uploaded)
            attachment_msg = (
                f"I'm attaching a file for context: **{uploaded.name}**\n\n"
                f"```\n{content[:4000]}\n```"
                + ("*(truncated)*" if len(content) > 4000 else "")
            )
            st.session_state.messages.append({"role": "user", "content": attachment_msg})
            response = call_agent(attachment_msg)
            if isinstance(response, ProblemBrief):
                st.session_state.brief = response
            else:
                st.session_state.messages.append({"role": "assistant", "content": response})
        except Exception as e:
            st.error(f"Could not read {uploaded.name}: {e}")
        st.rerun()

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
