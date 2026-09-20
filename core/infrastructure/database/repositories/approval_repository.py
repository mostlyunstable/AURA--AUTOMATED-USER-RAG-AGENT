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


class SQLAlchemyApprovalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, approval: Approval) -> None:
        model = ApprovalModel(
            id=approval.id,
            mission_id=approval.mission_id,
            approval_type=approval.approval_type.value,
            status=approval.status.value,
            requested_at=approval.requested_at,
            resolved_at=approval.resolved_at,
            resolved_by=approval.resolved_by,
            metadata_=approval.metadata,
        )
        self.session.add(model)
        await self.session.flush()

    async def get(self, approval_id: UUID) -> Optional[Approval]:
        result = await self.session.execute(
            select(ApprovalModel).where(ApprovalModel.id == approval_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Approval(
            id=model.id,
            mission_id=model.mission_id,
            approval_type=ApprovalType(model.approval_type),
            status=ApprovalStatus(model.status),
            requested_at=model.requested_at,
            resolved_at=model.resolved_at,
            resolved_by=model.resolved_by,
            metadata=model.metadata_,
        )

    async def get_by_mission(self, mission_id: UUID) -> List[Approval]:
        result = await self.session.execute(
            select(ApprovalModel).where(ApprovalModel.mission_id == mission_id)
        )
        models = result.scalars().all()
        return [
            Approval(
                id=model.id,
                mission_id=model.mission_id,
                approval_type=ApprovalType(model.approval_type),
                status=ApprovalStatus(model.status),
                requested_at=model.requested_at,
                resolved_at=model.resolved_at,
                resolved_by=model.resolved_by,
                metadata=model.metadata_,
            )
            for model in models
        ]

    async def update(self, approval: Approval) -> None:
        result = await self.session.execute(
            select(ApprovalModel).where(ApprovalModel.id == approval.id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.status = approval.status.value
            model.resolved_at = approval.resolved_at
            model.resolved_by = approval.resolved_by
            model.metadata_ = approval.metadata
            await self.session.flush()
