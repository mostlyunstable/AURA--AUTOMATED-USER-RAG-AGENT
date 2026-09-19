from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.domain.approvals.entities import Approval
from core.domain.events.entities import Event
from core.domain.missions.entities import Mission
from core.domain.tasks.entities import Task, TaskDependency, TaskExecution


class MissionRepository(ABC):
    @abstractmethod
    async def create(self, mission: Mission) -> None:
        pass

    @abstractmethod
    async def get(self, mission_id: UUID) -> Optional[Mission]:
        pass

    @abstractmethod
    async def list_all(self) -> List[Mission]:
        pass

    @abstractmethod
    async def update(self, mission: Mission) -> Mission:
        pass


class EventRepository(ABC):
    @abstractmethod
    async def append(self, event: Event) -> None:
        pass


class TaskRepository(ABC):
    @abstractmethod
    async def create(self, task: Task) -> None:
        pass

    @abstractmethod
    async def get(self, task_id: UUID) -> Optional[Task]:
        pass

    @abstractmethod
    async def update(self, task: Task) -> None:
        pass

    @abstractmethod
    async def get_by_mission(self, mission_id: UUID) -> List[Task]:
        pass


class TaskDependencyRepository(ABC):
    @abstractmethod
    async def add(self, dependency: TaskDependency) -> None:
        pass

    @abstractmethod
    async def get_dependencies_for_task(self, task_id: UUID) -> List[TaskDependency]:
        pass

    @abstractmethod
    async def get_dependencies_for_mission(
        self, mission_id: UUID
    ) -> List[TaskDependency]:
        pass


class TaskExecutionRepository(ABC):
    @abstractmethod
    async def add(self, execution: TaskExecution) -> None:
        pass

    @abstractmethod
    async def get_by_task(self, task_id: UUID) -> List[TaskExecution]:
        pass


class ApprovalRepository(ABC):
    @abstractmethod
    async def create(self, approval: Approval) -> None:
        pass

    @abstractmethod
    async def get(self, approval_id: UUID) -> Optional[Approval]:
        pass

    @abstractmethod
    async def get_by_mission(self, mission_id: UUID) -> List[Approval]:
        pass

    @abstractmethod
    async def update(self, approval: Approval) -> None:
        pass


class UnitOfWork(ABC):
    missions: MissionRepository
    events: EventRepository
    tasks: TaskRepository
    task_dependencies: TaskDependencyRepository
    task_executions: TaskExecutionRepository
    approvals: ApprovalRepository
    plans: PlanRepository
    execution_environments: ExecutionEnvironmentRepository
    command_executions: CommandExecutionRepository
    artifacts: ArtifactRepository

    @abstractmethod
    async def __aenter__(self):
        pass

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    @abstractmethod
    async def commit(self):
        pass

    @abstractmethod
    async def rollback(self):
        pass


class AgentRuntime(ABC):
    @abstractmethod
    async def execute(self, task: Task, context: Any) -> Any:
        pass


from core.domain.plans.entities import EngineeringPlan


class PlanRepository(ABC):
    @abstractmethod
    async def create(self, plan: EngineeringPlan) -> None:
        pass

    @abstractmethod
    async def get(self, plan_id: UUID) -> Optional[EngineeringPlan]:
        pass

    @abstractmethod
    async def get_by_mission(self, mission_id: UUID) -> List[EngineeringPlan]:
        pass

    @abstractmethod
    async def update(self, plan: EngineeringPlan) -> None:
        pass


from core.domain.execution.entities import Artifact, CommandResult, ExecutionEnvironment


class ExecutionEnvironmentRepository(ABC):
    @abstractmethod
    async def create(self, env: ExecutionEnvironment) -> None:
        pass

    @abstractmethod
    async def get(self, env_id: UUID) -> Optional[ExecutionEnvironment]:
        pass

    @abstractmethod
    async def update(self, env: ExecutionEnvironment) -> None:
        pass


class CommandExecutionRepository(ABC):
    @abstractmethod
    async def create(self, result: CommandResult) -> None:
        pass


class ArtifactRepository(ABC):
    @abstractmethod
    async def create(self, artifact: Artifact) -> None:
        pass
