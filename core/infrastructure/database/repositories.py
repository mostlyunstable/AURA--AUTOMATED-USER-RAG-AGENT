# mypy: ignore-errors
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


class SQLAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session: AsyncSession = None

    async def __aenter__(self):
        self.session = self.session_factory()
        self.missions = SQLAlchemyMissionRepository(self.session)
        self.events = SQLAlchemyEventRepository(self.session)
        self.tasks = SQLAlchemyTaskRepository(self.session)
        self.task_dependencies = SQLAlchemyTaskDependencyRepository(self.session)
        self.task_executions = SQLAlchemyTaskExecutionRepository(self.session)
        self.approvals = SQLAlchemyApprovalRepository(self.session)
        self.plans = SQLAlchemyPlanRepository(self.session)
        self.execution_environments = SQLAlchemyExecutionEnvironmentRepository(
            self.session
        )
        self.command_executions = SQLAlchemyCommandExecutionRepository(self.session)
        self.artifacts = SQLAlchemyArtifactRepository(self.session)
        self.agents = SQLAlchemyAgentRepository(self.session)
        self.agent_runs = SQLAlchemyAgentRunRepository(self.session)
        self.tool_calls = SQLAlchemyToolCallRepository(self.session)
        self.verification_results = SQLAlchemyVerificationResultRepository(self.session)
        self.pull_requests = SQLAlchemyPullRequestRepository(self.session)
        self.workers = SQLAlchemyWorkerRepository(self.session)
        self.worker_heartbeats = SQLAlchemyWorkerHeartbeatRepository(self.session)
        self.task_leases = SQLAlchemyTaskLeaseRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()


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


class SQLAlchemyAgentRepository(AgentRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: AgentModel) -> Agent:
        return Agent(
            id=model.id,
            name=model.name,
            agent_type=AgentType(model.agent_type),
            version=model.version,
            capabilities=[AgentCapability(c) for c in model.capabilities],
            status=AgentStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Agent) -> AgentModel:
        return AgentModel(
            id=entity.id,
            name=entity.name,
            agent_type=entity.agent_type.value,
            version=entity.version,
            capabilities=[c.value for c in entity.capabilities],
            status=entity.status.value,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    async def create(self, agent: Agent) -> None:
        model = self._to_model(agent)
        self.session.add(model)
        await self.session.flush()

    async def get(self, agent_id: UUID) -> Optional[Agent]:
        result = await self.session.execute(
            select(AgentModel).where(AgentModel.id == agent_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_type(self, agent_type: str) -> List[Agent]:
        result = await self.session.execute(
            select(AgentModel).where(AgentModel.agent_type == agent_type)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]


class SQLAlchemyAgentRunRepository(AgentRunRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: AgentRunModel) -> AgentRun:
        return AgentRun(
            id=model.id,
            mission_id=model.mission_id,
            task_id=model.task_id,
            task_execution_id=model.task_execution_id,
            agent_id=model.agent_id,
            status=AgentRunStatus(model.status),
            iteration_count=model.iteration_count,
            tool_call_count=model.tool_call_count,
            max_iterations=model.max_iterations,
            max_tool_calls=model.max_tool_calls,
            max_runtime_seconds=model.max_runtime_seconds,
            max_failed_actions=model.max_failed_actions,
            started_at=model.started_at,
            completed_at=model.completed_at,
            failure_reason=model.failure_reason,
            final_result=model.final_result,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: AgentRun) -> AgentRunModel:
        return AgentRunModel(
            id=entity.id,
            mission_id=entity.mission_id,
            task_id=entity.task_id,
            task_execution_id=entity.task_execution_id,
            agent_id=entity.agent_id,
            status=entity.status.value,
            iteration_count=entity.iteration_count,
            tool_call_count=entity.tool_call_count,
            max_iterations=entity.max_iterations,
            max_tool_calls=entity.max_tool_calls,
            max_runtime_seconds=entity.max_runtime_seconds,
            max_failed_actions=entity.max_failed_actions,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            failure_reason=entity.failure_reason,
            final_result=entity.final_result,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    async def create(self, run: AgentRun) -> None:
        model = self._to_model(run)
        self.session.add(model)
        await self.session.flush()

    async def get(self, run_id: UUID) -> Optional[AgentRun]:
        result = await self.session.execute(
            select(AgentRunModel).where(AgentRunModel.id == run_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_task_execution(self, task_execution_id: UUID) -> List[AgentRun]:
        result = await self.session.execute(
            select(AgentRunModel).where(
                AgentRunModel.task_execution_id == task_execution_id
            )
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def update(self, run: AgentRun) -> None:
        model = await self.session.get(AgentRunModel, run.id)
        if model:
            model.status = run.status.value
            model.iteration_count = run.iteration_count
            model.tool_call_count = run.tool_call_count
            model.started_at = run.started_at
            model.completed_at = run.completed_at
            model.failure_reason = run.failure_reason
            model.final_result = run.final_result
            model.updated_at = run.updated_at
            await self.session.flush()


class SQLAlchemyToolCallRepository(ToolCallRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: ToolCallModel) -> ToolCall:
        return ToolCall(
            id=model.id,
            agent_run_id=model.agent_run_id,
            tool_name=model.tool_name,
            arguments=model.arguments,
            policy_decision=ToolCallStatus(model.policy_decision),
            policy_reason=model.policy_reason,
            status=ToolCallStatus(model.status),
            started_at=model.started_at,
            completed_at=model.completed_at,
            result_summary=model.result_summary,
            failure_reason=model.failure_reason,
            created_at=model.created_at,
        )

    def _to_model(self, entity: ToolCall) -> ToolCallModel:
        return ToolCallModel(
            id=entity.id,
            agent_run_id=entity.agent_run_id,
            tool_name=entity.tool_name,
            arguments=entity.arguments,
            policy_decision=entity.policy_decision.value,
            policy_reason=entity.policy_reason,
            status=entity.status.value,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            result_summary=entity.result_summary,
            failure_reason=entity.failure_reason,
            created_at=entity.created_at,
        )

    async def create(self, call: ToolCall) -> None:
        model = self._to_model(call)
        self.session.add(model)
        await self.session.flush()

    async def get(self, call_id: UUID) -> Optional[ToolCall]:
        result = await self.session.execute(
            select(ToolCallModel).where(ToolCallModel.id == call_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_agent_run(self, agent_run_id: UUID) -> List[ToolCall]:
        result = await self.session.execute(
            select(ToolCallModel).where(ToolCallModel.agent_run_id == agent_run_id)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def update(self, call: ToolCall) -> None:
        model = await self.session.get(ToolCallModel, call.id)
        if model:
            model.policy_decision = call.policy_decision.value
            model.policy_reason = call.policy_reason
            model.status = call.status.value
            model.started_at = call.started_at
            model.completed_at = call.completed_at
            model.result_summary = call.result_summary
            model.failure_reason = call.failure_reason
            # mypy: ignore-errors


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
    ToolCallRepository,
    UnitOfWork,
    VerificationResultRepository,
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
from core.domain.tasks.entities import Task, TaskDependency, TaskExecution
from core.domain.tasks.enums import TaskStatus, TaskType

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
    TaskDependencyModel,
    TaskExecutionModel,
    TaskModel,
    ToolCallModel,
    VerificationResultModel,
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


class SQLAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session: AsyncSession = None

    async def __aenter__(self):
        self.session = self.session_factory()
        self.missions = SQLAlchemyMissionRepository(self.session)
        self.events = SQLAlchemyEventRepository(self.session)
        self.tasks = SQLAlchemyTaskRepository(self.session)
        self.task_dependencies = SQLAlchemyTaskDependencyRepository(self.session)
        self.task_executions = SQLAlchemyTaskExecutionRepository(self.session)
        self.approvals = SQLAlchemyApprovalRepository(self.session)
        self.plans = SQLAlchemyPlanRepository(self.session)
        self.execution_environments = SQLAlchemyExecutionEnvironmentRepository(
            self.session
        )
        self.command_executions = SQLAlchemyCommandExecutionRepository(self.session)
        self.artifacts = SQLAlchemyArtifactRepository(self.session)
        self.agents = SQLAlchemyAgentRepository(self.session)
        self.agent_runs = SQLAlchemyAgentRunRepository(self.session)
        self.tool_calls = SQLAlchemyToolCallRepository(self.session)
        self.verification_results = SQLAlchemyVerificationResultRepository(self.session)
        self.pull_requests = SQLAlchemyPullRequestRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()


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


class SQLAlchemyAgentRepository(AgentRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: AgentModel) -> Agent:
        return Agent(
            id=model.id,
            name=model.name,
            agent_type=AgentType(model.agent_type),
            version=model.version,
            capabilities=[AgentCapability(c) for c in model.capabilities],
            status=AgentStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Agent) -> AgentModel:
        return AgentModel(
            id=entity.id,
            name=entity.name,
            agent_type=entity.agent_type.value,
            version=entity.version,
            capabilities=[c.value for c in entity.capabilities],
            status=entity.status.value,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    async def create(self, agent: Agent) -> None:
        model = self._to_model(agent)
        self.session.add(model)
        await self.session.flush()

    async def get(self, agent_id: UUID) -> Optional[Agent]:
        result = await self.session.execute(
            select(AgentModel).where(AgentModel.id == agent_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_type(self, agent_type: str) -> List[Agent]:
        result = await self.session.execute(
            select(AgentModel).where(AgentModel.agent_type == agent_type)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]


class SQLAlchemyAgentRunRepository(AgentRunRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: AgentRunModel) -> AgentRun:
        return AgentRun(
            id=model.id,
            mission_id=model.mission_id,
            task_id=model.task_id,
            task_execution_id=model.task_execution_id,
            agent_id=model.agent_id,
            status=AgentRunStatus(model.status),
            iteration_count=model.iteration_count,
            tool_call_count=model.tool_call_count,
            max_iterations=model.max_iterations,
            max_tool_calls=model.max_tool_calls,
            max_runtime_seconds=model.max_runtime_seconds,
            max_failed_actions=model.max_failed_actions,
            started_at=model.started_at,
            completed_at=model.completed_at,
            failure_reason=model.failure_reason,
            final_result=model.final_result,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: AgentRun) -> AgentRunModel:
        return AgentRunModel(
            id=entity.id,
            mission_id=entity.mission_id,
            task_id=entity.task_id,
            task_execution_id=entity.task_execution_id,
            agent_id=entity.agent_id,
            status=entity.status.value,
            iteration_count=entity.iteration_count,
            tool_call_count=entity.tool_call_count,
            max_iterations=entity.max_iterations,
            max_tool_calls=entity.max_tool_calls,
            max_runtime_seconds=entity.max_runtime_seconds,
            max_failed_actions=entity.max_failed_actions,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            failure_reason=entity.failure_reason,
            final_result=entity.final_result,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    async def create(self, run: AgentRun) -> None:
        model = self._to_model(run)
        self.session.add(model)
        await self.session.flush()

    async def get(self, run_id: UUID) -> Optional[AgentRun]:
        result = await self.session.execute(
            select(AgentRunModel).where(AgentRunModel.id == run_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_task_execution(self, task_execution_id: UUID) -> List[AgentRun]:
        result = await self.session.execute(
            select(AgentRunModel).where(
                AgentRunModel.task_execution_id == task_execution_id
            )
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def update(self, run: AgentRun) -> None:
        model = await self.session.get(AgentRunModel, run.id)
        if model:
            model.status = run.status.value
            model.iteration_count = run.iteration_count
            model.tool_call_count = run.tool_call_count
            model.started_at = run.started_at
            model.completed_at = run.completed_at
            model.failure_reason = run.failure_reason
            model.final_result = run.final_result
            model.updated_at = run.updated_at
            await self.session.flush()


class SQLAlchemyToolCallRepository(ToolCallRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: ToolCallModel) -> ToolCall:
        return ToolCall(
            id=model.id,
            agent_run_id=model.agent_run_id,
            tool_name=model.tool_name,
            arguments=model.arguments,
            policy_decision=ToolCallStatus(model.policy_decision),
            policy_reason=model.policy_reason,
            status=ToolCallStatus(model.status),
            started_at=model.started_at,
            completed_at=model.completed_at,
            result_summary=model.result_summary,
            failure_reason=model.failure_reason,
            created_at=model.created_at,
        )

    def _to_model(self, entity: ToolCall) -> ToolCallModel:
        return ToolCallModel(
            id=entity.id,
            agent_run_id=entity.agent_run_id,
            tool_name=entity.tool_name,
            arguments=entity.arguments,
            policy_decision=entity.policy_decision.value,
            policy_reason=entity.policy_reason,
            status=entity.status.value,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            result_summary=entity.result_summary,
            failure_reason=entity.failure_reason,
            created_at=entity.created_at,
        )

    async def create(self, call: ToolCall) -> None:
        model = self._to_model(call)
        self.session.add(model)
        await self.session.flush()

    async def get(self, call_id: UUID) -> Optional[ToolCall]:
        result = await self.session.execute(
            select(ToolCallModel).where(ToolCallModel.id == call_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_agent_run(self, agent_run_id: UUID) -> List[ToolCall]:
        result = await self.session.execute(
            select(ToolCallModel).where(ToolCallModel.agent_run_id == agent_run_id)
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def update(self, call: ToolCall) -> None:
        model = await self.session.get(ToolCallModel, call.id)
        if model:
            model.policy_decision = call.policy_decision.value
            model.policy_reason = call.policy_reason
            model.status = call.status.value
            model.started_at = call.started_at
            model.completed_at = call.completed_at
            model.result_summary = call.result_summary
            model.failure_reason = call.failure_reason
            await self.session.flush()


class SQLAlchemyVerificationResultRepository(VerificationResultRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_domain(self, model: VerificationResultModel) -> VerificationResult:
        from core.domain.agents.verification import (
            VerificationCheck,
            VerificationCheckResult,
            VerificationCheckType,
            VerificationStatus,
        )

        checks = [
            VerificationCheck(
                check_type=VerificationCheckType(c["check_type"]),
                result=VerificationCheckResult(c["result"]),
                message=c["message"],
                details=c.get("details", {}),
                duration_ms=c.get("duration_ms", 0.0),
            )
            for c in model.checks
        ]
        failed_checks = [
            VerificationCheck(
                check_type=VerificationCheckType(c["check_type"]),
                result=VerificationCheckResult(c["result"]),
                message=c["message"],
                details=c.get("details", {}),
                duration_ms=c.get("duration_ms", 0.0),
            )
            for c in model.failed_checks
        ]
        return VerificationResult(
            id=model.id,
            agent_run_id=model.agent_run_id,
            task_execution_id=model.task_execution_id,
            status=VerificationStatus(model.status),
            success=model.success,
            checks=checks,
            failed_checks=failed_checks,
            warnings=model.warnings,
            changed_files=model.changed_files,
            test_results=model.test_results,
            diff_summary=model.diff_summary,
            failure_reason=model.failure_reason,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
        )

    def _to_model(self, entity: VerificationResult) -> VerificationResultModel:
        return VerificationResultModel(
            id=entity.id,
            agent_run_id=entity.agent_run_id,
            task_execution_id=entity.task_execution_id,
            status=entity.status.value,
            success=entity.success,
            checks=[
                {
                    "check_type": c.check_type.value,
                    "result": c.result.value,
                    "message": c.message,
                    "details": c.details,
                    "duration_ms": c.duration_ms,
                }
                for c in entity.checks
            ],
            failed_checks=[
                {
                    "check_type": c.check_type.value,
                    "result": c.result.value,
                    "message": c.message,
                    "details": c.details,
                    "duration_ms": c.duration_ms,
                }
                for c in entity.failed_checks
            ],
            warnings=entity.warnings,
            changed_files=entity.changed_files,
            test_results=entity.test_results,
            diff_summary=entity.diff_summary,
            failure_reason=entity.failure_reason,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            created_at=entity.created_at,
        )

    async def create(self, verification: VerificationResult) -> None:
        model = self._to_model(verification)
        self.session.add(model)
        await self.session.flush()

    async def get(self, verification_id: UUID) -> Optional[VerificationResult]:
        result = await self.session.execute(
            select(VerificationResultModel).where(
                VerificationResultModel.id == verification_id
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_agent_run(self, agent_run_id: UUID) -> List[VerificationResult]:
        result = await self.session.execute(
            select(VerificationResultModel).where(
                VerificationResultModel.agent_run_id == agent_run_id
            )
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def get_by_task_execution(
        self, task_execution_id: UUID
    ) -> List[VerificationResult]:
        result = await self.session.execute(
            select(VerificationResultModel).where(
                VerificationResultModel.task_execution_id == task_execution_id
            )
        )
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def update(self, verification: VerificationResult) -> None:
        model = await self.session.get(VerificationResultModel, verification.id)
        if model:
            model.status = verification.status.value
            model.success = verification.success
            model.checks = [
                {
                    "check_type": c.check_type.value,
                    "result": c.result.value,
                    "message": c.message,
                    "details": c.details,
                    "duration_ms": c.duration_ms,
                }
                for c in verification.checks
            ]
            model.failed_checks = [
                {
                    "check_type": c.check_type.value,
                    "result": c.result.value,
                    "message": c.message,
                    "details": c.details,
                    "duration_ms": c.duration_ms,
                }
                for c in verification.failed_checks
            ]
            model.warnings = verification.warnings
            model.changed_files = verification.changed_files
            model.test_results = verification.test_results
            model.diff_summary = verification.diff_summary
            model.failure_reason = verification.failure_reason
            model.completed_at = verification.completed_at
            await self.session.flush()


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
        self, capabilities: List[str] = None
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
