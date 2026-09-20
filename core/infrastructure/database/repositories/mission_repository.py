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

from .models import (
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


class SQLAlchemyMissionRepository(MissionRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: MissionModel) -> Mission:
        return Mission(
            id=model.id,
            title=model.title,
            description=model.description,
            repository_id=model.repository_id,
            source=model.source,
            status=MissionStatus(model.status),
            risk_level=model.risk_level,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Mission) -> MissionModel:
        return MissionModel(
            id=entity.id,
            title=entity.title,
            description=entity.description,
            repository_id=entity.repository_id,
            source=entity.source,
            status=entity.status.value,
            risk_level=entity.risk_level,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    async def create(self, mission: Mission) -> Mission:
        model = self._to_model(mission)
        self.session.add(model)
        # Flush to catch DB constraints within UOW but commit later
        await self.session.flush()
        return mission

    async def get(self, mission_id: UUID) -> Optional[Mission]:
        stmt = select(MissionModel).where(MissionModel.id == mission_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_domain(model)
        return None

    async def update(self, mission: Mission) -> Mission:
        model = await self.session.get(MissionModel, mission.id)
        if model:
            model.status = mission.status.value
            model.updated_at = mission.updated_at
            await self.session.flush()
        return mission

    async def list_all(self) -> List[Mission]:
        stmt = select(MissionModel)
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]


class SQLAlchemyEventRepository(EventRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append(self, event: Event) -> Event:
        model = EventModel(
            id=event.id,
            event_type=event.event_type,
            mission_id=event.mission_id,
            task_id=event.task_id,
            agent_id=event.agent_id,
            timestamp=event.timestamp,
            metadata_=event.metadata,
        )
        self.session.add(model)
        await self.session.flush()
        return event


