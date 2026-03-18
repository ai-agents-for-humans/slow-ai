from datetime import datetime, timezone

from slow_ai.models import AgentMemory, AgentTask, MemoryEntry


def _make_entry(tokens: int) -> MemoryEntry:
    return MemoryEntry(
        key="test_key",
        value={"data": "value"},
        source="perplexity_search",
        confidence=0.8,
        created_at=datetime.now(timezone.utc).isoformat(),
        tokens_consumed=tokens,
    )


def test_agent_memory_add_accumulates_tokens():
    memory = AgentMemory(agent_id="agent-1", agent_type="test", context_budget=1000)
    memory.add(_make_entry(300))
    memory.add(_make_entry(200))
    assert memory.total_tokens == 500
    assert len(memory.entries) == 2


def test_agent_memory_budget_remaining():
    memory = AgentMemory(agent_id="agent-1", agent_type="test", context_budget=1000)
    memory.add(_make_entry(400))
    assert memory.budget_remaining() == 600


def test_agent_memory_should_decompose_below_threshold():
    memory = AgentMemory(agent_id="agent-1", agent_type="test", context_budget=1000)
    memory.add(_make_entry(700))  # 70% — at threshold
    assert memory.should_decompose(threshold=0.75) is False


def test_agent_memory_should_decompose_above_threshold():
    memory = AgentMemory(agent_id="agent-1", agent_type="test", context_budget=1000)
    memory.add(_make_entry(800))  # 80% — above threshold
    assert memory.should_decompose(threshold=0.75) is True


def test_agent_task_defaults():
    task = AgentTask(agent_type="copernicus_specialist", goal="Find Sentinel-2 data")
    assert task.status == "pending"
    assert task.parent_task_id is None
    assert task.sub_task_ids == []
