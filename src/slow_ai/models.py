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
    prior_run_ids: list[str] = []   # ordered chain of prior run IDs, oldest first


# --- Context graph ---

class WorkItem(BaseModel):
    id: str                         # e.g. "wi-1-1" (phase-1, item-1)
    name: str                       # short label
    description: str                # what needs to happen
    success_criteria: list[str] = []
    required_skills: list[str] = [] # e.g. ["web_search", "pdf_extraction"]


class Phase(BaseModel):
    id: str                          # e.g. "phase-1"
    name: str                        # e.g. "Explore", "Investigate", "Critique"
    purpose: str                     # what this phase is trying to achieve
    work_items: list[WorkItem]       # all run in parallel within this phase
    depends_on_phases: list[str] = [] # phase ids that must complete before this
    synthesis_instruction: str = ""  # guidance for phase-level synthesis agent


class ContextGraph(BaseModel):
    goal: str
    phases: list[Phase]


# --- Skill gap / viability ---

class SkillGap(BaseModel):
    skill: str                      # e.g. "pdf_extraction"
    required_by: list[str]          # work item ids that directly need this skill
    downstream_blocked: int         # total items blocked (including transitive deps)
    is_critical_path: bool          # blocks > 50% of the graph


class ViabilityDecision(BaseModel):
    action: Literal["go", "degraded", "no_go"]
    skill_gaps: list[SkillGap] = []
    blocked_work_items: list[str] = []    # gap items + transitive dependents
    executable_work_items: list[str] = []
    coverage_ratio: float = 1.0
    reasoning: str


# --- Skill synthesis ---

class SynthesizedSkill(BaseModel):
    name: str
    description: str
    tools: list[str]                # existing tool names that implement this skill
    source: str = "synthesized"
    tags: list[str] = []


class SkillSynthesisResult(BaseModel):
    synthesized: list[SynthesizedSkill] = []
    needs_new_tool: list[str] = []          # skill names that couldn't be synthesized
    github_search_queries: list[str] = []   # suggested queries for unresolvable gaps
    reasoning: str


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
    agent_type: str             # reusable template name
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
    parent_task_id: str | None = None
    agent_type: str
    goal: str
    context_budget: int = 8000
    sub_task_ids: list[str] = []
    status: Literal["pending", "running", "completed", "failed"] = "pending"


# --- Spawn request ---

class SpawnRequest(BaseModel):
    requested_by: str
    agent_type: str
    goal: str
    context_budget: int = 4000
    tools: list[str] = ["perplexity_search", "web_browse"]
    priority: Literal["blocking", "background"] = "blocking"


# --- Registry ---

class AgentRegistration(BaseModel):
    agent_id: str
    agent_type: str
    parent_agent_id: str | None = None
    task_id: str
    status: Literal["registered", "running", "completed", "failed"] = "registered"
    spawned_at: str = ""
    completed_at: str | None = None
    memory_path: str | None = None
    tokens_used: int = 0
    children: list[str] = []
    work_item_id: str | None = None


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
    work_item_id: str | None = None
    artefacts_dir: str | None = None
    venv_path: str | None = None        # sandboxed run environment
    prior_run_ids: list[str] = []       # enables read_prior_evidence tool


# --- Research plan ---

class ResearchPlan(BaseModel):
    run_id: str
    phase_id: str                        # which phase this plan covers
    context_graph: ContextGraph | None = None
    specialists: list[AgentContext]
    milestone_flags: list[str]


# --- Orchestrator decision (phase assessment) ---

class SpecialistAssignment(BaseModel):
    role: str
    work_item_id: str
    goal: str
    context_budget: int = 6000
    evidence_required: dict[str, str] = {}


class OrchestratorDecision(BaseModel):
    action: Literal["proceed", "synthesize", "escalate_to_human", "circuit_break"]
    phase_id: str
    work_items_covered: list[str] = []    # wi-ids with confidence >= 0.6
    work_items_partial: list[str] = []    # wi-ids with confidence 0.3-0.59
    work_items_uncovered: list[str] = []  # wi-ids with confidence < 0.3
    escalation_notes: dict[str, str] = {}
    circuit_break_reason: str = ""
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
    artefacts: list[str]
    workers_spawned: list[str] = []


# --- Phase summary (synthesis + raw envelopes) ---

class PhaseSummary(BaseModel):
    phase_id: str
    phase_name: str
    synthesis: str                        # LLM-generated narrative
    envelopes: list[EvidenceEnvelope]     # raw envelopes preserved alongside synthesis
    covered_item_ids: list[str] = []      # confidence >= 0.6
    partial_item_ids: list[str] = []      # confidence 0.3-0.59
    uncovered_item_ids: list[str] = []    # confidence < 0.3
    mean_confidence: float = 0.0
    total_tokens: int = 0


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
