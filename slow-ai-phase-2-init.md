# Slow AI — Phase 2 init
## For Claude Code

---

## The rule

Build only what is in this file.
After every file you create, stop. Tell me what you built. Wait for my go-ahead before the next file.
Do not build ahead. Do not infer what comes next. One file at a time.

---

## What we are building

Phase 2 adds five things to the working Phase 1 Streamlit app:

1. Two real tools — Perplexity search and web browse
2. Agent memory — every agent instance carries its own memory store, written after each tool call
3. Dynamic worker spawning — agents can request sub-workers mid-execution, all registered with the orchestrator
4. AgentRegistry — the control plane, tracks every agent, its lineage, its status, its memory
5. Git store — every run is a repository, milestones and registry state committed at each checkpoint

The Streamlit app from Phase 1 is the entry point. After the interview produces a brief,
a "Start Research" button kicks off the orchestration. Progress shown live via callback.

---

## What already exists (do not rebuild)

- `src/slow_ai/config.py` — Settings with GEMINI_API_KEY
- `src/slow_ai/models.py` — ProblemBrief
- `src/slow_ai/agents/interviewer.py` — Interview agent
- `streamlit_app.py` — Streamlit interview UI

---

## New dependencies to add to `pyproject.toml`

```
gitpython
httpx
beautifulsoup4
lxml
```

Add to `.env.example` and to `Settings` in `config.py`:
```
PERPLEXITY_API_KEY=your-key-here
```

---

## New project structure

Add only these files. One at a time.

```
src/slow_ai/
├── models.py                  ← extend with new models
├── tools/
│   ├── __init__.py
│   ├── perplexity.py
│   └── web_browse.py
├── agents/
│   ├── orchestrator.py
│   └── specialist.py
├── execution/
│   ├── __init__.py
│   ├── git_store.py
│   └── registry.py            ← AgentRegistry — the control plane
└── research/
    ├── __init__.py
    └── runner.py
```

---

## File specifications

---

### `src/slow_ai/models.py` — extend, do not replace

Keep `ProblemBrief` exactly as it is. Add these models below it.

```python
from typing import Any, Literal
from pydantic import BaseModel
import uuid
from datetime import datetime, timezone

# --- Memory ---

class MemoryEntry(BaseModel):
    key: str                    # "kenya_sentinel2_scenes", "urls_checked"
    value: Any
    source: str                 # "perplexity_search", "web_browse", "inference"
    confidence: float           # 0.0 to 1.0
    created_at: str             # ISO timestamp
    tokens_consumed: int        # how much context this entry cost to produce

class AgentMemory(BaseModel):
    agent_id: str
    agent_type: str             # "copernicus_specialist" — the reusable template name
    entries: list[MemoryEntry] = []
    total_tokens: int = 0
    context_budget: int = 8000  # max tokens before decomposition is triggered

    def add(self, entry: MemoryEntry) -> None:
        self.entries.append(entry)
        self.total_tokens += entry.tokens_consumed

    def budget_remaining(self) -> int:
        return self.context_budget - self.total_tokens

    def should_decompose(self, threshold: float = 0.75) -> bool:
        return self.total_tokens >= self.context_budget * threshold

# --- Tasks ---

class AgentTask(BaseModel):
    task_id: str = ""
    parent_task_id: str | None = None   # None = root task from orchestrator
    agent_type: str
    goal: str
    context_budget: int = 8000
    sub_task_ids: list[str] = []
    status: Literal["pending", "running", "completed", "failed"] = "pending"

# --- Spawn request ---

class SpawnRequest(BaseModel):
    requested_by: str                           # parent agent_id
    agent_type: str
    goal: str
    context_budget: int = 4000
    tools: list[str] = ["perplexity_search", "web_browse"]
    priority: Literal["blocking", "background"] = "blocking"
    # blocking = parent waits for result before continuing
    # background = parent continues, result collected at milestone

# --- Registry ---

class AgentRegistration(BaseModel):
    agent_id: str
    agent_type: str
    parent_agent_id: str | None = None
    task_id: str
    status: Literal["registered", "running", "completed", "failed"] = "registered"
    spawned_at: str = ""
    completed_at: str | None = None
    memory_path: str | None = None     # git path to memory snapshot
    tokens_used: int = 0
    children: list[str] = []          # agent_ids of workers this agent spawned

# --- Agent context ---

class AgentContext(BaseModel):
    agent_id: str
    role: str
    expertise: list[str]
    task: AgentTask
    memory: AgentMemory
    constraints: dict[str, Any]
    tools_available: list[str] = ["perplexity_search", "web_browse"]
    evidence_required: dict[str, str]

# --- Research plan ---

class ResearchPlan(BaseModel):
    run_id: str
    specialists: list[AgentContext]
    milestone_flags: list[str]

# --- Evidence ---

class EvidenceEnvelope(BaseModel):
    agent_id: str
    role: str
    status: Literal["completed", "partial", "failed", "skipped"]
    proof: dict[str, Any]
    verdict: Literal["continue", "stop", "escalate"]
    confidence: float
    cost_tokens: int
    artefacts: list[str]               # filenames to commit to git
    workers_spawned: list[str] = []    # agent_ids of any workers this agent spawned

# --- Dataset output ---

class DatasetCandidate(BaseModel):
    name: str
    source: str
    url: str
    coverage_pct: float | None = None
    time_range: str | None = None
    resolution: str | None = None
    license: str | None = None
    format: str | None = None
    quality_score: float = 0.0
    notes: str = ""

class ResearchReport(BaseModel):
    run_id: str
    brief_goal: str
    datasets: list[DatasetCandidate]
    paths_not_taken: list[str] = []
    summary: str
    generated_at: str
```

---

### `src/slow_ai/tools/perplexity.py`

Calls the Perplexity API. Returns answer and cited URLs.

```python
import httpx
from pydantic import BaseModel
from slow_ai.config import settings

class PerplexityResult(BaseModel):
    answer: str
    citations: list[str]

async def perplexity_search(query: str) -> PerplexityResult:
    """Search Perplexity. Returns synthesised answer and cited URLs."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.perplexity_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": query}],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

    answer = data["choices"][0]["message"]["content"]
    citations = data.get("citations", [])

    # fallback: extract URLs from answer text if citations missing
    if not citations:
        import re
        citations = re.findall(r'https?://[^\s\)\"]+', answer)

    return PerplexityResult(answer=answer, citations=citations)
```

---

### `src/slow_ai/tools/web_browse.py`

Fetches a URL and returns cleaned readable text.

```python
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

class BrowseResult(BaseModel):
    url: str
    title: str = ""
    text: str = ""
    success: bool = True
    error: str | None = None

async def web_browse(url: str, max_chars: int = 4000) -> BrowseResult:
    """Fetch URL and extract readable text. Max 4000 chars."""
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SlowAI-Research/1.0)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title else ""
        main = soup.find("main") or soup.find("body")
        text = " ".join(main.get_text(separator=" ").split()) if main else ""
        text = text[:max_chars]

        return BrowseResult(url=url, title=title, text=text)

    except Exception as e:
        return BrowseResult(url=url, success=False, error=str(e))
```

---

### `src/slow_ai/execution/git_store.py`

One git repository per run. Commit per milestone.

```python
from pathlib import Path
from git import Repo, Actor
import json
from typing import Any

AUTHOR = Actor("SlowAI", "slowai@local")

class GitStore:
    def __init__(self, run_id: str, base_path: Path = Path("runs")):
        self.run_id = run_id
        self.run_path = base_path / run_id
        self.run_path.mkdir(parents=True, exist_ok=True)
        self.repo = Repo.init(self.run_path)

    def _write(self, relative_path: str, content: Any) -> Path:
        """Write JSON content to a file inside the run repo."""
        full_path = self.run_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(
            json.dumps(content, indent=2, default=str), encoding="utf-8"
        )
        return full_path

    def _commit(self, message: str, paths: list[str]) -> str:
        """Stage specific files and commit. Returns commit sha."""
        self.repo.index.add(paths)
        commit = self.repo.index.commit(
            message, author=AUTHOR, committer=AUTHOR
        )
        return commit.hexsha

    def commit_brief(self, brief: dict) -> str:
        self._write("problem_brief.json", brief)
        return self._commit("[init] problem brief", ["problem_brief.json"])

    def commit_milestone(
        self,
        milestone: str,
        artefacts: dict[str, Any],   # relative_path → content
        registry_snapshot: dict | None = None,
    ) -> str:
        paths = []
        for rel_path, content in artefacts.items():
            self._write(rel_path, content)
            paths.append(rel_path)

        if registry_snapshot:
            self._write("registry.json", registry_snapshot)
            paths.append("registry.json")

        return self._commit(f"[{milestone}]", paths)

    def record_skipped_path(
        self, path_id: str, reason: str, triggered_by: str
    ) -> str:
        content = {
            "path_id": path_id,
            "reason": reason,
            "triggered_by": triggered_by,
        }
        rel = f"paths/not_taken/{path_id}.json"
        self._write(rel, content)
        return self._commit(f"[skipped] {path_id}", [rel])

    def get_log(self) -> list[dict]:
        return [
            {
                "sha": c.hexsha[:8],
                "message": c.message.strip(),
                "timestamp": c.committed_datetime.isoformat(),
            }
            for c in self.repo.iter_commits()
        ]
```

---

### `src/slow_ai/execution/registry.py`

The control plane. Every agent registers here before running.
Lives in the runner, passed to all agents via the spawn mechanism.

```python
from datetime import datetime, timezone
from slow_ai.models import AgentRegistration, SpawnRequest
import uuid

class AgentRegistry:
    """
    The control plane. Tracks all agents: their lineage, status, token use.
    Committed to git as registry.json at each milestone.
    """

    def __init__(self):
        self.agents: dict[str, AgentRegistration] = {}

    def register(
        self,
        agent_type: str,
        parent_agent_id: str | None,
        task_id: str,
    ) -> AgentRegistration:
        agent_id = f"{agent_type}-{uuid.uuid4().hex[:6]}"
        reg = AgentRegistration(
            agent_id=agent_id,
            agent_type=agent_type,
            parent_agent_id=parent_agent_id,
            task_id=task_id,
            spawned_at=datetime.now(timezone.utc).isoformat(),
        )
        self.agents[agent_id] = reg

        # update parent's children list
        if parent_agent_id and parent_agent_id in self.agents:
            self.agents[parent_agent_id].children.append(agent_id)

        return reg

    def update_status(self, agent_id: str, status: str, tokens_used: int = 0) -> None:
        if agent_id in self.agents:
            self.agents[agent_id].status = status
            self.agents[agent_id].tokens_used = tokens_used
            if status in ("completed", "failed"):
                self.agents[agent_id].completed_at = (
                    datetime.now(timezone.utc).isoformat()
                )

    def set_memory_path(self, agent_id: str, path: str) -> None:
        if agent_id in self.agents:
            self.agents[agent_id].memory_path = path

    def snapshot(self) -> dict:
        """Return full registry as dict for git commit."""
        return {
            "agents": {
                aid: reg.model_dump()
                for aid, reg in self.agents.items()
            },
            "total_agents": len(self.agents),
            "running": sum(
                1 for r in self.agents.values() if r.status == "running"
            ),
        }

    def get_dag(self) -> list[dict]:
        """
        Return DAG as list of nodes and edges.
        Used by Phase 4 IDE to render the agent graph.
        """
        nodes = [
            {
                "id": reg.agent_id,
                "type": reg.agent_type,
                "status": reg.status,
                "tokens": reg.tokens_used,
            }
            for reg in self.agents.values()
        ]
        edges = [
            {
                "source": reg.parent_agent_id,
                "target": reg.agent_id,
            }
            for reg in self.agents.values()
            if reg.parent_agent_id
        ]
        return {"nodes": nodes, "edges": edges}
```

---

### `src/slow_ai/agents/orchestrator.py`

Reads the ProblemBrief. Returns a ResearchPlan with specialist contexts.
Also handles SpawnRequests from agents mid-execution.

```python
import os
from pydantic_ai import Agent
from slow_ai.models import ProblemBrief, ResearchPlan, AgentContext, AgentTask, AgentMemory, SpawnRequest
from slow_ai.config import settings
import uuid, json

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

_orchestrator = Agent(
    model="google-gla:gemini-2.0-flash",
    result_type=ResearchPlan,
    system_prompt="""
You are a research orchestrator for earth observation data.

Given a problem brief, produce a ResearchPlan with specialist agents to deploy.

Always consider these specialist types for earth observation:
- copernicus_specialist: Sentinel-2, Sentinel-1 SAR, ESA Open Access Hub, free optical data
- nasa_earthdata_specialist: MODIS, Landsat, SRTM, NASA CMR search API
- google_earth_engine_specialist: GEE data catalogue, cloud-based processing, STAC APIs
- open_data_specialist: national agencies, data.gov, OpenAfrica, RCMRD, regional portals

For each specialist:
- Assign a specific task based on brief constraints (region, time range, resolution)
- Set evidence_required: what proof they must return (sources_checked, datasets_found,
  coverage_pct, license, resolution, format, download_url)
- Set context_budget based on task complexity:
  - Single country, single time range: 6000 tokens
  - Multiple countries or long time range: 4000 tokens (expect decomposition)
  - Broad survey: 3000 tokens (will need workers)

Return run_id and milestone_flags from the brief.
""",
)

async def run_orchestrator(brief: ProblemBrief, run_id: str) -> ResearchPlan:
    result = await _orchestrator.run(
        f"Run ID: {run_id}\n\nProblem brief:\n{json.dumps(brief.model_dump(), indent=2)}"
    )
    plan = result.data
    plan.run_id = run_id

    # assign agent_ids and task_ids to each specialist
    for ctx in plan.specialists:
        task_id = f"task-{uuid.uuid4().hex[:6]}"
        ctx.agent_id = f"{ctx.role.replace(' ', '_').lower()}-{uuid.uuid4().hex[:6]}"
        ctx.task = AgentTask(
            task_id=task_id,
            parent_task_id=None,
            agent_type=ctx.role,
            goal=ctx.task if isinstance(ctx.task, str) else ctx.task.goal,
            context_budget=ctx.memory.context_budget if ctx.memory else 8000,
        )
        ctx.memory = AgentMemory(
            agent_id=ctx.agent_id,
            agent_type=ctx.role,
            context_budget=ctx.task.context_budget,
        )

    return plan


async def handle_spawn_request(
    request: SpawnRequest,
    registry,                 # AgentRegistry — passed in from runner
) -> AgentContext:
    """
    Called when an agent requests a worker mid-execution.
    Registers the worker in the registry and returns its context.
    """
    task_id = f"task-{uuid.uuid4().hex[:6]}"
    reg = registry.register(
        agent_type=request.agent_type,
        parent_agent_id=request.requested_by,
        task_id=task_id,
    )
    task = AgentTask(
        task_id=task_id,
        parent_task_id=request.requested_by,
        agent_type=request.agent_type,
        goal=request.goal,
        context_budget=request.context_budget,
    )
    memory = AgentMemory(
        agent_id=reg.agent_id,
        agent_type=request.agent_type,
        context_budget=request.context_budget,
    )
    return AgentContext(
        agent_id=reg.agent_id,
        role=request.agent_type,
        expertise=[],
        task=task,
        memory=memory,
        constraints={},
        tools_available=request.tools,
        evidence_required={},
    )
```

---

### `src/slow_ai/agents/specialist.py`

Generic specialist. Parameterised by AgentContext.
Runs tools, writes memory after each call, spawns workers when context budget is near.

```python
import os, json, uuid
from datetime import datetime, timezone
from pydantic_ai import Agent
from slow_ai.models import (
    AgentContext, EvidenceEnvelope, MemoryEntry, SpawnRequest
)
from slow_ai.tools.perplexity import perplexity_search
from slow_ai.tools.web_browse import web_browse
from slow_ai.config import settings

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key


def build_system_prompt(ctx: AgentContext) -> str:
    return f"""
You are a {ctx.role}.

Your expertise: {', '.join(ctx.expertise) if ctx.expertise else 'earth observation data research'}

Your task:
{ctx.task.goal}

Research constraints:
{json.dumps(ctx.constraints, indent=2)}

Context budget: {ctx.memory.context_budget} tokens. Currently used: {ctx.memory.total_tokens}.
Budget remaining: {ctx.memory.budget_remaining()} tokens.

You have two tools:
- perplexity_search: find datasets, get relevant URLs and a synthesised answer
- web_browse: read a specific URL and extract detailed information

Research process:
1. perplexity_search with a precise query tailored to your task and constraints
2. From citations returned, web_browse each URL to get actual dataset details
3. After each tool call, note key findings (you will write these to memory)
4. If your budget is running low and you have more URLs to check, note them in
   your evidence envelope — the runner will spawn workers for the remaining URLs

Evidence required:
{json.dumps(ctx.evidence_required, indent=2) if ctx.evidence_required else
 "sources_checked, datasets_found, coverage_pct, license, resolution, download_url"}

Return an EvidenceEnvelope with:
- status: completed / partial / failed
- proof: everything you found, structured
- verdict: continue (found useful data) / escalate (needs human review) / stop (nothing found)
- confidence: 0.0 to 1.0
- artefacts: list of filenames to save (include agent_id in name)
- workers_spawned: leave empty — the runner fills this in
"""


async def run_specialist(
    ctx: AgentContext,
    registry=None,            # AgentRegistry — passed in from runner
    spawn_handler=None,       # async callable(SpawnRequest) → AgentContext
) -> tuple[EvidenceEnvelope, AgentContext]:
    """
    Run a specialist agent.
    Returns the evidence envelope AND the updated context (with populated memory).
    """

    agent = Agent(
        model="google-gla:gemini-2.0-flash",
        result_type=EvidenceEnvelope,
        system_prompt=build_system_prompt(ctx),
    )

    # register perplexity and web_browse as tools
    @agent.tool_plain
    async def search(query: str) -> str:
        result = await perplexity_search(query)
        # write to memory
        entry = MemoryEntry(
            key=f"search_{uuid.uuid4().hex[:4]}",
            value={"query": query, "answer": result.answer, "citations": result.citations},
            source="perplexity_search",
            confidence=0.8,
            created_at=datetime.now(timezone.utc).isoformat(),
            tokens_consumed=len(result.answer.split()) * 2,
        )
        ctx.memory.add(entry)
        return json.dumps({"answer": result.answer, "citations": result.citations})

    @agent.tool_plain
    async def browse(url: str) -> str:
        result = await web_browse(url)
        entry = MemoryEntry(
            key=f"browse_{uuid.uuid4().hex[:4]}",
            value={"url": url, "title": result.title, "text": result.text[:500]},
            source="web_browse",
            confidence=0.9 if result.success else 0.1,
            created_at=datetime.now(timezone.utc).isoformat(),
            tokens_consumed=len(result.text.split()) * 2 if result.text else 10,
        )
        ctx.memory.add(entry)
        if not result.success:
            return json.dumps({"error": result.error})
        return json.dumps({"title": result.title, "text": result.text})

    if registry:
        registry.update_status(ctx.agent_id, "running")

    result = await agent.run(
        f"Begin research for your assigned task. "
        f"Start with a perplexity_search, then browse key URLs from the citations."
    )

    envelope = result.data
    envelope.agent_id = ctx.agent_id
    envelope.cost_tokens = ctx.memory.total_tokens

    if registry:
        registry.update_status(ctx.agent_id, "completed", tokens_used=ctx.memory.total_tokens)
        registry.set_memory_path(ctx.agent_id, f"memory/{ctx.agent_id}.json")

    return envelope, ctx
```

---

### `src/slow_ai/research/runner.py`

Async coordinator. Reads brief, runs full process, commits to git.

```python
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from slow_ai.models import (
    ProblemBrief, ResearchPlan, EvidenceEnvelope,
    ResearchReport, DatasetCandidate, SpawnRequest
)
from slow_ai.agents.orchestrator import run_orchestrator, handle_spawn_request
from slow_ai.agents.specialist import run_specialist
from slow_ai.execution.git_store import GitStore
from slow_ai.execution.registry import AgentRegistry
import os, json
from pydantic_ai import Agent
from slow_ai.config import settings

os.environ["GEMINI_API_KEY"] = settings.gemini_api_key


async def run_research(
    brief: ProblemBrief,
    on_progress: callable = None,
) -> ResearchReport:

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    store = GitStore(run_id=run_id)
    registry = AgentRegistry()

    store.commit_brief(brief.model_dump())
    _progress(on_progress, f"Run `{run_id}` initialised.")

    # Step 1: Orchestrator plans
    _progress(on_progress, "Orchestrator planning research...")
    plan: ResearchPlan = await run_orchestrator(brief, run_id)

    # Register all specialists
    for ctx in plan.specialists:
        registry.register(
            agent_type=ctx.role,
            parent_agent_id=None,
            task_id=ctx.task.task_id,
        )
        # align registered agent_id with context
        # (orchestrator assigned agent_id — sync it)

    store.commit_milestone(
        "M0-plan",
        {"research_plan.json": plan.model_dump()},
        registry_snapshot=registry.snapshot(),
    )
    _progress(on_progress, f"Plan ready — {len(plan.specialists)} specialists assigned.")

    # Step 2: Specialists run in parallel
    _progress(on_progress, "Launching specialists in parallel...")

    async def run_with_spawn(ctx):
        """Run a specialist with spawn capability."""
        async def spawn_handler(request: SpawnRequest) -> AgentContext:
            worker_ctx = await handle_spawn_request(request, registry)
            _progress(on_progress, f"Worker spawned: {worker_ctx.agent_id} (parent: {request.requested_by})")
            worker_envelope, worker_ctx = await run_specialist(worker_ctx, registry, None)
            return worker_ctx
        return await run_specialist(ctx, registry, spawn_handler)

    results = await asyncio.gather(
        *[run_with_spawn(ctx) for ctx in plan.specialists],
        return_exceptions=True,
    )

    envelopes = []
    updated_contexts = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            _progress(on_progress, f"Specialist {plan.specialists[i].agent_id} failed: {result}")
            store.record_skipped_path(
                f"specialist-failed-{plan.specialists[i].agent_id}",
                reason=str(result),
                triggered_by="runner",
            )
        else:
            envelope, updated_ctx = result
            envelopes.append(envelope)
            updated_contexts.append(updated_ctx)

    # Commit M1 — all envelopes and memory stores
    m1_artefacts = {}
    for envelope, ctx in zip(envelopes, updated_contexts):
        m1_artefacts[f"envelopes/{envelope.agent_id}.json"] = envelope.model_dump()
        m1_artefacts[f"memory/{ctx.agent_id}.json"] = ctx.memory.model_dump()

    store.commit_milestone("M1-source-discovery", m1_artefacts, registry.snapshot())
    _progress(on_progress, f"M1 complete — {len(envelopes)} envelopes committed.")

    # Check stop verdicts
    stops = [e for e in envelopes if e.verdict == "stop"]
    if stops:
        for e in stops:
            store.record_skipped_path(
                f"stop-verdict-{e.agent_id}",
                reason="agent returned stop verdict",
                triggered_by=e.agent_id,
            )

    # Step 3: Synthesis
    _progress(on_progress, "Synthesising final report...")
    report = await _synthesise(run_id, brief, envelopes, store, registry, on_progress)
    _progress(on_progress, f"Done. Report committed to runs/{run_id}/")

    return report


async def _synthesise(
    run_id, brief, envelopes, store, registry, on_progress
) -> ResearchReport:

    synthesis_agent = Agent(
        model="google-gla:gemini-2.0-flash",
        result_type=ResearchReport,
        system_prompt="""
You are a research synthesiser. You receive evidence envelopes from multiple
specialist agents and produce a final ranked research report.

For each dataset found across all envelopes:
- Deduplicate by name and source
- Assign a quality_score (0.0 to 1.0) based on coverage, resolution, license, completeness
- Rank datasets by quality_score descending
- Note paths not taken (failed agents, stop verdicts)
- Write a short summary of the overall findings

Return a ResearchReport.
""",
    )

    envelope_data = json.dumps([e.model_dump() for e in envelopes], indent=2)
    result = await synthesis_agent.run(
        f"Run ID: {run_id}\n\nGoal: {brief.goal}\n\nEvidence envelopes:\n{envelope_data}"
    )
    report = result.data
    report.run_id = run_id
    report.brief_goal = brief.goal
    report.generated_at = datetime.now(timezone.utc).isoformat()

    store.commit_milestone(
        "M2-final-report",
        {"report.json": report.model_dump()},
        registry.snapshot(),
    )

    return report


def _progress(callback, message: str) -> None:
    if callback:
        callback(message)
```

---

### Streamlit integration

In `streamlit_app.py`, after the brief is confirmed, add a research section:

```python
if "brief" in st.session_state and st.session_state.brief:
    st.divider()
    st.subheader("Research")

    if st.button("Start Research", type="primary"):
        progress_placeholder = st.empty()
        log = []

        def on_progress(msg: str):
            log.append(msg)
            progress_placeholder.markdown(
                "\n".join(f"- {m}" for m in log)
            )

        import asyncio
        from slow_ai.research.runner import run_research

        with st.spinner("Research in progress..."):
            try:
                import nest_asyncio
                nest_asyncio.apply()
            except ImportError:
                pass

            report = asyncio.run(
                run_research(st.session_state.brief, on_progress=on_progress)
            )

        st.success("Research complete!")

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
```

Add `nest_asyncio` to dependencies in `pyproject.toml`.

---

## Acceptance criteria

Before telling me Phase 2 is done, verify:

- [ ] `perplexity_search("Sentinel-2 datasets East Africa agriculture 2018–2024")` returns answer + citations
- [ ] `web_browse("https://scihub.copernicus.eu")` returns cleaned text
- [ ] `GitStore` creates `runs/{run_id}/`, commits brief as first commit
- [ ] `AgentRegistry` registers all specialists before any of them run
- [ ] A SpawnRequest from a specialist creates a new worker registered under the parent
- [ ] `registry.snapshot()` shows correct lineage (parent_agent_id populated)
- [ ] M1 git commit contains `envelopes/*.json` and `memory/*.json` for all agents
- [ ] `registry.json` is committed at every milestone
- [ ] `get_dag()` returns nodes and edges that correctly reflect spawning lineage
- [ ] Final `ResearchReport` is committed and displayed in Streamlit
- [ ] `paths/not_taken/` used for failed agents and stop verdicts

---

## What not to build

- Temporal (Phase 3)
- Observer operator (Phase 3)
- Skills / agent repository (Phase 3)
- Cost budget enforcement (Phase 3)
- React IDE / DAG visualisation (Phase 4)

---

## Build order

1. Extend `models.py`. Stop. Review all models together.
2. `tools/perplexity.py`. Stop. Test with a sample query.
3. `tools/web_browse.py`. Stop. Test with a real URL.
4. `execution/git_store.py`. Stop. Test: init, commit brief, commit milestone.
5. `execution/registry.py`. Stop. Test: register two agents with parent/child relationship.
6. `agents/orchestrator.py`. Stop. Test with a sample brief.
7. `agents/specialist.py`. Stop. Test one specialist in isolation.
8. `research/runner.py`. Stop. Test end to end.
9. Streamlit integration. Stop.

---

## Start here

Extend `models.py` with all new models. Show me the complete file. Wait.
