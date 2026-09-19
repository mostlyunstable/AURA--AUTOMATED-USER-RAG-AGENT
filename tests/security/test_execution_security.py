import asyncio
import os
import tempfile
from uuid import uuid4

import pytest

from core.domain.execution.entities import (ExecutionCommand,
                                            ExecutionEnvironment)
from core.domain.execution.enums import CommandStatus
from core.infrastructure.execution.git_worktree import LocalGitWorktreeManager
from core.infrastructure.execution.local_sandbox import LocalSandboxManager


@pytest.fixture
def sandbox_manager():
    return LocalSandboxManager()


@pytest.fixture
def worktree_manager():
    return LocalGitWorktreeManager()


@pytest.mark.asyncio
async def test_path_traversal_protection(sandbox_manager):
    env = ExecutionEnvironment(
        id=uuid4(),
        mission_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        worktree_path="/tmp/aura-worktrees/env-1",
    )

    cmd = ExecutionCommand(
        executable="echo",
        arguments=["test"],
        working_directory="/tmp/aura-worktrees/env-1/../../etc",
    )

    result = await sandbox_manager.execute(env, cmd)
    assert result.status == CommandStatus.REJECTED
    assert "outside the allowed worktree" in result.failure_reason


@pytest.mark.asyncio
async def test_shell_execution_prohibited(sandbox_manager):
    # Try to execute bash -c
    env = ExecutionEnvironment(
        id=uuid4(),
        mission_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        worktree_path="/tmp/aura-worktrees/env-1",
    )

    cmd = ExecutionCommand(
        executable="bash",
        arguments=["-c", "echo hello"],
        working_directory="/tmp/aura-worktrees/env-1",
    )

    result = await sandbox_manager.execute(env, cmd)
    assert result.status == CommandStatus.REJECTED
    assert "not allowed" in result.failure_reason


@pytest.mark.asyncio
async def test_timeout_enforcement(sandbox_manager):
    env = ExecutionEnvironment(
        id=uuid4(),
        mission_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        worktree_path="/tmp/aura-worktrees/env-1",
    )
    os.makedirs(env.worktree_path, exist_ok=True)

    # We use python because it's allowed in AURA_ALLOWED_EXECUTABLES by default (python3 usually)
    # Let's add sleep to allowed just for this test, or we can use python -c "import time; time.sleep(10)"
    cmd = ExecutionCommand(
        executable="python3",
        arguments=["-c", "import time; time.sleep(10)"],
        working_directory=env.worktree_path,
        timeout_seconds=1,
    )

    result = await sandbox_manager.execute(env, cmd)
    assert result.status == CommandStatus.TIMED_OUT
    assert result.timed_out is True


@pytest.mark.asyncio
async def test_output_truncation(sandbox_manager):
    # Monkeypatch max stdout for test
    sandbox_manager.max_stdout = 10

    env = ExecutionEnvironment(
        id=uuid4(),
        mission_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        worktree_path="/tmp/aura-worktrees/env-1",
    )
    os.makedirs(env.worktree_path, exist_ok=True)

    cmd = ExecutionCommand(
        executable="python3",
        arguments=["-c", "print('A' * 100)"],
        working_directory=env.worktree_path,
        timeout_seconds=5,
    )

    result = await sandbox_manager.execute(env, cmd)
    assert result.status == CommandStatus.SUCCEEDED
    assert result.output_truncated is True
    assert "[TRUNCATED]" in result.stdout
    assert len(result.stdout) < 50
