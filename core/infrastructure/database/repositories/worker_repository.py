from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.application.interfaces import (
    AgentRepository,
    AgentRunRepository,
    ArtifactRepository,
    CommandExecutionRepository,
    EventRepository,
    ExecutionEnvironmentRepository,
    MissionRepository,
    PlanRepository,
    PullRequestRepository,
    TaskLeaseRepository,
    ToolCallRepository,
    UnitOfWork,
    VerificationResultRepository,
    WorkerHeartbeatRepository,
    WorkerRepository,
)
from core.domain.agents.entities import Agent, AgentRun, ToolCall
from core.domain.agents.enums import AgentStatus, AgentType, ToolCallStatus
from core.domain.agents.verification import VerificationResult
from core.domain.approvals.entities import Approval
from core.domain.approvals.enums import ApprovalStatus, ApprovalType
from core.domain.events.entities import Event
from core.domain.execution.entities import Artifact, CommandResult, ExecutionEnvironment
from core.domain.execution.enums import ArtifactType, CommandStatus, EnvironmentStatus
from core.domain.missions.entities import Mission
from core.domain.missions.enums import MissionStatus
from core.domain.plans.entities import EngineeringPlan, PlannerOutput
from core.domain.plans.enums import PlanStatus
from core.domain.pull_requests.entities import PullRequest
from core.domain.pull_requests.enums import PullRequestProvider, PullRequestStatus
from core.domain.tasks.entities import Task, TaskDependency, TaskExecution
from core.domain.tasks.enums import TaskStatus, TaskType
from core.domain.workers.entities import TaskLease, Worker, WorkerHeartbeat
from core.domain.workers.enums import WorkerCapability, WorkerStatus
from core.infrastructure.database.models import (
    AgentModel,
    AgentRunModel,
    ApprovalModel,
    ArtifactModel,
    CommandExecutionModel,
    EventModel,
    ExecutionEnvironmentModel,
    MissionModel,
    PlanModel,
    PullRequestModel,
    TaskDependencyModel,
    TaskExecutionModel,
    TaskLeaseModel,
    TaskModel,
    ToolCallModel,
    VerificationResultModel,
    WorkerHeartbeatModel,
    WorkerModel,
)


class SQLAlchemyWorkerRepository(WorkerRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: WorkerModel) -> Worker:
        return Worker(
            id=model.id,
            name=model.name,
            status=WorkerStatus(model.status),
            capabilities=[c for c in model.capabilities],
            capabilities_enum=[
                WorkerCapability(c)
                for c in model.capabilities
                if c in WorkerCapability.__members__
            ],
            last_heartbeat_at=model.last_heartbeat_at,
            metadata=model.metadata_ or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Worker) -> WorkerModel:
        return WorkerModel(
            id=entity.id,
            name=entity.name,
            status=entity.status.value,
            capabilities=[
                c.value if isinstance(c, WorkerCapability) else c
                for c in entity.capabilities
            ],
            last_heartbeat_at=entity.last_heartbeat_at,
            metadata_=entity.metadata,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    async def create(self, worker: Worker) -> None:
        model = self._to_model(worker)
        self.session.add(model)
        await self.session.flush()

    async def get(self, worker_id: UUID) -> Optional[Worker]:
        result = await self.session.execute(
            select(WorkerModel).where(WorkerModel.id == worker_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_status(self, status: str) -> List[Worker]:
        result = await self.session.execute(
            select(WorkerModel).where(WorkerModel.status == status)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def get_available_workers(
        self, capabilities: Optional[List[str]] = None
    ) -> List[Worker]:
        stmt = select(WorkerModel).where(
            WorkerModel.status.in_(
                [WorkerStatus.AVAILABLE.value, WorkerStatus.BUSY.value]
            )
        )
        if capabilities:
            # Filter by capabilities - workers that have ALL required capabilities
            for cap in capabilities:
                stmt = stmt.where(WorkerModel.capabilities.contains([cap]))

        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def update(self, worker: Worker) -> None:
        model = await self.session.get(WorkerModel, worker.id)
        if model:
            model.status = worker.status.value
            model.capabilities = [
                c.value if isinstance(c, WorkerCapability) else c
                for c in worker.capabilities
            ]
            model.last_heartbeat_at = worker.last_heartbeat_at
            model.metadata_ = worker.metadata
            model.updated_at = worker.updated_at
            await self.session.flush()


class SQLAlchemyWorkerHeartbeatRepository(WorkerHeartbeatRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: WorkerHeartbeatModel) -> WorkerHeartbeat:
        return WorkerHeartbeat(
            id=model.id,
            worker_id=model.worker_id,
            task_execution_id=model.task_execution_id,
            task_id=model.task_id,
            lease_expires_at=model.lease_expires_at,
            metadata=model.metadata_ or {},
            created_at=model.created_at,
        )

    def _to_model(self, entity: WorkerHeartbeat) -> WorkerHeartbeatModel:
        return WorkerHeartbeatModel(
            id=entity.id,
            worker_id=entity.worker_id,
            task_execution_id=entity.task_execution_id,
            task_id=entity.task_id,
            lease_expires_at=entity.lease_expires_at,
            metadata_=entity.metadata,
            created_at=entity.created_at,
        )

    async def create(self, heartbeat: WorkerHeartbeat) -> None:
        model = self._to_model(heartbeat)
        self.session.add(model)
        await self.session.flush()

    async def get(self, heartbeat_id: UUID) -> Optional[WorkerHeartbeat]:
        result = await self.session.execute(
            select(WorkerHeartbeatModel).where(WorkerHeartbeatModel.id == heartbeat_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_worker(self, worker_id: UUID) -> List[WorkerHeartbeat]:
        result = await self.session.execute(
            select(WorkerHeartbeatModel).where(
                WorkerHeartbeatModel.worker_id == worker_id
            )
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def get_by_task_execution(
        self, task_execution_id: UUID
    ) -> List[WorkerHeartbeat]:
        result = await self.session.execute(
            select(WorkerHeartbeatModel).where(
                WorkerHeartbeatModel.task_execution_id == task_execution_id
            )
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def update(self, heartbeat: WorkerHeartbeat) -> None:
        model = await self.session.get(WorkerHeartbeatModel, heartbeat.id)
        if model:
            model.lease_expires_at = heartbeat.lease_expires_at
            model.metadata_ = heartbeat.metadata
            await self.session.flush()


class SQLAlchemyTaskLeaseRepository(TaskLeaseRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: TaskLeaseModel) -> TaskLease:
        return TaskLease(
            id=model.id,
            worker_id=model.worker_id,
            task_id=model.task_id,
            task_execution_id=model.task_execution_id,
            claimed_at=model.claimed_at,
            lease_expires_at=model.lease_expires_at,
            last_heartbeat_at=model.last_heartbeat_at,
            renewed_count=model.renewed_count,
            metadata=model.metadata_ or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: TaskLease) -> TaskLeaseModel:
        return TaskLeaseModel(
            id=entity.id,
            worker_id=entity.worker_id,
            task_id=entity.task_id,
            task_execution_id=entity.task_execution_id,
            claimed_at=entity.claimed_at,
            lease_expires_at=entity.lease_expires_at,
            last_heartbeat_at=entity.last_heartbeat_at,
            renewed_count=entity.renewed_count,
            metadata_=entity.metadata,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    async def create(self, lease: TaskLease) -> None:
        model = self._to_model(lease)
        self.session.add(model)
        await self.session.flush()

    async def get(self, lease_id: UUID) -> Optional[TaskLease]:
        result = await self.session.execute(
            select(TaskLeaseModel).where(TaskLeaseModel.id == lease_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_worker(self, worker_id: UUID) -> List[TaskLease]:
        result = await self.session.execute(
            select(TaskLeaseModel).where(TaskLeaseModel.worker_id == worker_id)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def get_by_task_execution(self, task_execution_id: UUID) -> List[TaskLease]:
        result = await self.session.execute(
            select(TaskLeaseModel).where(
                TaskLeaseModel.task_execution_id == task_execution_id
            )
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def get_stale_leases(self, before: datetime) -> List[TaskLease]:
        result = await self.session.execute(
            select(TaskLeaseModel).where(TaskLeaseModel.lease_expires_at < before)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def update(self, lease: TaskLease) -> None:
        model = await self.session.get(TaskLeaseModel, lease.id)
        if model:
            model.lease_expires_at = lease.lease_expires_at
            model.last_heartbeat_at = lease.last_heartbeat_at
            model.renewed_count = lease.renewed_count
            model.metadata_ = lease.metadata
            model.updated_at = lease.updated_at
            await self.session.flush()
