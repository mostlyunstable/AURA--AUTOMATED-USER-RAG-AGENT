import os
import tempfile
from uuid import uuid4

import pytest

from core.application.tool_gateway import ToolGatewayImpl
from core.domain.agents.entities import AgentRun, ToolCall
from core.domain.agents.enums import AgentCapability
from core.domain.agents.tools import TOOL_SCHEMAS
from core.infrastructure.execution.artifact_collector import ArtifactCollector


class MockExecutionService:
    async def execute_command(self, env_id, command):
        from core.domain.execution.entities import CommandResult
        from core.domain.execution.enums import CommandStatus

        return CommandResult(
            environment_id=env_id,
            status=CommandStatus.SUCCEEDED,
            exit_code=0,
            stdout="test output",
            stderr="",
            duration_ms=100,
        )


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


class MockUOW:
    def __init__(self):
        self.tool_calls = MockToolCallRepo()
        self.execution_environments = MockExecutionEnvironmentRepo()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        pass


class MockExecutionEnvironmentRepo:
    def __init__(self, worktree_path="/tmp/test-worktree"):
        self.worktree_path = worktree_path

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
                worktree_path=self.worktree_path,
            )
        ]


class MockAgentPolicy:
    def __init__(self):
        self.allowed_capabilities = set(AgentCapability)
        self.denied_capabilities = set()
        self.max_iterations = 50
        self.max_tool_calls = 100
        self.max_runtime_seconds = 1800
        self.max_failed_actions = 5

    def is_allowed(self, capability):
        return capability in self.allowed_capabilities

    def check_limits(self, run):
        if run.iteration_count >= self.max_iterations:
            return f"Iteration limit exceeded"
        if run.tool_call_count >= self.max_tool_calls:
            return f"Tool call limit exceeded"
        return None


@pytest.fixture
def temp_worktree():
    with tempfile.TemporaryDirectory() as td:
        # Create a test file
        with open(os.path.join(td, "test.py"), "w") as f:
            f.write("print('hello')\n")
        # Create a subdirectory
        os.makedirs(os.path.join(td, "subdir"), exist_ok=True)
        with open(os.path.join(td, "subdir", "test2.py"), "w") as f:
            f.write("print('world')\n")
        yield td


@pytest.fixture
def agent_run():
    return AgentRun(
        mission_id=uuid4(),
        task_id=uuid4(),
        task_execution_id=uuid4(),
        agent_id=uuid4(),
    )


@pytest.fixture
def tool_gateway(temp_worktree):
    uow = MockUOW()
    uow.execution_environments = MockExecutionEnvironmentRepo(
        worktree_path=temp_worktree
    )
    exec_service = MockExecutionService()
    artifact_collector = ArtifactCollector(worktree_root=temp_worktree)
    policy = MockAgentPolicy()
    return ToolGatewayImpl(uow, exec_service, artifact_collector, policy)


@pytest.mark.asyncio
async def test_read_file_success(tool_gateway, agent_run, temp_worktree):
    result = await tool_gateway.execute_tool(
        agent_run, "READ_FILE", {"path": "test.py"}, temp_worktree
    )
    assert result.success is True
    assert "print('hello')" in result.output


@pytest.mark.asyncio
async def test_read_file_not_found(tool_gateway, agent_run, temp_worktree):
    result = await tool_gateway.execute_tool(
        agent_run, "READ_FILE", {"path": "nonexistent.py"}, temp_worktree
    )
    assert result.success is False
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_read_file_path_traversal(tool_gateway, agent_run, temp_worktree):
    # Try to read outside worktree
    result = await tool_gateway.execute_tool(
        agent_run, "READ_FILE", {"path": "../../../etc/passwd"}, temp_worktree
    )
    assert result.success is False
    assert "denied" in result.error.lower() or "access denied" in result.error.lower()


@pytest.mark.asyncio
async def test_write_file_success(tool_gateway, agent_run, temp_worktree):
    result = await tool_gateway.execute_tool(
        agent_run,
        "WRITE_FILE",
        {"path": "new_file.py", "content": "print('new')"},
        temp_worktree,
    )
    assert result.success is True
    # Verify file was created
    assert os.path.exists(os.path.join(temp_worktree, "new_file.py"))


@pytest.mark.asyncio
async def test_write_file_path_traversal(tool_gateway, agent_run, temp_worktree):
    # Try to write outside worktree
    result = await tool_gateway.execute_tool(
        agent_run,
        "WRITE_FILE",
        {"path": "../../../etc/evil.py", "content": "bad"},
        temp_worktree,
    )
    assert result.success is False
    assert "denied" in result.error.lower() or "access denied" in result.error.lower()


@pytest.mark.asyncio
async def test_list_directory(tool_gateway, agent_run, temp_worktree):
    result = await tool_gateway.execute_tool(
        agent_run, "LIST_DIRECTORY", {"path": "."}, temp_worktree
    )
    assert result.success is True
    assert isinstance(result.output, list)
    names = [item["name"] for item in result.output]
    assert "test.py" in names
    assert "subdir" in names


@pytest.mark.asyncio
async def test_search_repository(tool_gateway, agent_run, temp_worktree):
    result = await tool_gateway.execute_tool(
        agent_run, "SEARCH_REPOSITORY", {"query": "hello", "path": "."}, temp_worktree
    )
    assert result.success is True
    assert isinstance(result.output, list)


@pytest.mark.asyncio
async def test_get_git_status(tool_gateway, agent_run, temp_worktree):
    # Initialize git repo
    os.system(
        f"cd {temp_worktree} && git init -q && git config user.email 'test@test.com' && git config user.name 'Test' && git add . && git commit -m 'init' -q"
    )
    result = await tool_gateway.execute_tool(
        agent_run, "GET_GIT_STATUS", {"path": "."}, temp_worktree
    )
    # Should succeed (even if no changes)
    assert result.success is True


@pytest.mark.asyncio
async def test_get_git_diff(tool_gateway, agent_run, temp_worktree):
    # Initialize git repo
    os.system(
        f"cd {temp_worktree} && git init -q && git config user.email 'test@test.com' && git config user.name 'Test' && git add . && git commit -m 'init' -q"
    )
    result = await tool_gateway.execute_tool(
        agent_run, "GET_GIT_DIFF", {"path": "."}, temp_worktree
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_finish_task(tool_gateway, agent_run, temp_worktree):
    result = await tool_gateway.execute_tool(
        agent_run,
        "FINISH_TASK",
        {"summary": "Task done", "success": True},
        temp_worktree,
    )
    assert result.success is True
    assert result.metadata.get("finish_task") is True
    assert result.metadata.get("success") is True


@pytest.mark.asyncio
async def test_unknown_tool(tool_gateway, agent_run, temp_worktree):
    result = await tool_gateway.execute_tool(
        agent_run, "UNKNOWN_TOOL", {}, temp_worktree
    )
    assert result.success is False
    assert "unknown" in result.error.lower()


@pytest.mark.asyncio
async def test_iteration_limit(tool_gateway, agent_run, temp_worktree):
    agent_run.iteration_count = 50  # At limit
    result = await tool_gateway.execute_tool(
        agent_run, "READ_FILE", {"path": "test.py"}, temp_worktree
    )
    assert result.success is False
    assert "iteration limit" in result.error.lower()


@pytest.mark.asyncio
async def test_tool_call_limit(tool_gateway, agent_run, temp_worktree):
    agent_run.tool_call_count = 100  # At limit
    result = await tool_gateway.execute_tool(
        agent_run, "READ_FILE", {"path": "test.py"}, temp_worktree
    )
    assert result.success is False
    assert "tool call limit" in result.error.lower()
