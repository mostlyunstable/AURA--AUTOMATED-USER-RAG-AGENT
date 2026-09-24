from typing import Set

from core.domain.agents.enums import AgentTaskStatus
from core.domain.agents.orchestration.entities import AgentTask


class InvalidAgentTaskTransition(Exception):
    pass


class AgentTaskStateMachine:
    VALID_TRANSITIONS: dict[AgentTaskStatus, Set[AgentTaskStatus]] = {
        AgentTaskStatus.PENDING: {
            AgentTaskStatus.READY,
            AgentTaskStatus.CANCELLED,
        },
        AgentTaskStatus.READY: {
            AgentTaskStatus.ASSIGNED,
            AgentTaskStatus.BLOCKED,
            AgentTaskStatus.CANCELLED,
        },
        AgentTaskStatus.ASSIGNED: {
            AgentTaskStatus.RUNNING,
            AgentTaskStatus.CANCELLED,
        },
        AgentTaskStatus.RUNNING: {
            AgentTaskStatus.WAITING,
            AgentTaskStatus.SUCCEEDED,
            AgentTaskStatus.FAILED,
            AgentTaskStatus.CANCELLED,
        },
        AgentTaskStatus.WAITING: {
            AgentTaskStatus.RUNNING,
            AgentTaskStatus.BLOCKED,
            AgentTaskStatus.CANCELLED,
        },
        AgentTaskStatus.SUCCEEDED: set(),
        AgentTaskStatus.FAILED: {
            AgentTaskStatus.RETRYING,
        },
        AgentTaskStatus.RETRYING: {
            AgentTaskStatus.PENDING,
            AgentTaskStatus.CANCELLED,
        },
        AgentTaskStatus.BLOCKED: {
            AgentTaskStatus.READY,
            AgentTaskStatus.CANCELLED,
        },
        AgentTaskStatus.CANCELLED: set(),
    }

    @classmethod
    def can_transition(
        cls, from_status: AgentTaskStatus, to_status: AgentTaskStatus
    ) -> bool:
        return to_status in cls.VALID_TRANSITIONS.get(from_status, set())

    @classmethod
    def transition(cls, task: "AgentTask", new_status: AgentTaskStatus) -> "AgentTask":
        if not cls.can_transition(task.status, new_status):
            raise InvalidAgentTaskTransition(
                f"Cannot transition agent task from {task.status.value} to {new_status.value}"
            )
        task.status = new_status
        task.updated_at = utc_now()
        if new_status == AgentTaskStatus.RUNNING:
            task.started_at = utc_now()
        elif new_status in (
            AgentTaskStatus.SUCCEEDED,
            AgentTaskStatus.FAILED,
            AgentTaskStatus.CANCELLED,
        ):
            task.completed_at = utc_now()
        return task


def utc_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


from datetime import datetime
