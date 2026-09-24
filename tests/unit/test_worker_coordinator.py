import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from core.application.interfaces import UnitOfWork
from core.application.worker_coordinator import WorkerCoordinator
from core.domain.agents.entities import Agent
from core.domain.agents.enums import AgentCapability, AgentType
from core.domain.missions.enums import MissionStatus
from core.domain.tasks.entities import Task, TaskExecution
from core.domain.tasks.enums import TaskStatus, TaskType
from core.domain.workers.entities import TaskLease, Worker
from core.domain.workers.enums import WorkerCapability, WorkerStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MockUOW:
    def __init__(self):
        self.missions = MagicMock()
        self.missions.get = AsyncMock()
        self.tasks = MagicMock()
        self.tasks.get_by_mission = AsyncMock()
        self.tasks.claim_task = AsyncMock()
        self.tasks.update = AsyncMock()
        self.task_dependencies = MagicMock()
        self.task_dependencies.get_dependencies_for_mission = AsyncMock()
        self.task_executions = MagicMock()
        self.task_executions.add = AsyncMock()
        self.task_executions.get = AsyncMock()
        self.task_executions.update = AsyncMock()
        self.task_leases = MagicMock()
        self.task_leases.create = AsyncMock()
        self.task_leases.get = AsyncMock()
        self.task_leases.update = AsyncMock()
        self.task_leases.get_stale_leases = AsyncMock()
        self.workers = MagicMock()
        self.workers.get_by_status = AsyncMock()
        self.workers.get = AsyncMock()
        self.workers.update = AsyncMock()
        self.workers.create = AsyncMock()
        self.worker_heartbeats = MagicMock()
        self.worker_heartbeats.create = AsyncMock()
        self.events = MagicMock()
        self.events.append = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def commit(self):
        pass


@pytest.fixture
def mock_uow_factory():
    uow = MockUOW()
    factory = lambda: uow
    return factory, uow


@pytest.fixture
def sample_mission():
    return MagicMock(
        id=uuid4(),
        status=MissionStatus.EXECUTING,
        repository_id="test-repo",
    )


@pytest.fixture
def sample_agent():
    return Agent(
        id=uuid4(),
        name="test-agent",
        agent_type=AgentType.CODING_AGENT,
        capabilities=[
            AgentCapability.READ_REPOSITORY,
            AgentCapability.WRITE_REPOSITORY,
        ],
    )


@pytest.fixture
def sample_worker():
    return Worker(
        id=uuid4(),
        name="test-worker",
        status=WorkerStatus.AVAILABLE,
        capabilities=[c.value for c in WorkerCapability],
    )


@pytest.fixture
def sample_task():
    return Task(
        id=uuid4(),
        mission_id=uuid4(),
        title="Test Task",
        description="Implement feature X",
        status=TaskStatus.QUEUED,
        task_type=TaskType.IMPLEMENTATION,
        priority=1,
        attempt_count=0,
        max_attempts=3,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


@pytest.fixture
def sample_execution():
    return TaskExecution(
        id=uuid4(),
        task_id=uuid4(),
        agent_id=uuid4(),
        attempt_number=1,
        status=TaskStatus.RUNNING,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


@pytest.fixture
def sample_lease(sample_worker, sample_task, sample_execution):
    return TaskLease(
        id=uuid4(),
        worker_id=sample_worker.id,
        task_id=sample_task.id,
        task_execution_id=sample_execution.id,
        claimed_at=utc_now(),
        lease_expires_at=utc_now() + timedelta(seconds=90),
        last_heartbeat_at=utc_now(),
        renewed_count=0,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


class TestWorkerCoordinator:
    @pytest.mark.asyncio
    async def test_register_creates_new_worker(self, mock_uow_factory, sample_agent):
        factory, uow = mock_uow_factory
        uow.workers.get_by_status = AsyncMock(return_value=[])
        uow.workers.create = AsyncMock()
        uow.workers.update = AsyncMock()
        uow.events.append = AsyncMock()

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=uuid4(),
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
            worker_name="test-worker",
        )

        worker = await coordinator.register()

        assert worker.name == "test-worker"
        assert worker.status == WorkerStatus.AVAILABLE
        uow.workers.create.assert_called_once()
        uow.events.append.assert_called()

    @pytest.mark.asyncio
    async def test_register_reuses_existing_worker(
        self, mock_uow_factory, sample_agent, sample_worker
    ):
        factory, uow = mock_uow_factory
        uow.workers.get_by_status = AsyncMock(return_value=[sample_worker])
        uow.workers.update = AsyncMock()
        uow.events.append = AsyncMock()

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=uuid4(),
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
            worker_name="test-worker",
        )

        worker = await coordinator.register()

        assert worker.id == sample_worker.id
        uow.workers.create.assert_not_called()
        uow.workers.update.assert_called()

    @pytest.mark.asyncio
    async def test_claim_next_task_mission_not_executing(
        self, mock_uow_factory, sample_agent, sample_mission
    ):
        factory, uow = mock_uow_factory
        sample_mission.status = MissionStatus.PLANNING
        uow.missions.get = AsyncMock(return_value=sample_mission)

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=sample_mission.id,
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
        )

        result = await coordinator.claim_next_task()

        assert result is None

    @pytest.mark.asyncio
    async def test_claim_next_task_no_ready_tasks(
        self, mock_uow_factory, sample_agent, sample_mission
    ):
        factory, uow = mock_uow_factory
        uow.missions.get = AsyncMock(return_value=sample_mission)
        uow.tasks.get_by_mission = AsyncMock(return_value=[])
        uow.task_dependencies.get_dependencies_for_mission = AsyncMock(return_value=[])

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=sample_mission.id,
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
        )
        await coordinator.register()

        result = await coordinator.claim_next_task()

        assert result is None

    @pytest.mark.asyncio
    async def test_claim_next_task_skips_wrong_capability(
        self, mock_uow_factory, sample_agent, sample_mission, sample_task
    ):
        factory, uow = mock_uow_factory
        sample_task.task_type = TaskType.SECURITY_REVIEW
        uow.missions.get = AsyncMock(return_value=sample_mission)
        uow.tasks.get_by_mission = AsyncMock(return_value=[sample_task])
        uow.task_dependencies.get_dependencies_for_mission = AsyncMock(return_value=[])

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=sample_mission.id,
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
            capabilities=[WorkerCapability.CODING.value],
        )
        await coordinator.register()

        result = await coordinator.claim_next_task()

        assert result is None

    @pytest.mark.asyncio
    async def test_claim_next_task_claims_eligible_task(
        self, mock_uow_factory, sample_agent, sample_mission, sample_task, sample_worker
    ):
        factory, uow = mock_uow_factory
        claimed_task = Task(
            id=sample_task.id,
            mission_id=sample_task.mission_id,
            title=sample_task.title,
            description=sample_task.description,
            status=TaskStatus.RUNNING,
            task_type=sample_task.task_type,
            priority=sample_task.priority,
            assigned_agent_id=sample_worker.id,
            attempt_count=1,
            max_attempts=sample_task.max_attempts,
            created_at=sample_task.created_at,
            updated_at=utc_now(),
        )
        uow.missions.get = AsyncMock(return_value=sample_mission)
        uow.tasks.get_by_mission = AsyncMock(return_value=[sample_task])
        uow.task_dependencies.get_dependencies_for_mission = AsyncMock(return_value=[])
        uow.tasks.claim_task = AsyncMock(return_value=claimed_task)
        uow.task_executions.add = AsyncMock()
        uow.task_leases.create = AsyncMock()
        uow.workers.update = AsyncMock()
        uow.events.append = AsyncMock()

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=sample_mission.id,
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
            capabilities=[WorkerCapability.CODING.value],
        )
        coordinator._worker_internal = sample_worker

        result = await coordinator.claim_next_task()

        assert result is not None
        task, execution, lease = result
        assert task.id == sample_task.id
        assert execution.task_id == sample_task.id
        assert lease.worker_id == sample_worker.id
        uow.tasks.claim_task.assert_called_once_with(sample_task.id, sample_worker.id)
        uow.task_executions.add.assert_called_once()
        uow.task_leases.create.assert_called_once()
        uow.events.append.assert_called()

    @pytest.mark.asyncio
    async def test_claim_next_task_lost_race_continues(
        self, mock_uow_factory, sample_agent, sample_mission, sample_task, sample_worker
    ):
        factory, uow = mock_uow_factory
        uow.missions.get = AsyncMock(return_value=sample_mission)
        uow.tasks.get_by_mission = AsyncMock(return_value=[sample_task])
        uow.task_dependencies.get_dependencies_for_mission = AsyncMock(return_value=[])
        uow.tasks.claim_task = AsyncMock(return_value=None)

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=sample_mission.id,
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
            capabilities=[WorkerCapability.CODING.value],
        )
        coordinator._worker_internal = sample_worker

        result = await coordinator.claim_next_task()

        assert result is None

    @pytest.mark.asyncio
    async def test_renew_lease_success(
        self, mock_uow_factory, sample_agent, sample_worker, sample_lease
    ):
        factory, uow = mock_uow_factory
        uow.task_leases.get = AsyncMock(return_value=sample_lease)
        uow.task_leases.update = AsyncMock()
        uow.worker_heartbeats.create = AsyncMock()
        uow.workers.get = AsyncMock(return_value=sample_worker)
        uow.workers.update = AsyncMock()

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=uuid4(),
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
        )
        coordinator._worker_internal = sample_worker

        result = await coordinator.renew_lease(sample_lease.id)

        assert result is True
        uow.task_leases.get.assert_called_once_with(sample_lease.id)
        uow.task_leases.update.assert_called_once()
        uow.worker_heartbeats.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_renew_lease_fails_if_not_owner(
        self, mock_uow_factory, sample_agent, sample_worker, sample_lease
    ):
        factory, uow = mock_uow_factory
        sample_lease.worker_id = uuid4()
        uow.task_leases.get = AsyncMock(return_value=sample_lease)

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=uuid4(),
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
        )
        coordinator._worker_internal = sample_worker

        result = await coordinator.renew_lease(sample_lease.id)

        assert result is False

    @pytest.mark.asyncio
    async def test_renew_lease_fails_if_expired(
        self, mock_uow_factory, sample_agent, sample_worker, sample_lease
    ):
        factory, uow = mock_uow_factory
        sample_lease.lease_expires_at = utc_now() - timedelta(seconds=10)
        uow.task_leases.get = AsyncMock(return_value=sample_lease)

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=uuid4(),
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
        )
        coordinator._worker_internal = sample_worker

        result = await coordinator.renew_lease(sample_lease.id)

        assert result is False

    @pytest.mark.asyncio
    async def test_recover_stale_requeues_tasks(
        self,
        mock_uow_factory,
        sample_agent,
        sample_worker,
        sample_task,
        sample_lease,
        sample_execution,
    ):
        factory, uow = mock_uow_factory
        sample_lease.lease_expires_at = utc_now() - timedelta(seconds=10)
        uow.task_leases.get_stale_leases = AsyncMock(return_value=[sample_lease])
        uow.task_leases.get = AsyncMock(return_value=sample_lease)
        uow.tasks.get = AsyncMock(return_value=sample_task)
        uow.task_executions.get = AsyncMock(return_value=sample_execution)
        uow.tasks.update = AsyncMock()
        uow.task_executions.update = AsyncMock()
        uow.events.append = AsyncMock()

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=uuid4(),
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
        )
        coordinator._worker_internal = sample_worker

        with patch("core.application.worker_coordinator.TaskStateMachine") as mock_sm:
            mock_sm.transition = MagicMock()
            result = await coordinator.recover_stale()

        assert result == 1
        uow.task_leases.get_stale_leases.assert_called_once()
        uow.tasks.get.assert_called_once_with(sample_lease.task_id)
        uow.task_executions.get.assert_called_once_with(sample_lease.task_execution_id)

    @pytest.mark.asyncio
    async def test_recover_stale_skips_max_attempts(
        self,
        mock_uow_factory,
        sample_agent,
        sample_worker,
        sample_task,
        sample_lease,
        sample_execution,
    ):
        factory, uow = mock_uow_factory
        sample_lease.lease_expires_at = utc_now() - timedelta(seconds=10)
        sample_task.attempt_count = 3
        sample_task.max_attempts = 3
        uow.task_leases.get_stale_leases = AsyncMock(return_value=[sample_lease])
        uow.task_leases.get = AsyncMock(return_value=sample_lease)
        uow.tasks.get = AsyncMock(return_value=sample_task)

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=uuid4(),
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
        )
        coordinator._worker_internal = sample_worker

        with patch("core.application.worker_coordinator.TaskStateMachine") as mock_sm:
            mock_sm.transition = MagicMock()
            result = await coordinator.recover_stale()

        assert result == 0

    @pytest.mark.asyncio
    async def test_shutdown_sets_worker_stopped(
        self, mock_uow_factory, sample_agent, sample_worker
    ):
        factory, uow = mock_uow_factory
        uow.workers.get = AsyncMock(return_value=sample_worker)
        uow.workers.update = AsyncMock()

        coordinator = WorkerCoordinator(
            uow_factory=factory,
            mission_id=uuid4(),
            agent=sample_agent,
            execution_service_factory=lambda u: AsyncMock(),
            agent_runtime_factory=lambda u: AsyncMock(),
            verification_factory=lambda u: AsyncMock(),
        )
        coordinator._worker_internal = sample_worker

        with patch("core.application.worker_coordinator.WorkerStateMachine") as mock_sm:
            mock_sm.transition = MagicMock()
            await coordinator.shutdown(graceful=False)

        assert coordinator.running is False
        assert coordinator.draining is True
        mock_sm.transition.assert_called_with(sample_worker, WorkerStatus.STOPPED)
