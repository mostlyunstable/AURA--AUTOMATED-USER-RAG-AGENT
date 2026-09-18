from core.domain.tasks.entities import Task, TaskDependency, TaskExecution
from core.domain.tasks.enums import TaskStatus, TaskType
from core.domain.approvals.entities import Approval
from core.domain.approvals.enums import ApprovalStatus, ApprovalType
from core.domain.plans.entities import EngineeringPlan, PlannerOutput
from core.domain.plans.enums import PlanStatus
from core.application.interfaces import PlanRepository, ExecutionEnvironmentRepository, CommandExecutionRepository, ArtifactRepository
from core.domain.execution.entities import ExecutionEnvironment, CommandResult, Artifact
from core.domain.execution.enums import EnvironmentStatus, CommandStatus, ArtifactType
from .models import ExecutionEnvironmentModel, CommandExecutionModel, ArtifactModel
from .models import PlanModel

from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.missions.entities import Mission
from core.domain.missions.enums import MissionStatus
from core.domain.events.entities import Event
from core.application.interfaces import MissionRepository, EventRepository, UnitOfWork
from .models import MissionModel, EventModel, TaskModel, TaskDependencyModel, TaskExecutionModel, ApprovalModel

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
            updated_at=model.updated_at
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
            updated_at=entity.updated_at
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
            metadata_=event.metadata
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
        self.execution_environments = SQLAlchemyExecutionEnvironmentRepository(self.session)
        self.command_executions = SQLAlchemyCommandExecutionRepository(self.session)
        self.artifacts = SQLAlchemyArtifactRepository(self.session)
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
            updated_at=task.updated_at
        )
        self.session.add(model)
        await self.session.flush()

    async def get(self, task_id: UUID) -> Optional[Task]:
        result = await self.session.execute(select(TaskModel).where(TaskModel.id == task_id))
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
            updated_at=model.updated_at
        )
        
    async def update(self, task: Task) -> None:
        result = await self.session.execute(select(TaskModel).where(TaskModel.id == task.id))
        model = result.scalar_one_or_none()
        if model:
            model.status = task.status.value
            model.priority = task.priority
            model.assigned_agent_id = task.assigned_agent_id
            model.attempt_count = task.attempt_count
            model.updated_at = task.updated_at
            await self.session.flush()

    async def get_by_mission(self, mission_id: UUID) -> List[Task]:
        result = await self.session.execute(select(TaskModel).where(TaskModel.mission_id == mission_id))
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
                updated_at=model.updated_at
            ) for model in models
        ]

class SQLAlchemyTaskDependencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, dependency: TaskDependency) -> None:
        model = TaskDependencyModel(
            task_id=dependency.task_id,
            depends_on_task_id=dependency.depends_on_task_id
        )
        self.session.add(model)
        await self.session.flush()

    async def get_dependencies_for_task(self, task_id: UUID) -> List[TaskDependency]:
        result = await self.session.execute(select(TaskDependencyModel).where(TaskDependencyModel.task_id == task_id))
        models = result.scalars().all()
        return [TaskDependency(task_id=model.task_id, depends_on_task_id=model.depends_on_task_id) for model in models]

    async def get_dependencies_for_mission(self, mission_id: UUID) -> List[TaskDependency]:
        stmt = select(TaskDependencyModel).join(TaskModel, TaskModel.id == TaskDependencyModel.task_id).where(TaskModel.mission_id == mission_id)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [TaskDependency(task_id=model.task_id, depends_on_task_id=model.depends_on_task_id) for model in models]

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
            result_metadata_=execution.result_metadata
        )
        self.session.add(model)
        await self.session.flush()

    async def get_by_task(self, task_id: UUID) -> List[TaskExecution]:
        result = await self.session.execute(select(TaskExecutionModel).where(TaskExecutionModel.task_id == task_id))
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
                result_metadata=model.result_metadata_
            ) for model in models
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
            metadata_=approval.metadata
        )
        self.session.add(model)
        await self.session.flush()

    async def get(self, approval_id: UUID) -> Optional[Approval]:
        result = await self.session.execute(select(ApprovalModel).where(ApprovalModel.id == approval_id))
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
            metadata=model.metadata_
        )
        
    async def get_by_mission(self, mission_id: UUID) -> List[Approval]:
        result = await self.session.execute(select(ApprovalModel).where(ApprovalModel.mission_id == mission_id))
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
                metadata=model.metadata_
            ) for model in models
        ]

    async def update(self, approval: Approval) -> None:
        result = await self.session.execute(select(ApprovalModel).where(ApprovalModel.id == approval.id))
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
            created_at=plan.created_at
        )
        self.session.add(model)
        await self.session.flush()

    async def get(self, plan_id: UUID) -> Optional[EngineeringPlan]:
        result = await self.session.execute(select(PlanModel).where(PlanModel.id == plan_id))
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
            created_at=model.created_at
        )

    async def get_by_mission(self, mission_id: UUID) -> List[EngineeringPlan]:
        result = await self.session.execute(select(PlanModel).where(PlanModel.mission_id == mission_id).order_by(PlanModel.created_at.desc()))
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
                created_at=model.created_at
            ) for model in models
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
            id=env.id, mission_id=env.mission_id, task_id=env.task_id, execution_id=env.execution_id,
            status=env.status.value, worktree_path=env.worktree_path, base_commit_sha=env.base_commit_sha,
            created_at=env.created_at, started_at=env.started_at, completed_at=env.completed_at,
            failure_reason=env.failure_reason, metadata_=env.metadata
        )
        self.session.add(model)
        await self.session.flush()
    async def get(self, env_id: UUID) -> Optional[ExecutionEnvironment]:
        result = await self.session.execute(select(ExecutionEnvironmentModel).where(ExecutionEnvironmentModel.id == env_id))
        model = result.scalar_one_or_none()
        if not model: return None
        return ExecutionEnvironment(
            id=model.id, mission_id=model.mission_id, task_id=model.task_id, execution_id=model.execution_id,
            status=EnvironmentStatus(model.status), worktree_path=model.worktree_path, base_commit_sha=model.base_commit_sha,
            created_at=model.created_at, started_at=model.started_at, completed_at=model.completed_at,
            failure_reason=model.failure_reason, metadata=model.metadata_ or {}
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
            id=result.id, environment_id=result.environment_id, status=result.status.value,
            exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr,
            duration_ms=result.duration_ms, timed_out=result.timed_out, output_truncated=result.output_truncated,
            failure_reason=result.failure_reason
        )
        self.session.add(model)
        await self.session.flush()

class SQLAlchemyArtifactRepository(ArtifactRepository):
    def __init__(self, session):
        self.session = session
    async def create(self, artifact: Artifact) -> None:
        model = ArtifactModel(
            id=artifact.id, environment_id=artifact.environment_id, path=artifact.path,
            type=artifact.type.value, size=artifact.size, sha256=artifact.sha256,
            created_at=artifact.created_at, metadata_=artifact.metadata
        )
        self.session.add(model)
        await self.session.flush()
