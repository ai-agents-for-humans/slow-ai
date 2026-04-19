# Slow AI V2 — Design Document

**Status:** Design phase — no code written yet.
**Scope:** Layered graph model, HITL throughout, memory architecture,
context graph repository, attachment support, post-run conversation.

---

## 1. Overview

V2 introduces human oversight at every meaningful decision point, not just at
failure escalations. It also introduces four accumulating repositories that
compound in value across runs. The system gets better not just because skills
grow, but because context graphs, evidence, and human feedback accumulate into
a corpus that informs every future run.

### The four repositories

| Repository | Lives at | What accumulates |
|---|---|---|
| **Context graphs** | `output/context_graphs/` | Every confirmed graph + brief + edits + outcomes |
| **Skills** | `src/slow_ai/skills/registry.json` | Synthesized skill → tool mappings |
| **Tools** | `src/slow_ai/tools/` + MCP (V2) | Concrete tool implementations |
| **Evidence runs** | `runs/{run_id}/` | Full git-committed run artefacts |

Human feedback is captured at multiple levels and linked across all four.

---

## 2. Layered Graph Model (Phase + WorkItems)

### The problem with the current model

The current model is a flat DAG of WorkItems connected by dependency edges.
Dependency order is inferred at runtime — which wave an item runs in is
computed, not declared. This makes the graph hard for humans to read and hard
to modify conversationally.

### The Compass pattern

Based on the Compass architecture: phases are explicit, named, and purposeful.
Each phase contains parallel work items. Phases depend on phases — not on
individual items. The structure maps naturally to how humans think about
structured work.

```
Phase A (e.g. "Explore")
  ├── WorkItem: map the landscape
  ├── WorkItem: identify key players
  └── WorkItem: surface known unknowns
        ↓  (all items in A complete before B starts)
Phase B (e.g. "Investigate")
  ├── WorkItem: deep dive on finding 1
  ├── WorkItem: deep dive on finding 2
  └── WorkItem: validate assumptions from Phase A
        ↓
Phase C (e.g. "Critique")
  ├── WorkItem: identify gaps in evidence
  ├── WorkItem: check confidence of key claims
  └── WorkItem: flag contradictions
        ↓
Phase D (e.g. "Synthesise")
  └── WorkItem: produce final output
```

The context planner designs phases, not just work items. Phase names and
purposes are domain-specific — they are not fixed. A due diligence run might
have phases named "Market Scan", "Financials", "Risk Assessment", "Red Flags".
A compliance run might have "Regulation Mapping", "Gap Analysis", "Remediation
Planning".

### New data model

```python
class Phase:
    id: str
    name: str                    # human-readable, domain-specific
    purpose: str                 # what this phase is trying to achieve
    work_items: list[WorkItem]   # all run in parallel within the phase
    depends_on_phases: list[str] # phase ids that must complete first
    synthesis_instruction: str   # how to combine work item outputs into
                                 # phase-level context for the next phase

class ContextGraph:
    goal: str
    phases: list[Phase]          # replaces flat work_items list
    # WorkItem structure unchanged — required_skills, success_criteria etc.
```

### Execution change

Current: `_ready_work_items(graph, covered)` computes items ready based on
individual dependency edges.

New: phases execute in topological order. Within each phase, all work items
run in parallel via `asyncio.gather()`. After all items in a phase complete,
a phase-level synthesis produces a `PhaseSummary` that becomes the upstream
context for the next phase. The orchestrator sees phase summaries, not raw
individual envelopes.

### Why this matters for HITL

When the human reviews the context graph, they review at the phase level.
"I want to add a competitor analysis phase before the synthesis" is a clear,
understandable instruction. "Add a node between node 7 and node 12" is not.
The phase model makes conversational graph editing tractable.

---

## 3. HITL Architecture — All Stages

### 3.1 Stage 1: Interview (existing + attachments)

User describes the work. Attachments can be uploaded. The interviewer
extracts key information from attachments and uses it to ask better follow-up
questions. The confirmed brief + all attachments are committed at `[init]`.

→ Covered in Section 5 (Attachment Support).

### 3.2 Stage 2: Graph Review (NEW)

After context planning, the run pauses at a new status: `awaiting_graph_approval`.

The UI shows:
- The generated context graph (phases + work items, rendered as before)
- A chat interface below it: "What would you like to change?"

The user can say things like:
- "Add a phase before synthesis that critiques the evidence quality"
- "Split the investigation phase — I want separate agents for financial data and market data"
- "Remove the competitor benchmarking phase, we don't need it"
- "The first phase should also look at regulatory filings"

A **graph editor agent** interprets the instruction and produces structured
`GraphEdit` operations. The graph is updated and re-rendered. The conversation
continues until the user confirms: "Looks good, proceed."

The confirmation event records:
- The original generated graph
- All edits made (structured diffs)
- The final confirmed graph
- Timestamp and any written rationale

This record is the first RL training data point: `(brief, original_graph,
human_edits, confirmed_graph)`. A graph that needed many edits is a signal
that the context planner got the planning wrong. A graph that was confirmed
immediately is a signal that it got it right.

**Memory for graph review conversation:**

```
context = {
    brief: ProblemBrief (full),
    graph: ContextGraph (full, as structured JSON + human-readable summary),
    conversation: list[{role, content}]   # rolling, all messages kept
}
output = GraphEdit operations (structured)
storage = runs/{run_id}/live/graph_review.jsonl (live)
         committed at confirmation as part of [M-1-context]
```

The graph editor agent does not need tools. Its output type is a list of
`GraphEdit` operations that the runner applies deterministically. The runner
re-renders the graph and writes it back to `live/context_graph.json` so the
UI reflects the change immediately.

**GraphEdit operations:**
```python
class AddPhase(BaseModel):
    after_phase_id: str | None   # None = add at end
    name: str
    purpose: str
    work_items: list[WorkItemSpec]

class RemovePhase(BaseModel):
    phase_id: str

class ModifyPhase(BaseModel):
    phase_id: str
    name: str | None = None
    purpose: str | None = None

class AddWorkItem(BaseModel):
    phase_id: str
    name: str
    description: str
    required_skills: list[str]

class RemoveWorkItem(BaseModel):
    work_item_id: str

class ModifyWorkItem(BaseModel):
    work_item_id: str
    name: str | None = None
    description: str | None = None
    required_skills: list[str] | None = None

GraphEdit = AddPhase | RemovePhase | ModifyPhase | AddWorkItem | RemoveWorkItem | ModifyWorkItem
```

**Phase synthesis design decision:** synthesis always runs at every phase
boundary. The `PhaseSummary` includes both the synthesised narrative AND the
raw evidence envelopes from all work items in that phase. The next phase's
agents receive the synthesis as their upstream context, but the envelopes are
preserved in full — every claim in the synthesis can be traced back to a
specific envelope.

**Phase boundary as circuit breaker:** every phase boundary is a natural
circuit breaker point. Before the next phase starts, check: cumulative cost
within budget? mean confidence above floor? orchestrator assessment coherent?
If any threshold is breached, the circuit opens at the boundary — the run
pauses or stops cleanly rather than mid-phase. This is cleaner than the
current mid-wave detection and maps directly to the MAPE-K observer. Blast
radius reduction beyond per-agent tool scoping is still an open design
question for a later iteration.

### 3.3 Stage 3: Wave Gates (enhanced existing)

Currently: `escalate_to_human` writes a checkpoint but does not block.
V2: each phase boundary is a potential HITL gate.

The orchestrator, after completing a phase, can decide:
- `proceed` — next phase starts immediately
- `checkpoint` — pause for human review of this phase's output

At a checkpoint, the UI shows the phase summary + all evidence envelopes from
that phase + a chat interface. The human can:
- Approve: "Proceed"
- Inject context: "Before the next phase, also consider X"
- Correct: "The finding about Y is wrong — the correct figure is Z"
- Redirect: "Skip the next phase, go straight to synthesis"

The human response is committed to git as a `HumanCheckpoint` record before
the next phase starts. This becomes part of the RL training corpus — what did
the human choose to correct or add at this point?

### 3.4 Stage 4: Post-Run Conversation (NEW)

After the run completes, the report view gains a persistent chat interface.

**What the conversation agent can access:**
- The confirmed brief
- The final synthesis report (full)
- An index of all evidence envelopes (agent, phase, one-line summary, confidence)
- An index of all artefacts (filename, type, which agent produced it)

**Tools available to the conversation agent:**
```python
read_envelope(agent_id: str) -> EvidenceEnvelope
    # lazy-loads a specific agent's full evidence from git

read_artefact(filename: str) -> str
    # reads a specific artefact file from git

search_evidence(query: str) -> list[EnvelopeSummary]
    # searches across all evidence by keyword/topic
```

**What it can answer:**
- "What were the primary sources for the market sizing claim?"
- "Show me everything the code agent produced"
- "What was the confidence on the competitive analysis?"
- "What did the agents find about X that didn't make it into the final report?"
- "What would change if we assumed Y instead of Z?" (re-synthesises from existing evidence)

**What it cannot do (V2):**
- Spawn new agents for deeper investigation (V3)
- Modify the run's git history

**Memory model:**
```
context = {
    brief: ProblemBrief,
    report: ResearchReport,
    envelope_index: list[EnvelopeSummary],   # lightweight, always in context
    artefact_index: list[ArtefactSummary],   # lightweight, always in context
    conversation: list[{role, content}]      # rolling window: last 20 + summary
}
storage = runs/{run_id}/conversation.jsonl   # appended live, not committed to git
         (conversation is ephemeral within a session — not part of the audit trail)
```

The conversation is stored but not committed. It is session-scoped. If the user
returns to a completed run, the conversation picks up from where it left off
(read from the jsonl) but the underlying evidence is always re-read from git.

---

## 4. Context Graph Repository

### Purpose

Instead of generating a fresh context graph on every run, the system:
1. Stores every confirmed context graph
2. At graph generation time, finds similar past graphs and shows outcomes
3. Accumulates human feedback (edits, approval, post-run ratings) per graph
4. This becomes the training corpus for V3 RL on planning strategy

### Schema

```python
class ContextGraphRecord:
    id: str                          # uuid
    brief_summary: str               # 2-3 sentence summary for display
    brief_embedding: list[float]     # for similarity search
    graph_embedding: list[float]     # for similarity search
    original_graph: ContextGraph     # what the planner produced
    confirmed_graph: ContextGraph    # what the human approved
    edits: list[GraphEdit]           # what changed and why
    edit_count: int                  # signal: 0 = planner got it right
    confirmed_at: str                # ISO timestamp
    run_ids: list[str]               # runs that used this graph
    outcomes: list[GraphOutcome]     # linked after runs complete

class GraphOutcome:
    run_id: str
    coverage_ratio: float            # what % of work items were executed
    mean_confidence: float           # average confidence across envelopes
    human_rating: int | None         # 1-5 explicit post-run rating
    post_run_edit_count: int         # how many times user used post-run chat
    viability_action: str            # go / degraded / no_go
```

### Storage

```
output/
  context_graphs/
    index.jsonl           ← one line per record (lightweight fields only)
    {id}/
      record.json         ← full ContextGraphRecord
      original_graph.json
      confirmed_graph.json
      edits.jsonl
```

### Similarity at graph review time

When a new context graph is generated and shown for review, the UI also shows
a panel: "Similar past graphs":

```
  ┌────────────────────────────────────────────────────────┐
  │  Similar past graphs                                   │
  │                                                        │
  │  ● Due diligence: FinTech acquisition (3 weeks ago)    │
  │    6 phases · coverage 94% · confidence 0.81 · ★ 4/5  │
  │    0 edits at review — planner got it right            │
  │                                                        │
  │  ● Market sizing: B2B SaaS (6 weeks ago)               │
  │    5 phases · coverage 78% · confidence 0.71 · ★ 3/5  │
  │    4 edits — added competitor benchmarking phase       │
  └────────────────────────────────────────────────────────┘
```

The user can say "Use the structure from the FinTech acquisition run" and the
graph editor agent will apply the phase structure from that past graph to the
current brief.

### Similarity algorithm (V2 — simple)

Brief embedding similarity using cosine distance. No graph structure matching
yet (that's V3). Embeddings computed using the `fast` model at graph generation
time. Stored in the record. At query time, compare against all indexed embeddings
and return top 3.

---

## 5. Attachment Support (PDFs and CSVs)

### Interview flow

The user uploads a file during the interview. The interviewer agent:
1. Acknowledges the file
2. A background step extracts and summarises the content
3. The summary is injected into the interviewer's context
4. The interviewer uses the content to ask better follow-up questions
5. The final brief includes an `attachments` field with references

The user does not need to describe the file — the system reads it.

### Data model

```python
class Attachment:
    filename: str
    type: Literal["pdf", "csv"]
    summary: str               # produced by fast model, ~300 words
    key_facts: list[str]       # bullet points extracted, used in brief context
    path: str                  # relative path within brief_attachments/

class ProblemBrief:
    # ... existing fields ...
    attachments: list[Attachment] = []
```

### Ingestion pipeline

**PDF:**
```
upload → extract text (pdfplumber) → chunk if > 4K words
       → fast model: "summarise this document and extract key facts
          relevant to a research/analysis brief"
       → Attachment(summary=..., key_facts=[...])
```

**CSV:**
```
upload → pandas read_csv → describe schema (column names, types, row count,
         sample 5 rows) → fast model: "describe what this dataset contains
         and what analytical questions it could answer"
       → Attachment(summary=..., key_facts=[...])
```

### Storage

```
runs/{run_id}/
  brief_attachments/
    {filename}          ← original file, committed at [init]
    {filename}.summary  ← extracted summary, committed at [init]
```

Attachments are committed as part of `[init]` alongside `problem_brief.json`.
Specialist agents that need attachment content receive the `key_facts` in their
context. If they need the full summary, they can read it via a `read_attachment`
tool (same pattern as post-run conversation's `read_envelope`).

---

## 6. Memory Summary

| Stage | Memory in context | Rolling window | Stored where |
|---|---|---|---|
| Interview | Conversation history + attachments | All messages (brief is short) | `[init]` commit |
| Graph review | Brief + full graph + conversation | All messages | `[M-1-context]` commit |
| Wave gate | Brief + phase summaries + current phase envelopes + conversation | All messages | `[M{N}-assessment]` commit |
| Post-run chat | Brief + report + envelope index + conversation | Last 20 + summary | `runs/{run_id}/conversation.jsonl` |

---

## 7. Implementation Order

Each step is independently testable. Do not start the next step until the
current one is running correctly.

### Step 1 — Layered graph model
**What changes:** `models.py` (add Phase), context planner prompt, orchestrator
wave loop, UI rendering.
**Test:** generate a context graph, verify phases are rendered correctly in UI.
**Does not touch:** HITL, attachments, post-run chat, repository.

### Step 2 — HITL graph review
**What changes:** new run status `awaiting_graph_approval`, new graph editor
agent, UI chat interface at graph review stage, GraphEdit operations applied
to Phase-based graph.
**Test:** generate graph, modify it conversationally, confirm, verify the
confirmed graph is what runs.
**Depends on:** Step 1.

### Step 3 — Context graph repository (storage + browse view)
**What changes:** new `output/context_graphs/` store, write record on graph
confirmation, new UI view to browse all stored context graphs (no similarity
search — that is V3).
**Test:** confirm a run, open the context graph browser, verify the record
appears with brief summary, phase structure, and outcome link.
**Depends on:** Step 2 (needs confirmed graphs to store).
**Note:** Similarity search deferred to V3.

### Step 4 — PDF/CSV attachments
**What changes:** UI file upload in interview, ingestion pipeline (pdfplumber
+ pandas), Attachment model, brief commit includes attachments.
**Test:** upload a PDF during interview, verify key facts appear in brief,
verify attachments committed at `[init]`.
**Independent of Steps 1-3** — can be done in parallel if needed.

### Step 5 — Post-run conversation
**What changes:** new UI mode on completed runs, conversation agent,
`read_envelope` / `read_artefact` / `search_evidence` tools, conversation
stored in `conversation.jsonl`.
**Test:** complete a run, open post-run chat, ask a question about a specific
agent's findings, verify the answer cites the correct evidence.
**Independent of Steps 1-3** — can be done after Step 1.

### Step 6 — Multi-level human feedback store
**What changes:** feedback records linked to context graph repository entries,
wave gate responses stored and linked, post-run rating UI, outcome fields
populated on `ContextGraphRecord` after run completion.
**Test:** complete a full run with graph edit + wave approval + post-run
rating, verify all feedback fields populated in the context graph record.
**Depends on:** Steps 2, 3, 5.

---

## 8. What This Enables in V3

Every piece of V2 is infrastructure for V3 RL:

- **`(brief, original_graph, confirmed_graph, edit_count)`** → supervision signal for context planner: did the human approve or heavily modify?
- **`(phase_summary, human_checkpoint_response)`** → supervision signal for orchestrator: what did the human correct mid-run?
- **`(run_id, coverage, confidence, human_rating)`** → outcome signal: how good was the run overall?
- **`(conversation.jsonl)`** → signal about gaps: what did the user have to ask about that wasn't in the report?

The RL training corpus is not something we build separately. It accumulates as
a side effect of every run. By the time V3 is ready to train, the corpus is
already there.
