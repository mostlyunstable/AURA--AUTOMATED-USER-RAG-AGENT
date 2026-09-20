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


class SQLAlchemyExecutionEnvironmentRepository(ExecutionEnvironmentRepository):
    def __init__(self, session):
        self.session = session

    async def create(self, env: ExecutionEnvironment) -> None:
        model = ExecutionEnvironmentModel(
            id=env.id,
            mission_id=env.mission_id,
            task_id=env.task_id,
            execution_id=env.execution_id,
            status=env.status.value,
            worktree_path=env.worktree_path,
            base_commit_sha=env.base_commit_sha,
            created_at=env.created_at,
            started_at=env.started_at,
            completed_at=env.completed_at,
            failure_reason=env.failure_reason,
            metadata_=env.metadata,
        )
        self.session.add(model)
        await self.session.flush()

    async def get(self, env_id: UUID) -> Optional[ExecutionEnvironment]:
        result = await self.session.execute(
            select(ExecutionEnvironmentModel).where(
                ExecutionEnvironmentModel.id == env_id
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return ExecutionEnvironment(
            id=model.id,
            mission_id=model.mission_id,
            task_id=model.task_id,
            execution_id=model.execution_id,
            status=EnvironmentStatus(model.status),
            worktree_path=model.worktree_path,
            base_commit_sha=model.base_commit_sha,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            failure_reason=model.failure_reason,
            metadata=model.metadata_ or {},
        )

    async def update(self, env: ExecutionEnvironment) -> None:
        model = await self.session.get(ExecutionEnvironmentModel, env.id)
        if model:
            model.status = env.status.value
            model.worktree_path = env.worktree_path
            model.base_commit_sha = env.base_commit_sha
            model.started_at = env.started_at
            model.completed_at = env.completed_at
            model.failure_reason = env.failure_reason
            model.metadata_ = env.metadata
            await self.session.flush()

    async def get_by_task_execution(
        self, task_execution_id: UUID
    ) -> List[ExecutionEnvironment]:
        result = await self.session.execute(
            select(ExecutionEnvironmentModel).where(
                ExecutionEnvironmentModel.execution_id == task_execution_id
            )
        )
        models = result.scalars().all()
        return [
            ExecutionEnvironment(
                id=model.id,
                mission_id=model.mission_id,
                task_id=model.task_id,
                execution_id=model.execution_id,
                status=EnvironmentStatus(model.status),
                worktree_path=model.worktree_path,
                base_commit_sha=model.base_commit_sha,
                created_at=model.created_at,
                started_at=model.started_at,
                completed_at=model.completed_at,
                failure_reason=model.failure_reason,
                metadata=model.metadata_ or {},
            )
            for model in models
        ]


class SQLAlchemyCommandExecutionRepository(CommandExecutionRepository):
    def __init__(self, session):
        self.session = session

    async def create(self, result: CommandResult) -> None:
        model = CommandExecutionModel(
            id=result.id,
            environment_id=result.environment_id,
            status=result.status.value,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
            timed_out=result.timed_out,
            output_truncated=result.output_truncated,
            failure_reason=result.failure_reason,
        )
        self.session.add(model)
        await self.session.flush()

    async def get_by_environment(self, environment_id: UUID) -> List[CommandResult]:
        result = await self.session.execute(
            select(CommandExecutionModel).where(
                CommandExecutionModel.environment_id == environment_id
            )
        )
        models = result.scalars().all()
        return [
            CommandResult(
                id=model.id,
                environment_id=model.environment_id,
                status=CommandStatus(model.status),
                exit_code=model.exit_code,
                stdout=model.stdout,
                stderr=model.stderr,
                duration_ms=model.duration_ms,
                timed_out=model.timed_out,
                output_truncated=model.output_truncated,
                failure_reason=model.failure_reason,
            )
            for model in models
        ]


class SQLAlchemyArtifactRepository(ArtifactRepository):
    def __init__(self, session):
        self.session = session

    async def create(self, artifact: Artifact) -> None:
        model = ArtifactModel(
            id=artifact.id,
            environment_id=artifact.environment_id,
            path=artifact.path,
            type=artifact.type.value,
            size=artifact.size,
            sha256=artifact.sha256,
            created_at=artifact.created_at,
            metadata_=artifact.metadata,
        )
        self.session.add(model)
        await self.session.flush()

    async def get_by_environment(self, environment_id: UUID) -> List[Artifact]:
        result = await self.session.execute(
            select(ArtifactModel).where(ArtifactModel.environment_id == environment_id)
        )
        models = result.scalars().all()
        return [
            Artifact(
                id=model.id,
                environment_id=model.environment_id,
                path=model.path,
                type=ArtifactType(model.type),
                size=model.size,
                sha256=model.sha256,
                created_at=model.created_at,
                metadata=model.metadata_ or {},
            )
            for model in models
        ]


