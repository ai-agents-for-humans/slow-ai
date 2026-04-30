import uuid
from datetime import UTC, datetime
from typing import Literal

from slow_ai.models import AgentRegistration


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
        agent_id: str | None = None,
        work_item_id: str | None = None,
    ) -> AgentRegistration:
        if agent_id is None:
            agent_id = f"{agent_type}-{uuid.uuid4().hex[:6]}"
        reg = AgentRegistration(
            agent_id=agent_id,
            agent_type=agent_type,
            parent_agent_id=parent_agent_id,
            task_id=task_id,
            spawned_at=datetime.now(UTC).isoformat(),
            work_item_id=work_item_id,
        )
        self.agents[agent_id] = reg

        if parent_agent_id and parent_agent_id in self.agents:
            self.agents[parent_agent_id].children.append(agent_id)

        return reg

    def update_status(
        self,
        agent_id: str,
        status: Literal["registered", "running", "completed", "failed"],
        tokens_used: int = 0,
    ) -> None:
        if agent_id in self.agents:
            self.agents[agent_id].status = status
            self.agents[agent_id].tokens_used = tokens_used
            if status in ("completed", "failed"):
                self.agents[agent_id].completed_at = datetime.now(UTC).isoformat()

    def set_memory_path(self, agent_id: str, path: str) -> None:
        if agent_id in self.agents:
            self.agents[agent_id].memory_path = path

    def snapshot(self) -> dict:
        """Return full registry as dict for git commit."""
        return {
            "agents": {aid: reg.model_dump() for aid, reg in self.agents.items()},
            "total_agents": len(self.agents),
            "running": sum(1 for r in self.agents.values() if r.status == "running"),
        }

    def get_dag(self) -> dict:
        """
        Return DAG as nodes and edges for UI rendering.
        """
        nodes = [
            {
                "id": reg.agent_id,
                "type": reg.agent_type,
                "status": reg.status,
                "tokens": reg.tokens_used,
                "spawned_at": reg.spawned_at,
                "completed_at": reg.completed_at,
                "work_item_id": reg.work_item_id,
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
