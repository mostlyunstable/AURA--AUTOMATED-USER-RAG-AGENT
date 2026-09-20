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


class SQLAlchemyTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, task: Task) -> None:
        model = TaskModel(
            id=task.id,
            mission_id=task.mission_id,
            title=task.title,
            description=task.description,
            status=task.status.value,
            task_type=task.task_type.value,
            priority=task.priority,
            assigned_agent_id=task.assigned_agent_id,
            attempt_count=task.attempt_count,
            max_attempts=task.max_attempts,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        self.session.add(model)
        await self.session.flush()

    async def get(self, task_id: UUID) -> Optional[Task]:
        result = await self.session.execute(
            select(TaskModel).where(TaskModel.id == task_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Task(
            id=model.id,
            mission_id=model.mission_id,
            title=model.title,
            description=model.description,
            status=TaskStatus(model.status),
            task_type=TaskType(model.task_type),
            priority=model.priority,
            assigned_agent_id=model.assigned_agent_id,
            attempt_count=model.attempt_count,
            max_attempts=model.max_attempts,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def update(self, task: Task) -> None:
        result = await self.session.execute(
            select(TaskModel).where(TaskModel.id == task.id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.status = task.status.value
            model.priority = task.priority
            model.assigned_agent_id = task.assigned_agent_id
            model.attempt_count = task.attempt_count
            model.updated_at = task.updated_at
            await self.session.flush()

    async def get_by_mission(self, mission_id: UUID) -> List[Task]:
        result = await self.session.execute(
            select(TaskModel).where(TaskModel.mission_id == mission_id)
        )
        models = result.scalars().all()
        return [
            Task(
                id=model.id,
                mission_id=model.mission_id,
                title=model.title,
                description=model.description,
                status=TaskStatus(model.status),
                task_type=TaskType(model.task_type),
                priority=model.priority,
                assigned_agent_id=model.assigned_agent_id,
                attempt_count=model.attempt_count,
                max_attempts=model.max_attempts,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )
            for model in models
        ]


class SQLAlchemyTaskDependencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, dependency: TaskDependency) -> None:
        model = TaskDependencyModel(
            task_id=dependency.task_id, depends_on_task_id=dependency.depends_on_task_id
        )
        self.session.add(model)
        await self.session.flush()

    async def get_dependencies_for_task(self, task_id: UUID) -> List[TaskDependency]:
        result = await self.session.execute(
            select(TaskDependencyModel).where(TaskDependencyModel.task_id == task_id)
        )
        models = result.scalars().all()
        return [
            TaskDependency(
                task_id=model.task_id, depends_on_task_id=model.depends_on_task_id
            )
            for model in models
        ]

    async def get_dependencies_for_mission(
        self, mission_id: UUID
    ) -> List[TaskDependency]:
        stmt = (
            select(TaskDependencyModel)
            .join(TaskModel, TaskModel.id == TaskDependencyModel.task_id)
            .where(TaskModel.mission_id == mission_id)
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [
            TaskDependency(
                task_id=model.task_id, depends_on_task_id=model.depends_on_task_id
            )
            for model in models
        ]


class SQLAlchemyTaskExecutionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, execution: TaskExecution) -> None:
        model = TaskExecutionModel(
            id=execution.id,
            task_id=execution.task_id,
            agent_id=execution.agent_id,
            attempt_number=execution.attempt_number,
            status=execution.status.value,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            error=execution.error,
            result_metadata_=execution.result_metadata,
        )
        self.session.add(model)
        await self.session.flush()

    async def get_by_task(self, task_id: UUID) -> List[TaskExecution]:
        result = await self.session.execute(
            select(TaskExecutionModel).where(TaskExecutionModel.task_id == task_id)
        )
        models = result.scalars().all()
        return [
            TaskExecution(
                id=model.id,
                task_id=model.task_id,
                agent_id=model.agent_id,
                attempt_number=model.attempt_number,
                status=TaskStatus(model.status),
                started_at=model.started_at,
                completed_at=model.completed_at,
                error=model.error,
                result_metadata=model.result_metadata_,
            )
            for model in models
        ]
