from typing import Set

from core.domain.agents.entities import AgentRun
from core.domain.agents.enums import AgentRunStatus


class AgentRunStateMachine:
    VALID_TRANSITIONS: dict[AgentRunStatus, Set[AgentRunStatus]] = {
        AgentRunStatus.CREATED: {AgentRunStatus.READY},
        AgentRunStatus.READY: {AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED},
        AgentRunStatus.RUNNING: {
            AgentRunStatus.VERIFYING,
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.TIMED_OUT,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.BLOCKED,
            AgentRunStatus.POLICY_REJECTED,
        },
        AgentRunStatus.VERIFYING: {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.RUNNING,
            AgentRunStatus.CANCELLED,
        },
        AgentRunStatus.COMPLETED: set(),
        AgentRunStatus.FAILED: set(),
        AgentRunStatus.TIMED_OUT: set(),
        AgentRunStatus.CANCELLED: set(),
        AgentRunStatus.BLOCKED: {AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED},
        AgentRunStatus.POLICY_REJECTED: {
            AgentRunStatus.RUNNING,
            AgentRunStatus.CANCELLED,
        },
    }

    @classmethod
    def can_transition(
        cls, from_status: AgentRunStatus, to_status: AgentRunStatus
    ) -> bool:
        return to_status in cls.VALID_TRANSITIONS.get(from_status, set())

    @classmethod
    def transition(cls, run: AgentRun, new_status: AgentRunStatus) -> AgentRun:
        if not cls.can_transition(run.status, new_status):
            raise InvalidAgentRunTransition(
                f"Cannot transition from {run.status.value} to {new_status.value}"
            )
        run.status = new_status
        run.updated_at = utc_now()
        return run


class InvalidAgentRunTransition(Exception):
    pass


def utc_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
