from uuid import uuid4

import pytest

from core.application.execution_service import ExecutionService
from core.domain.execution.enums import EnvironmentStatus


class FakeEnvRepo:
    def __init__(self, envs):
        self.envs = list(envs)
        self.created = []

    async def create(self, env):
        self.created.append(env)
        self.envs.append(env)

    async def get(self, env_id):
        return next((e for e in self.envs if e.id == env_id), None)

    async def update(self, env):
        pass

    async def get_by_task_execution(self, execution_id):
        return [e for e in self.envs if e.execution_id == execution_id]


class FakeEventRepo:
    def __init__(self):
        self.events = []

    async def append(self, event):
        self.events.append(event)


class FakeUOW:
    def __init__(self, envs):
        self.execution_environments = FakeEnvRepo(envs)
        self.events = FakeEventRepo()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def commit(self):
        pass


class FakeWorktreeManager:
    def __init__(self):
        self.created = 0

    async def get_base_commit(self, repository_id):
        return "sha"

    async def create(self, env, repository_id):
        self.created += 1
        return f"/tmp/worktree-{self.created}"


class FakeSandboxManager:
    async def create(self, env):
        pass

    async def destroy(self, env):
        pass


def make_env(execution_id, status=EnvironmentStatus.READY):
    from core.domain.execution.entities import ExecutionEnvironment

    return ExecutionEnvironment(
        mission_id=uuid4(),
        task_id=uuid4(),
        execution_id=execution_id,
        status=status,
        worktree_path="/tmp/existing-worktree",
    )


@pytest.mark.asyncio
async def test_create_environment_is_idempotent_for_ready_env():
    execution_id = uuid4()
    existing = make_env(execution_id, EnvironmentStatus.READY)
    uow = FakeUOW([existing])
    worktree = FakeWorktreeManager()
    service = ExecutionService(uow, worktree, FakeSandboxManager())

    env = await service.create_environment(
        existing.mission_id, existing.task_id, execution_id, "repo"
    )

    assert env.id == existing.id
    assert worktree.created == 0
    assert uow.execution_environments.created == []


@pytest.mark.asyncio
async def test_create_environment_creates_new_when_none_ready():
    execution_id = uuid4()
    failed = make_env(execution_id, EnvironmentStatus.FAILED)
    uow = FakeUOW([failed])
    worktree = FakeWorktreeManager()
    service = ExecutionService(uow, worktree, FakeSandboxManager())

    env = await service.create_environment(
        failed.mission_id, failed.task_id, execution_id, "repo"
    )

    assert env.id != failed.id
    assert worktree.created == 1
