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


class SQLAlchemyPlanRepository(PlanRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, plan: EngineeringPlan) -> None:
        model = PlanModel(
            id=plan.id,
            mission_id=plan.mission_id,
            planner_agent_id=plan.planner_agent_id,
            planner_version=plan.planner_version,
            provider=plan.provider,
            model=plan.model,
            status=plan.status.value,
            output_data=plan.output.model_dump(),
            created_at=plan.created_at,
        )
        self.session.add(model)
        await self.session.flush()

    async def get(self, plan_id: UUID) -> Optional[EngineeringPlan]:
        result = await self.session.execute(
            select(PlanModel).where(PlanModel.id == plan_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return EngineeringPlan(
            id=model.id,
            mission_id=model.mission_id,
            planner_agent_id=model.planner_agent_id,
            planner_version=model.planner_version,
            provider=model.provider,
            model=model.model,
            status=PlanStatus(model.status),
            output=PlannerOutput.model_validate(model.output_data),
            created_at=model.created_at,
        )

    async def get_by_mission(self, mission_id: UUID) -> List[EngineeringPlan]:
        result = await self.session.execute(
            select(PlanModel)
            .where(PlanModel.mission_id == mission_id)
            .order_by(PlanModel.created_at.desc())
        )
        models = result.scalars().all()
        return [
            EngineeringPlan(
                id=model.id,
                mission_id=model.mission_id,
                planner_agent_id=model.planner_agent_id,
                planner_version=model.planner_version,
                provider=model.provider,
                model=model.model,
                status=PlanStatus(model.status),
                output=PlannerOutput.model_validate(model.output_data),
                created_at=model.created_at,
            )
            for model in models
        ]

    async def update(self, plan: EngineeringPlan) -> None:
        model = await self.session.get(PlanModel, plan.id)
        if model:
            model.status = plan.status.value
            model.output_data = plan.output.model_dump()
            await self.session.flush()
