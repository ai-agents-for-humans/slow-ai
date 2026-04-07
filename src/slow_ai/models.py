from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from pydantic import BaseModel


class ProblemBrief(BaseModel):
    goal: str
    domain: str
    constraints: dict[str, Any]
    unknowns: list[str]
    success_criteria: list[str]
    milestone_flags: list[str]
    excluded_paths: list[str]


# --- Context graph ---

class WorkItem(BaseModel):
    id: str                         # e.g. "wi-1"
    name: str                       # short label
    description: str                # what research needs to happen
    success_criteria: list[str] = []
    depends_on: list[str] = []      # ids of WorkItems this item depends on


class ContextGraph(BaseModel):
    goal: str
    nodes: list[WorkItem]
    edges: list[dict[str, str]] = []  # [{"source": "wi-1", "target": "wi-2"}]


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
    work_item_id: str | None = None    # WorkItem.id this agent addresses


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
    work_item_id: str | None = None    # WorkItem.id this agent addresses


# --- Research plan ---

class ResearchPlan(BaseModel):
    run_id: str
    context_graph: ContextGraph | None = None
    specialists: list[AgentContext]
    milestone_flags: list[str]


# --- Orchestrator decision (assess step) ---

class SpecialistAssignment(BaseModel):
    role: str
    work_item_id: str
    goal: str
    context_budget: int = 6000
    evidence_required: dict[str, str] = {}


class OrchestratorDecision(BaseModel):
    action: Literal["spawn_specialists", "escalate_to_human", "synthesize"]
    wave: int
    work_items_covered: list[str] = []     # wi-ids considered done
    work_items_pending: list[str] = []     # wi-ids still needing work
    work_items_escalated: list[str] = []   # wi-ids needing human input
    next_wave: list[SpecialistAssignment] = []   # populated when action == "spawn_specialists"
    escalation_notes: dict[str, str] = {}  # wi-id → reason, when action == "escalate_to_human"
    reasoning: str


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
