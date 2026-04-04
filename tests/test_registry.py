import pytest

from slow_ai.execution.registry import AgentRegistry


@pytest.fixture
def registry():
    return AgentRegistry()


def test_register_creates_agent(registry):
    reg = registry.register("copernicus_specialist", parent_agent_id=None, task_id="task-001")
    assert reg.agent_id.startswith("copernicus_specialist-")
    assert reg.status == "registered"
    assert reg.parent_agent_id is None
    assert reg.task_id == "task-001"


def test_register_adds_to_agents(registry):
    reg = registry.register("nasa_specialist", None, "task-002")
    assert reg.agent_id in registry.agents


def test_register_child_updates_parent_children_list(registry):
    parent = registry.register("orchestrator", None, "task-root")
    child = registry.register("copernicus_specialist", parent.agent_id, "task-001")
    assert child.agent_id in registry.agents[parent.agent_id].children


def test_register_unknown_parent_does_not_raise(registry):
    reg = registry.register("specialist", parent_agent_id="nonexistent-id", task_id="task-x")
    assert reg.agent_id in registry.agents


def test_update_status_running(registry):
    reg = registry.register("specialist", None, "task-001")
    registry.update_status(reg.agent_id, "running")
    assert registry.agents[reg.agent_id].status == "running"
    assert registry.agents[reg.agent_id].completed_at is None


def test_update_status_completed_sets_timestamp(registry):
    reg = registry.register("specialist", None, "task-001")
    registry.update_status(reg.agent_id, "completed", tokens_used=500)
    assert registry.agents[reg.agent_id].status == "completed"
    assert registry.agents[reg.agent_id].tokens_used == 500
    assert registry.agents[reg.agent_id].completed_at is not None


def test_update_status_failed_sets_timestamp(registry):
    reg = registry.register("specialist", None, "task-001")
    registry.update_status(reg.agent_id, "failed")
    assert registry.agents[reg.agent_id].completed_at is not None


def test_update_status_unknown_agent_does_not_raise(registry):
    registry.update_status("nonexistent", "completed")  # should be a no-op


def test_set_memory_path(registry):
    reg = registry.register("specialist", None, "task-001")
    registry.set_memory_path(reg.agent_id, "memory/specialist-abc123.json")
    assert registry.agents[reg.agent_id].memory_path == "memory/specialist-abc123.json"


def test_snapshot_structure(registry):
    registry.register("specialist-a", None, "task-001")
    registry.register("specialist-b", None, "task-002")
    snap = registry.snapshot()
    assert snap["total_agents"] == 2
    assert snap["running"] == 0
    assert len(snap["agents"]) == 2


def test_snapshot_running_count(registry):
    reg = registry.register("specialist", None, "task-001")
    registry.update_status(reg.agent_id, "running")
    assert registry.snapshot()["running"] == 1


def test_get_dag_nodes_and_edges(registry):
    parent = registry.register("orchestrator", None, "task-root")
    child = registry.register("specialist", parent.agent_id, "task-001")

    dag = registry.get_dag()
    node_ids = [n["id"] for n in dag["nodes"]]
    assert parent.agent_id in node_ids
    assert child.agent_id in node_ids

    assert len(dag["edges"]) == 1
    assert dag["edges"][0]["source"] == parent.agent_id
    assert dag["edges"][0]["target"] == child.agent_id


def test_get_dag_no_edges_for_root_agents(registry):
    registry.register("specialist-a", None, "task-001")
    registry.register("specialist-b", None, "task-002")
    dag = registry.get_dag()
    assert dag["edges"] == []
