import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.application.verification_engine import VerificationEngine
from core.domain.agents.verification import (
    TaskContext,
    VerificationCheck,
    VerificationCheckResult,
    VerificationCheckType,
    VerificationResult,
    VerificationStatus,
)
from core.infrastructure.execution.artifact_collector import ArtifactCollector


class MockUOW:
    def __init__(self):
        self.verification_results = MockVerificationRepo()
        self.events = MockEventRepo()
        self.execution_environments = MockExecutionEnvRepo()
        self.command_executions = MockCommandExecRepo()
        self.artifacts = MockArtifactRepo()
        self.tool_calls = MockToolCallRepo()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        pass


class MockEventRepo:
    def __init__(self):
        self.events = []

    async def append(self, event):
        self.events.append(event)


class MockVerificationRepo:
    def __init__(self):
        self.verifications = []

    async def create(self, v):
        self.verifications.append(v)

    async def update(self, v):
        pass


class MockExecutionEnvRepo:
    def __init__(self):
        self.env_id = uuid4()

    async def get_by_task_execution(self, task_execution_id):
        from core.domain.execution.entities import ExecutionEnvironment
        from core.domain.execution.enums import EnvironmentStatus

        return [
            ExecutionEnvironment(
                id=self.env_id,
                mission_id=uuid4(),
                task_id=uuid4(),
                execution_id=task_execution_id,
                status=EnvironmentStatus.READY,
                worktree_path="/tmp/test-worktree",
            )
        ]


class MockCommandExecRepo:
    def __init__(self):
        self.commands = []

    async def get_by_environment(self, env_id):
        return self.commands

    async def create(self, result):
        self.commands.append(result)


class MockArtifactRepo:
    async def get_by_environment(self, env_id):
        return []

    async def create(self, artifact):
        pass


class MockToolCallRepo:
    def __init__(self):
        self.calls = []

    async def get_by_agent_run(self, agent_run_id):
        return self.calls


@pytest.fixture
def temp_worktree():
    with tempfile.TemporaryDirectory() as td:
        # Create a test file
        with open(os.path.join(td, "test.py"), "w") as f:
            f.write("def add(a, b):\n    return a + b\n")
        # Initialize git repo
        os.system(
            f"cd {td} && git init -q && git config user.email 'test@test.com' && git config user.name 'Test' && git add . && git commit -m 'init' -q"
        )
        yield td


@pytest.fixture
def task_context(temp_worktree):
    return TaskContext(
        mission_id=uuid4(),
        task_id=uuid4(),
        task_execution_id=uuid4(),
        agent_run_id=uuid4(),
        repository_root=temp_worktree,
        worktree_path=temp_worktree,
        task_objective="Test task",
        acceptance_criteria=["Function add should return sum"],
        constraints=[],
        allowed_paths=[],
        available_tools=["READ_FILE", "WRITE_FILE", "RUN_TESTS"],
        available_capabilities=["READ_REPOSITORY", "WRITE_REPOSITORY", "RUN_TESTS"],
    )


@pytest.fixture
def verification_engine(temp_worktree):
    uow = MockUOW()
    artifact_collector = ArtifactCollector(worktree_root=temp_worktree)
    return VerificationEngine(uow, artifact_collector)


@pytest.mark.asyncio
async def test_verification_engine_creation(verification_engine):
    assert verification_engine is not None


@pytest.mark.asyncio
async def test_git_status_check(verification_engine, task_context, temp_worktree):
    check = await verification_engine._check_git_status(task_context, temp_worktree)
    assert check.check_type == VerificationCheckType.GIT_STATUS
    assert check.result in [
        VerificationCheckResult.PASSED,
        VerificationCheckResult.FAILED,
    ]


@pytest.mark.asyncio
async def test_git_diff_check(verification_engine, task_context, temp_worktree):
    check = await verification_engine._check_git_diff(task_context, temp_worktree)
    assert check.check_type == VerificationCheckType.GIT_DIFF
    assert check.result in [
        VerificationCheckResult.PASSED,
        VerificationCheckResult.FAILED,
    ]


@pytest.mark.asyncio
async def test_scope_check_with_allowed_paths(verification_engine, temp_worktree):
    # Create a file outside allowed paths
    with open(os.path.join(temp_worktree, "allowed.py"), "w") as f:
        f.write("pass")

    # Create a file that would be outside if we had allowed paths
    context = TaskContext(
        mission_id=uuid4(),
        task_id=uuid4(),
        task_execution_id=uuid4(),
        agent_run_id=uuid4(),
        repository_root=temp_worktree,
        worktree_path=temp_worktree,
        task_objective="Test",
        acceptance_criteria=[],
        constraints=[],
        allowed_paths=["allowed.py"],  # Only this file is allowed
        available_tools=[],
        available_capabilities=[],
    )

    check = await verification_engine._check_scope(context, temp_worktree)
    assert check.check_type == VerificationCheckType.SCOPE


@pytest.mark.asyncio
async def test_secret_leakage_check(verification_engine, task_context, temp_worktree):
    # Create a diff with a secret
    with open(os.path.join(temp_worktree, "secret.py"), "w") as f:
        f.write('API_KEY = "sk-test-12345"\n')
    os.system(f"cd {temp_worktree} && git add . && git commit -m 'add secret' -q")

    check = await verification_engine._check_secret_leakage(task_context, temp_worktree)
    assert check.check_type == VerificationCheckType.SECRET_LEAKAGE


@pytest.mark.asyncio
async def test_unexpected_changes_check(
    verification_engine, task_context, temp_worktree
):
    check = await verification_engine._check_unexpected_changes(
        task_context, temp_worktree
    )
    assert check.check_type == VerificationCheckType.UNEXPECTED_CHANGES


@pytest.mark.asyncio
async def test_full_verification_flow(verification_engine, task_context, temp_worktree):
    result = await verification_engine.verify(
        task_context,
        task_context.agent_run_id,
        temp_worktree,
        task_context.task_execution_id,
    )
    assert isinstance(result, VerificationResult)
    assert result.status in [
        VerificationStatus.PASSED,
        VerificationStatus.FAILED,
        VerificationStatus.INCONCLUSIVE,
    ]
    assert len(result.checks) > 0


@pytest.mark.asyncio
async def test_artifact_and_command_queries_use_environment_id(
    verification_engine, task_context, temp_worktree
):
    """Artifacts/commands must be queried by environment ID, not execution ID."""
    from core.domain.execution.entities import Artifact
    from core.domain.execution.enums import ArtifactType

    requested_env_ids = []
    orig_artifacts = verification_engine.uow.artifacts.get_by_environment
    orig_commands = verification_engine.uow.command_executions.get_by_environment

    async def spy_artifacts(env_id):
        requested_env_ids.append(("artifacts", env_id))
        return [
            Artifact(
                environment_id=env_id,
                path="out.log",
                type=ArtifactType.LOG,
                size=3,
                sha256="abc",
            )
        ]

    async def spy_commands(env_id):
        requested_env_ids.append(("commands", env_id))
        return []

    verification_engine.uow.artifacts.get_by_environment = spy_artifacts
    verification_engine.uow.command_executions.get_by_environment = spy_commands
    try:
        envs = (
            await verification_engine.uow.execution_environments.get_by_task_execution(
                task_context.task_execution_id
            )
        )
        env_id = envs[0].id
        # The execution ID must differ from the environment ID for this
        # test to prove the correct identifier is used.
        assert env_id != task_context.task_execution_id

        artifacts_check = await verification_engine._check_artifacts(
            task_context, task_context.task_execution_id
        )
        failures_check = await verification_engine._check_execution_failures(
            task_context, task_context.task_execution_id
        )

        assert artifacts_check.result == VerificationCheckResult.PASSED
        assert ("artifacts", env_id) in requested_env_ids
        assert ("commands", env_id) in requested_env_ids
        assert failures_check.result == VerificationCheckResult.PASSED
    finally:
        verification_engine.uow.artifacts.get_by_environment = orig_artifacts
        verification_engine.uow.command_executions.get_by_environment = orig_commands


@pytest.mark.asyncio
async def test_verification_with_failed_git():
    # Test with a non-git directory
    with tempfile.TemporaryDirectory() as td:
        uow = MockUOW()
        artifact_collector = ArtifactCollector(worktree_root=td)
        engine = VerificationEngine(uow, artifact_collector)

        context = TaskContext(
            mission_id=uuid4(),
            task_id=uuid4(),
            task_execution_id=uuid4(),
            agent_run_id=uuid4(),
            repository_root=td,
            worktree_path=td,
            task_objective="Test",
        )

        check = await engine._check_git_status(context, td)
        assert check.result == VerificationCheckResult.FAILED
