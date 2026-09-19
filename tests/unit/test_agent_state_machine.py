import pytest

from core.domain.agents.entities import Agent, AgentRun, ToolCall
from core.domain.agents.enums import (
    AgentCapability,
    AgentRunStatus,
    AgentStatus,
    AgentType,
    ToolCallStatus,
)
from core.domain.agents.state_machine import (
    AgentRunStateMachine,
    InvalidAgentRunTransition,
)


def test_agent_creation():
    agent = Agent(
        name="test-agent",
        agent_type=AgentType.CODING_AGENT,
        capabilities=[
            AgentCapability.READ_REPOSITORY,
            AgentCapability.WRITE_REPOSITORY,
        ],
    )
    assert agent.name == "test-agent"
    assert agent.agent_type == AgentType.CODING_AGENT
    assert AgentCapability.READ_REPOSITORY in agent.capabilities
    assert agent.status == AgentStatus.ACTIVE


def test_agent_run_creation():
    from uuid import uuid4

    agent_run = AgentRun(
        mission_id=uuid4(),
        task_id=uuid4(),
        task_execution_id=uuid4(),
        agent_id=uuid4(),
    )
    assert agent_run.status == AgentRunStatus.CREATED
    assert agent_run.iteration_count == 0
    assert agent_run.tool_call_count == 0


def test_valid_state_transition():
    from uuid import uuid4

    agent_run = AgentRun(
        mission_id=uuid4(),
        task_id=uuid4(),
        task_execution_id=uuid4(),
        agent_id=uuid4(),
    )
    assert agent_run.status == AgentRunStatus.CREATED

    updated = AgentRunStateMachine.transition(agent_run, AgentRunStatus.READY)
    assert updated.status == AgentRunStatus.READY

    updated = AgentRunStateMachine.transition(updated, AgentRunStatus.RUNNING)
    assert updated.status == AgentRunStatus.RUNNING

    updated = AgentRunStateMachine.transition(updated, AgentRunStatus.VERIFYING)
    assert updated.status == AgentRunStatus.VERIFYING

    updated = AgentRunStateMachine.transition(updated, AgentRunStatus.COMPLETED)
    assert updated.status == AgentRunStatus.COMPLETED


def test_invalid_state_transition():
    from uuid import uuid4

    agent_run = AgentRun(
        mission_id=uuid4(),
        task_id=uuid4(),
        task_execution_id=uuid4(),
        agent_id=uuid4(),
    )

    with pytest.raises(InvalidAgentRunTransition):
        AgentRunStateMachine.transition(agent_run, AgentRunStatus.RUNNING)


def test_terminal_states():
    from uuid import uuid4

    terminal_states = [
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.TIMED_OUT,
        AgentRunStatus.CANCELLED,
    ]
    for status in terminal_states:
        agent_run = AgentRun(
            mission_id=uuid4(),
            task_id=uuid4(),
            task_execution_id=uuid4(),
            agent_id=uuid4(),
            status=status,
        )
        with pytest.raises(InvalidAgentRunTransition):
            AgentRunStateMachine.transition(agent_run, AgentRunStatus.CREATED)


def test_recovery_flow():
    from uuid import uuid4

    agent_run = AgentRun(
        mission_id=uuid4(),
        task_id=uuid4(),
        task_execution_id=uuid4(),
        agent_id=uuid4(),
        status=AgentRunStatus.RUNNING,
    )
    updated = AgentRunStateMachine.transition(agent_run, AgentRunStatus.BLOCKED)
    assert updated.status == AgentRunStatus.BLOCKED
    updated = AgentRunStateMachine.transition(updated, AgentRunStatus.RUNNING)
    assert updated.status == AgentRunStatus.RUNNING


def test_policy_rejected_flow():
    from uuid import uuid4

    agent_run = AgentRun(
        mission_id=uuid4(),
        task_id=uuid4(),
        task_execution_id=uuid4(),
        agent_id=uuid4(),
        status=AgentRunStatus.RUNNING,
    )
    updated = AgentRunStateMachine.transition(agent_run, AgentRunStatus.POLICY_REJECTED)
    assert updated.status == AgentRunStatus.POLICY_REJECTED
    updated = AgentRunStateMachine.transition(updated, AgentRunStatus.RUNNING)
    assert updated.status == AgentRunStatus.RUNNING


def test_tool_call_creation():
    from uuid import uuid4

    tool_call = ToolCall(
        agent_run_id=uuid4(),
        tool_name="READ_FILE",
        arguments={"path": "test.py"},
    )
    assert tool_call.tool_name == "READ_FILE"
    assert tool_call.status == ToolCallStatus.PENDING
    assert tool_call.policy_decision == ToolCallStatus.PENDING
