# React Migration Spec

Migration plan for replacing the Streamlit UI with a React + FastAPI frontend.
The execution plane (`src/slow_ai/`) is untouched — only the rendering layer changes.

---

## Why

Streamlit's render model (full script re-run on every state change) is fundamentally
at odds with what this app needs:

| Problem in Streamlit | Native in React |
|---|---|
| Page jumps on state transitions | React Router — smooth navigation, no re-render |
| 5s polling lag and visual jitter | SSE push — instant updates |
| Cannot scroll to a position after rerun | Full browser control |
| Context graph and DAG re-render together, causing stacking | Components mount/unmount independently |
| Button disable requires two-render workaround | `useState` — trivial |
| Session state lost on page refresh | Browser localStorage / URL params |
| Fragment polling causes layout instability | SSE stream replaces fragments entirely |

---

## Architectural Principle

The execution plane already writes all state as JSON files to `runs/{run_id}/live/`.
The React frontend needs only a thin API layer that:

1. Proxies file reads and writes
2. Launches subprocesses
3. Streams live file changes as SSE events
4. Wraps pydantic-ai agents behind POST endpoints

No logic moves from Python to JavaScript. The intelligence stays in Python.

---

## Repository Structure

```
slow_ai/
  src/slow_ai/              ← unchanged — execution plane
    agents/
    tools/
    research/
    execution/
    skills/
    llm/
    models.py
    config.py

  api/                      ← new: FastAPI server (~400 lines)
    main.py                 ← app factory, CORS, mounts routers
    routes/
      projects.py           ← GET /projects, POST /projects
      runs.py               ← GET /runs/{id}/*, POST /runs/{id}/launch
      interview.py          ← POST /interview (streaming)
      graph.py              ← POST /graph/plan, POST /graph/refine
      conversation.py       ← POST /conversation/{run_id}/turn
    sse.py                  ← GET /runs/{id}/stream — SSE live updates
    deps.py                 ← shared FastAPI dependencies

  frontend/                 ← new: React + Vite + TypeScript
    package.json
    vite.config.ts
    src/
      main.tsx
      App.tsx               ← React Router root
      pages/
        Interview.tsx       ← chat-style brief elicitation
        GraphReview.tsx     ← context graph + chat + launch button
        LiveRun.tsx         ← SSE-driven live view
        PostRun.tsx         ← tabbed: Conversation / Evidence / Report / Log
        Projects.tsx        ← project list + run history sidebar
      components/
        ContextGraph.tsx    ← ReactFlow, phase + work item nodes
        AgentDag.tsx        ← ReactFlow, live agent tree
        ConversationPanel.tsx
        PhaseCard.tsx       ← phase summary expander
        BriefDisplay.tsx
        StatusBadge.tsx
      hooks/
        useRunStream.ts     ← SSE connection, pushes live state updates
        useGraph.ts         ← graph state + mutation helpers
        useInterview.ts     ← streaming chat with interviewer agent
      api/
        client.ts           ← typed fetch wrappers for all endpoints
      types/
        models.ts           ← TypeScript types mirroring pydantic models

  docs/
    technical.md
    react_migration.md      ← this file
```

---

## API Design

### Projects

```
GET  /projects
     → [{ project_id, goal, domain, created_at }]

POST /projects
     body: ProblemBrief
     → { project_id }
```

### Runs

```
GET  /runs?project_id={id}
     → [{ run_id, started_at, status }]

POST /runs/{run_id}/launch
     body: { brief, project_id, approved_graph? }
     → { run_id }

GET  /runs/{run_id}/live/{filename}
     → raw JSON of runs/{run_id}/live/{filename}

GET  /runs/{run_id}/stream
     → SSE stream: event: update, data: { file, content }
        fired whenever any live file changes (inotify / polling fallback)
```

### Interview

```
POST /interview
     body: { message, history }
     → SSE stream of tokens, final event: { type: "brief", data: ProblemBrief }
        or { type: "message", data: str }
```

### Graph

```
POST /graph/plan
     body: { brief, run_id, prior_context? }
     → { graph: ContextGraph, summary: str }

POST /graph/refine
     body: { brief, current_graph, feedback, run_id }
     → { graph: ContextGraph, summary: str }
```

### Conversation

```
POST /conversation/{run_id}/turn
     body: { message, history }
     → SSE stream of tokens, final event: { type: "done", response: str }
```

---

## SSE Live Update Design

The `useRunStream` hook opens a single SSE connection for an active run:

```typescript
// hooks/useRunStream.ts
export function useRunStream(runId: string) {
  const [state, setState] = useState<RunLiveState>({
    status: "initializing",
    dag: null,
    phaseSummaries: [],
    assessment: null,
    log: [],
  });

  useEffect(() => {
    const source = new EventSource(`/api/runs/${runId}/stream`);
    source.onmessage = (e) => {
      const { file, content } = JSON.parse(e.data);
      setState(prev => applyLiveUpdate(prev, file, content));
    };
    return () => source.close();
  }, [runId]);

  return state;
}
```

The server-side SSE endpoint watches `runs/{run_id}/live/` for file changes
(using `watchfiles` or polling) and pushes each changed file as an event.
No 5s timer — updates arrive as they happen.

---

## Page Designs

### Interview
- Chat interface (user message → streamed agent response)
- File upload for PDF/CSV context (drag-and-drop)
- When agent returns a `ProblemBrief`: renders structured brief preview with
  Confirm / Continue editing buttons
- On confirm: POST /projects → navigate to GraphReview

### GraphReview
- Left panel: ContextGraph (ReactFlow)
- Right panel: chat interface
- Opening message: the `generate_graph_summary` narrative
- Each refinement: POST /graph/refine → graph updates in place, new narrative
- Launch button: POST /runs/{id}/launch → navigate to LiveRun
  - Button disables immediately on click (trivial with useState)

### LiveRun
- Subscribes to SSE via `useRunStream`
- Top: status badge (colour-coded pill)
- Agent DAG: ReactFlow, updates as new nodes arrive via SSE
- Below DAG: scrollable progress log (new entries appear at bottom)
- Phase Summary cards appear as phases complete
- No polling, no re-renders of unrelated components
- On `status === "completed"`: navigate to PostRun

### PostRun
- Four tabs: Conversation / Evidence / Report / Log
- Conversation: starts with run summary message, then user input
  - Streamed responses via SSE
- Evidence: final DAG (click nodes → side panel with envelope/memory), context
  graph with coverage overlay, phase summaries
- Report: structured report and dataset quality scores
- Log: run log + git commit list

### Projects (sidebar / home)
- List of saved projects with goals
- Each project: list of historical runs with status badges
- Click run → navigate to PostRun for that run

---

## Technology Choices

| Layer | Choice | Reason |
|---|---|---|
| API server | FastAPI + Uvicorn | Already Python, SSE support, async native |
| Frontend framework | React + Vite + TypeScript | Industry standard, fast HMR, typed |
| Graph rendering | ReactFlow | Same library powering streamlit-flow-component |
| Routing | React Router v6 | Clean URL-based navigation |
| Styling | Tailwind CSS | Fast to iterate, dark mode trivial |
| SSE client | Native EventSource | No dependency needed |
| File watching (server) | watchfiles | Python, async, inotify on Linux |
| State management | useState + useContext | Complexity doesn't warrant Redux |
| HTTP client | native fetch + typed wrappers | No Axios needed for this scale |

---

## Migration Phases

### Phase 1 — API layer (2–3 days)
- FastAPI app with all routes listed above
- SSE endpoint with watchfiles
- All existing Streamlit logic ported to endpoint handlers
- Run Streamlit and FastAPI in parallel (Streamlit still works during transition)
- Integration tested against existing runs

### Phase 2 — Interview + Graph Review pages (3–4 days)
- Interview chat with streaming
- Brief confirmation view
- ContextGraph component (ReactFlow, matching current node styles)
- Graph review chat + launch flow
- Can test against live API

### Phase 3 — Live Run page (3–4 days)
- SSE hook
- AgentDag component (ReactFlow, live updates)
- Progress log
- Phase summary cards
- Status transitions → navigate to PostRun on completion

### Phase 4 — Post-Run pages (2–3 days)
- Conversation tab with streaming
- Evidence tab: DAG, context graph, phase summaries
- Report and Log tabs
- Historical run loading

### Phase 5 — Parity + cutover (2–3 days)
- Remove Streamlit from `main.py`
- Update `pyproject.toml` — remove streamlit deps
- Add `frontend/` build step to startup docs
- End-to-end test of full flow

**Total: ~2–3 weeks to full parity**

---

## What Stays Exactly the Same

- `src/slow_ai/` — every agent, tool, runner, model, registry
- `runs/{run_id}/` — file structure, git store, live files
- `output/{project_id}/` — project store
- `.env` configuration

The React migration is purely a rendering layer replacement.
The intelligence, the execution model, and the storage contract are untouched.

---

## Known Issues to Resolve During Migration

- `brief = None` after page refresh (fixed in Streamlit by loading from
  `input_brief.json` — React handles this natively via URL params)
- Context graph stacking during live run (non-issue in React — separate components)
- 5s polling lag (eliminated by SSE)
- No scroll control on state transition (full control in React)
