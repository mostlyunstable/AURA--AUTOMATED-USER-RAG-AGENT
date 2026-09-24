import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.domain.agents.entities import Agent, AgentRun
from core.domain.agents.enums import AgentCapability, AgentRunStatus, AgentType
from core.domain.llm.interfaces import LLMProvider, LLMRequest, LLMResponse
from core.domain.tasks.entities import Task
from core.domain.tasks.enums import TaskStatus, TaskType


class MockLLMProvider(LLMProvider):
    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
        else:
            # Default to finish task
            import json

            content = json.dumps(
                {
                    "action_type": "FINISH_TASK",
                    "target": "task",
                    "arguments": {"summary": "Task completed", "success": True},
                    "rationale": "Task is done",
                    "expected_result": "Task marked complete",
                    "confidence": 1.0,
                }
            )
            resp = LLMResponse(
                content=content,
                provider="test",
                model="test",
                input_tokens=10,
                output_tokens=10,
                latency_ms=100,
                request_id="test",
                finish_reason="stop",
            )
        self.call_count += 1
        return resp


class MockToolGateway:
    def __init__(self):
        self.calls = []

    async def execute_tool(self, agent_run, tool_name, arguments, worktree_path):
        self.calls.append((tool_name, arguments))
        from core.domain.agents.interfaces import ToolResult

        if tool_name == "FINISH_TASK":
            return ToolResult(
                success=True,
                output={
                    "summary": arguments.get("summary", ""),
                    "success": arguments.get("success", True),
                },
                metadata={
                    "finish_task": True,
                    "success": arguments.get("success", True),
                },
            )
        return ToolResult(success=True, output="ok")


class MockUOW:
    def __init__(self):
        self.agent_runs = []
        self.events = []
        self.tasks = {}
        self.tool_calls = []
        self.task_executions = MockTaskExecutionRepo()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        pass


class MockTaskExecutionRepo:
    def __init__(self):
        self.executions = {}

    async def add(self, execution):
        self.executions[execution.id] = execution

    async def get(self, execution_id):
        return self.executions.get(execution_id)

    async def get_by_task(self, task_id):
        return [e for e in self.executions.values() if e.task_id == task_id]

    async def update(self, execution):
        self.executions[execution.id] = execution


class MockAgentRunRepo:
    def __init__(self):
        self.runs = {}

    async def create(self, run):
        self.runs[run.id] = run

    async def get(self, run_id):
        return self.runs.get(run_id)

    async def get_by_task_execution(self, task_execution_id):
        return [
            r for r in self.runs.values() if r.task_execution_id == task_execution_id
        ]

    async def update(self, run):
        self.runs[run.id] = run


class MockTaskRepo:
    def __init__(self):
        self.tasks = {}

    async def get(self, task_id):
        return self.tasks.get(task_id)

    async def update(self, task):
        self.tasks[task.id] = task


class MockEventRepo:
    def __init__(self):
        self.events = []

    async def append(self, event):
        self.events.append(event)


class MockToolCallRepo:
    def __init__(self):
        self.calls = []

    async def create(self, call):
        self.calls.append(call)

    async def update(self, call):
        for i, c in enumerate(self.calls):
            if c.id == call.id:
                self.calls[i] = call
                break

    async def get_by_agent_run(self, agent_run_id):
        return [c for c in self.calls if c.agent_run_id == agent_run_id]


class MockExecutionEnvRepo:
    async def get_by_task_execution(self, task_execution_id):
        from core.domain.execution.entities import ExecutionEnvironment
        from core.domain.execution.enums import EnvironmentStatus

        return [
            ExecutionEnvironment(
                id=uuid4(),
                mission_id=uuid4(),
                task_id=uuid4(),
                execution_id=task_execution_id,
                status=EnvironmentStatus.READY,
                worktree_path="/tmp/test",
            )
        ]


@pytest.fixture
def mock_uow():
    uow = MockUOW()
    uow.agent_runs = MockAgentRunRepo()
    uow.tasks = MockTaskRepo()
    uow.events = MockEventRepo()
    uow.tool_calls = MockToolCallRepo()
    uow.execution_environments = MockExecutionEnvRepo()
    return uow


@pytest.fixture
def agent():
    return Agent(
        name="test-coding-agent",
        agent_type=AgentType.CODING_AGENT,
        capabilities=[
            AgentCapability.READ_REPOSITORY,
            AgentCapability.WRITE_REPOSITORY,
        ],
    )


@pytest.fixture
def agent_policy():
    from core.domain.agents.interfaces import AgentPolicy

    return AgentPolicy(
        allowed_capabilities=[
            AgentCapability.READ_REPOSITORY,
            AgentCapability.WRITE_REPOSITORY,
            AgentCapability.FINISH_TASK,
        ],
        denied_capabilities=[],
        max_iterations=10,
        max_tool_calls=20,
        max_runtime_seconds=300,
        max_failed_actions=3,
    )


@pytest.mark.asyncio
async def test_agent_runtime_finishes_task(mock_uow, agent, agent_policy):
    from core.application.agent_runtime import CodingAgentRuntime

    llm_provider = MockLLMProvider()
    tool_gateway = MockToolGateway()

    runtime = CodingAgentRuntime(
        uow=mock_uow,
        llm_provider=llm_provider,
        tool_gateway=tool_gateway,
        agent_policy=agent_policy,
        agent=agent,
    )

    task_id = uuid4()
    task_execution_id = uuid4()

    # Add a mock task in RUNNING state, as a worker would leave it on claim.
    from core.domain.tasks.entities import TaskExecution

    mock_uow.tasks.tasks[task_id] = Task(
        id=task_id,
        mission_id=uuid4(),
        title="Test Task",
        description="Test",
        task_type=TaskType.IMPLEMENTATION,
        status=TaskStatus.RUNNING,
    )
    mock_uow.task_executions.executions[task_execution_id] = TaskExecution(
        id=task_execution_id,
        task_id=task_id,
        agent_id=agent.id,
        attempt_number=1,
        status=TaskStatus.RUNNING,
    )

    result = await runtime.run(
        task_id=task_id,
        task_execution_id=task_execution_id,
        agent_id=agent.id,
        worktree_path="/tmp/test",
        repository_id="test-repo",
    )

    assert result.status == AgentRunStatus.COMPLETED
    assert result.final_result is not None
    # FINISH_TASK is handled directly by the runtime, not through tool gateway
    # The tool gateway is for environment interactions only
    assert mock_uow.tasks.tasks[task_id].status == TaskStatus.SUCCEEDED
    assert (
        mock_uow.task_executions.executions[task_execution_id].status
        == TaskStatus.SUCCEEDED
    )
