import asyncio
import os
import tempfile
from uuid import uuid4

import pytest

from core.application.coding_agent import CodingAgent
from core.domain.agents.entities import Agent, AgentRun
from core.domain.agents.enums import AgentCapability, AgentRunStatus, AgentType
from core.domain.agents.interfaces import AgentPolicy, ToolGateway, ToolResult
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
        self.agent_runs = MockAgentRunRepo()
        self.tasks = MockTaskRepo()
        self.events = MockEventRepo()
        self.tool_calls = MockToolCallRepo()
        self.verification_results = MockVerificationRepo()
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


class MockVerificationRepo:
    async def create(self, v):
        pass

    async def update(self, v):
        pass


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
        pass

    async def get_by_agent_run(self, agent_run_id):
        return [c for c in self.calls if c.agent_run_id == agent_run_id]


class MockVerificationEngine:
    def __init__(self, should_pass=True):
        self.should_pass = should_pass

    async def verify(self, context, agent_run_id, worktree_path, execution_id):
        from core.domain.agents.verification import (
            VerificationResult,
            VerificationStatus,
        )

        return VerificationResult(
            agent_run_id=agent_run_id,
            task_execution_id=context.task_execution_id,
            status=(
                VerificationStatus.PASSED
                if self.should_pass
                else VerificationStatus.FAILED
            ),
            success=self.should_pass,
            checks=[],
            failed_checks=[],
            warnings=[],
            changed_files=[],
            test_results={},
        )


@pytest.fixture
def mock_uow():
    return MockUOW()


@pytest.fixture
def agent():
    return Agent(
        name="test-coding-agent",
        agent_type=AgentType.CODING_AGENT,
        capabilities=[
            AgentCapability.READ_REPOSITORY,
            AgentCapability.WRITE_REPOSITORY,
            AgentCapability.FINISH_TASK,
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


@pytest.fixture
def tool_gateway():
    return MockToolGateway()


@pytest.fixture
def llm_provider():
    return MockLLMProvider()


@pytest.fixture
def verification_engine():
    return MockVerificationEngine()


@pytest.mark.asyncio
async def test_coding_agent_finishes_task(
    mock_uow, agent, agent_policy, tool_gateway, llm_provider, verification_engine
):
    task_id = uuid4()
    task_execution_id = uuid4()

    from core.domain.tasks.entities import TaskExecution

    # Task is RUNNING, as a worker would leave it on claim.
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

    runtime = CodingAgent(
        uow=mock_uow,
        llm_provider=llm_provider,
        tool_gateway=tool_gateway,
        agent_policy=agent_policy,
        agent=agent,
        verification_engine=verification_engine,
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
    assert mock_uow.tasks.tasks[task_id].status == TaskStatus.SUCCEEDED
    assert (
        mock_uow.task_executions.executions[task_execution_id].status
        == TaskStatus.SUCCEEDED
    )


@pytest.mark.asyncio
async def test_coding_agent_verification_failure_recovery(
    mock_uow, agent, agent_policy, tool_gateway, llm_provider
):
    # First verification fails, second passes
    verification_engine = MockVerificationEngine(should_pass=False)
    # Override to pass on second call
    call_count = [0]
    original_verify = verification_engine.verify

    async def mock_verify(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            from core.domain.agents.verification import (
                VerificationResult,
                VerificationStatus,
            )

            return VerificationResult(
                agent_run_id=args[1],
                task_execution_id=args[0].task_execution_id,
                status=VerificationStatus.FAILED,
                success=False,
                checks=[],
                failed_checks=[],
                warnings=[],
                changed_files=[],
                test_results={},
                failure_reason="Test verification failed",
            )
        return await original_verify(*args, **kwargs)

    verification_engine.verify = mock_verify

    task_id = uuid4()
    task_execution_id = uuid4()

    mock_uow.tasks.tasks[task_id] = Task(
        id=task_id,
        mission_id=uuid4(),
        title="Test Task",
        description="Test",
        task_type=TaskType.IMPLEMENTATION,
    )

    runtime = CodingAgent(
        uow=mock_uow,
        llm_provider=llm_provider,
        tool_gateway=tool_gateway,
        agent_policy=agent_policy,
        agent=agent,
        verification_engine=verification_engine,
    )

    result = await runtime.run(
        task_id=task_id,
        task_execution_id=task_execution_id,
        agent_id=agent.id,
        worktree_path="/tmp/test",
        repository_id="test-repo",
    )

    # Should fail after max recovery attempts
    assert result.status == AgentRunStatus.FAILED


@pytest.mark.asyncio
async def test_coding_agent_verification_failure_then_recovery(
    mock_uow, agent, agent_policy, tool_gateway, llm_provider
):
    # First verification fails, second passes
    call_count = [0]

    class ConditionalVerificationEngine:
        async def verify(self, context, agent_run_id, worktree_path, execution_id):
            from core.domain.agents.verification import (
                VerificationResult,
                VerificationStatus,
            )

            call_count[0] += 1
            if call_count[0] == 1:
                return VerificationResult(
                    agent_run_id=agent_run_id,
                    task_execution_id=context.task_execution_id,
                    status=VerificationStatus.FAILED,
                    success=False,
                    checks=[],
                    failed_checks=[],
                    warnings=[],
                    changed_files=[],
                    test_results={},
                    failure_reason="Test verification failed",
                )
            return VerificationResult(
                agent_run_id=agent_run_id,
                task_execution_id=context.task_execution_id,
                status=VerificationStatus.PASSED,
                success=True,
                checks=[],
                failed_checks=[],
                warnings=[],
                changed_files=[],
                test_results={},
            )

    verification_engine = ConditionalVerificationEngine()

    task_id = uuid4()
    task_execution_id = uuid4()

    mock_uow.tasks.tasks[task_id] = Task(
        id=task_id,
        mission_id=uuid4(),
        title="Test Task",
        description="Test",
        task_type=TaskType.IMPLEMENTATION,
    )

    runtime = CodingAgent(
        uow=mock_uow,
        llm_provider=llm_provider,
        tool_gateway=tool_gateway,
        agent_policy=agent_policy,
        agent=agent,
        verification_engine=verification_engine,
    )

    result = await runtime.run(
        task_id=task_id,
        task_execution_id=task_execution_id,
        agent_id=agent.id,
        worktree_path="/tmp/test",
        repository_id="test-repo",
    )

    # Should recover and pass
    assert result.status == AgentRunStatus.COMPLETED
    assert call_count[0] == 2


@pytest.mark.asyncio
async def test_coding_agent_iteration_limit(
    mock_uow, agent, agent_policy, tool_gateway, llm_provider
):
    # Create an LLM that never finishes
    class InfiniteLLM(LLMProvider):
        async def generate(self, request):
            import json

            content = json.dumps(
                {
                    "action_type": "READ_FILE",
                    "target": "test.py",
                    "arguments": {"path": "test.py"},
                    "rationale": "Reading file",
                    "expected_result": "File content",
                    "confidence": 1.0,
                }
            )
            return LLMResponse(
                content=content,
                provider="test",
                model="test",
                input_tokens=10,
                output_tokens=10,
                latency_ms=100,
                request_id="test",
                finish_reason="stop",
            )

    infinite_llm = InfiniteLLM()

    # Set very low iteration limit
    agent_policy.max_iterations = 3

    task_id = uuid4()
    task_execution_id = uuid4()

    mock_uow.tasks.tasks[task_id] = Task(
        id=task_id,
        mission_id=uuid4(),
        title="Test Task",
        description="Test",
        task_type=TaskType.IMPLEMENTATION,
    )

    runtime = CodingAgent(
        uow=mock_uow,
        llm_provider=infinite_llm,
        tool_gateway=tool_gateway,
        agent_policy=agent_policy,
        agent=agent,
        verification_engine=MockVerificationEngine(),
    )

    result = await runtime.run(
        task_id=task_id,
        task_execution_id=task_execution_id,
        agent_id=agent.id,
        worktree_path="/tmp/test",
        repository_id="test-repo",
    )

    assert result.status == AgentRunStatus.FAILED
    assert (
        "iteration limit" in result.failure_reason.lower()
        or result.iteration_count >= 3
    )


@pytest.mark.asyncio
async def test_coding_agent_tool_call_limit(
    mock_uow, agent, agent_policy, tool_gateway, llm_provider
):
    class InfiniteLLM(LLMProvider):
        async def generate(self, request):
            import json

            content = json.dumps(
                {
                    "action_type": "READ_FILE",
                    "target": "test.py",
                    "arguments": {"path": "test.py"},
                    "rationale": "Reading file",
                    "expected_result": "File content",
                    "confidence": 1.0,
                }
            )
            return LLMResponse(
                content=content,
                provider="test",
                model="test",
                input_tokens=10,
                output_tokens=10,
                latency_ms=100,
                request_id="test",
                finish_reason="stop",
            )

    agent_policy.max_tool_calls = 3

    task_id = uuid4()
    task_execution_id = uuid4()

    mock_uow.tasks.tasks[task_id] = Task(
        id=task_id,
        mission_id=uuid4(),
        title="Test Task",
        description="Test",
        task_type=TaskType.IMPLEMENTATION,
    )

    runtime = CodingAgent(
        uow=mock_uow,
        llm_provider=InfiniteLLM(),
        tool_gateway=tool_gateway,
        agent_policy=agent_policy,
        agent=agent,
        verification_engine=MockVerificationEngine(),
    )

    result = await runtime.run(
        task_id=task_id,
        task_execution_id=task_execution_id,
        agent_id=agent.id,
        worktree_path="/tmp/test",
        repository_id="test-repo",
    )

    assert result.status == AgentRunStatus.FAILED
    assert result.tool_call_count >= 3
