import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from core.application.orphan_recovery import OrphanRecoveryService
from core.domain.execution.entities import ExecutionEnvironment
from core.domain.execution.enums import EnvironmentStatus


class MockUoW:
    def __init__(self):
        self.environments = {}
        self.events = []

    class MockEnvRepo:
        def __init__(self, environments):
            self.environments = environments

        async def get(self, id):
            return self.environments.get(id)

        async def update(self, env):
            self.environments[env.id] = env

    class MockEvents:
        def __init__(self, events):
            self.events = events

        async def append(self, event):
            self.events.append(event)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_orphan_recovery(tmp_path):
    root = tmp_path / "worktrees"
    root.mkdir()

    # 1. Active env
    active_env_id = uuid4()
    active_dir = root / str(uuid4()) / str(uuid4()) / str(uuid4())
    active_dir.mkdir(parents=True)
    (active_dir / ".aura-environment").write_text(f"environment_id={active_env_id}")

    # 2. Orphan env
    orphan_env_id = uuid4()
    orphan_dir = root / str(uuid4()) / str(uuid4()) / str(uuid4())
    orphan_dir.mkdir(parents=True)
    (orphan_dir / ".aura-environment").write_text(f"environment_id={orphan_env_id}")

    # 3. Unknown directory
    unknown_dir = root / "some" / "random" / "path"
    unknown_dir.mkdir(parents=True)

    uow = MockUoW()
    active_env = ExecutionEnvironment(
        id=active_env_id,
        mission_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        status=EnvironmentStatus.READY,
    )
    uow.environments[active_env_id] = active_env
    uow.execution_environments = uow.MockEnvRepo(uow.environments)
    uow.events = uow.MockEvents(uow.events)

    svc = OrphanRecoveryService(uow=uow, worktree_root=str(root))
    await svc.recover_orphans()

    assert os.path.exists(active_dir)
    assert not os.path.exists(orphan_dir)
    assert os.path.exists(unknown_dir)

    assert len(uow.events.events) == 2
    assert uow.events.events[0].event_type == "execution.environment.orphan_detected"
    assert uow.events.events[1].event_type == "execution.environment.recovered"
