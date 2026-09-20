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


class SQLAlchemyPullRequestRepository(PullRequestRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: PullRequestModel) -> PullRequest:
        from core.domain.pull_requests.enums import (
            PullRequestProvider,
            PullRequestStatus,
        )

        return PullRequest(
            id=model.id,
            mission_id=model.mission_id,
            task_execution_id=model.task_execution_id,
            agent_run_id=model.agent_run_id,
            provider=PullRequestProvider(model.provider),
            provider_pr_id=model.provider_pr_id,
            provider_url=model.provider_url,
            source_branch=model.source_branch,
            target_branch=model.target_branch,
            title=model.title,
            description=model.description,
            status=PullRequestStatus(model.status),
            source_commit_sha=model.source_commit_sha,
            merge_commit_sha=model.merge_commit_sha,
            merged_at=model.merged_at,
            merged_by=model.merged_by,
            approval_ids=model.approval_ids or [],
            created_at=model.created_at,
            updated_at=model.updated_at,
            metadata=model.metadata_ or {},
        )

    def _to_model(self, entity: PullRequest) -> PullRequestModel:
        return PullRequestModel(
            id=entity.id,
            mission_id=entity.mission_id,
            task_execution_id=entity.task_execution_id,
            agent_run_id=entity.agent_run_id,
            provider=entity.provider.value,
            provider_pr_id=entity.provider_pr_id,
            provider_url=entity.provider_url,
            source_branch=entity.source_branch,
            target_branch=entity.target_branch,
            title=entity.title,
            description=entity.description,
            status=entity.status.value,
            source_commit_sha=entity.source_commit_sha,
            merge_commit_sha=entity.merge_commit_sha,
            merged_at=entity.merged_at,
            merged_by=entity.merged_by,
            approval_ids=entity.approval_ids,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            metadata_=entity.metadata,
        )

    async def create(self, pr: PullRequest) -> None:
        model = self._to_model(pr)
        self.session.add(model)
        await self.session.flush()

    async def get(self, pr_id: UUID) -> Optional[PullRequest]:
        result = await self.session.execute(
            select(PullRequestModel).where(PullRequestModel.id == pr_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_mission(self, mission_id: UUID) -> List[PullRequest]:
        result = await self.session.execute(
            select(PullRequestModel).where(PullRequestModel.mission_id == mission_id)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def get_by_task_execution(self, task_execution_id: UUID) -> List[PullRequest]:
        result = await self.session.execute(
            select(PullRequestModel).where(
                PullRequestModel.task_execution_id == task_execution_id
            )
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def update(self, pr: PullRequest) -> None:
        model = await self.session.get(PullRequestModel, pr.id)
        if model:
            model.provider = pr.provider.value
            model.provider_pr_id = pr.provider_pr_id
            model.provider_url = pr.provider_url
            model.source_branch = pr.source_branch
            model.target_branch = pr.target_branch
            model.title = pr.title
            model.description = pr.description
            model.status = pr.status.value
            model.source_commit_sha = pr.source_commit_sha
            model.merge_commit_sha = pr.merge_commit_sha
            model.merged_at = pr.merged_at
            model.merged_by = pr.merged_by
            model.approval_ids = pr.approval_ids
            model.updated_at = pr.updated_at
            model.metadata_ = pr.metadata
            await self.session.flush()


