from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.domain.agents.entities import Agent, AgentRun, ToolCall
from core.domain.agents.verification import VerificationResult
from core.domain.approvals.entities import Approval
from core.domain.events.entities import Event
from core.domain.missions.entities import Mission
from core.domain.plans.entities import EngineeringPlan
from core.domain.pull_requests.entities import PullRequest
from core.domain.tasks.entities import Task, TaskDependency, TaskExecution
from core.domain.tasks.enums import TaskStatus
from core.domain.workers.entities import TaskLease, Worker, WorkerHeartbeat


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

    @abstractmethod
    async def claim_task(self, task_id: UUID, worker_id: UUID) -> Optional[Task]:
        pass

    @abstractmethod
    async def try_transition_status(
        self, task_id: UUID, from_status: TaskStatus, to_status: TaskStatus
    ) -> Optional[Task]:
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
    async def get(self, execution_id: UUID) -> Optional[TaskExecution]:
        pass

    @abstractmethod
    async def get_by_task(self, task_id: UUID) -> List[TaskExecution]:
        pass

    @abstractmethod
    async def update(self, execution: TaskExecution) -> None:
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


class ExecutionEnvironmentRepository(ABC):
    @abstractmethod
    async def create(self, env: "ExecutionEnvironment") -> None:
        pass

    @abstractmethod
    async def get(self, env_id: UUID) -> Optional["ExecutionEnvironment"]:
        pass

    @abstractmethod
    async def update(self, env: "ExecutionEnvironment") -> None:
        pass

    @abstractmethod
    async def get_by_task_execution(
        self, task_execution_id: UUID
    ) -> List["ExecutionEnvironment"]:
        pass


class CommandExecutionRepository(ABC):
    @abstractmethod
    async def create(self, result: "CommandResult") -> None:
        pass

    @abstractmethod
    async def get_by_environment(self, environment_id: UUID) -> List["CommandResult"]:
        pass


class ArtifactRepository(ABC):
    @abstractmethod
    async def create(self, artifact: "Artifact") -> None:
        pass

    @abstractmethod
    async def get_by_environment(self, environment_id: UUID) -> List["Artifact"]:
        pass


class AgentRepository(ABC):
    @abstractmethod
    async def create(self, agent: Agent) -> None:
        pass

    @abstractmethod
    async def get(self, agent_id: UUID) -> Optional[Agent]:
        pass

    @abstractmethod
    async def get_by_type(self, agent_type: str) -> List[Agent]:
        pass


class AgentRunRepository(ABC):
    @abstractmethod
    async def create(self, run: AgentRun) -> None:
        pass

    @abstractmethod
    async def get(self, run_id: UUID) -> Optional[AgentRun]:
        pass

    @abstractmethod
    async def get_by_task_execution(self, task_execution_id: UUID) -> List[AgentRun]:
        pass

    @abstractmethod
    async def update(self, run: AgentRun) -> None:
        pass


class ToolCallRepository(ABC):
    @abstractmethod
    async def create(self, call: ToolCall) -> None:
        pass

    @abstractmethod
    async def get(self, call_id: UUID) -> Optional[ToolCall]:
        pass

    @abstractmethod
    async def get_by_agent_run(self, agent_run_id: UUID) -> List[ToolCall]:
        pass

    @abstractmethod
    async def update(self, call: ToolCall) -> None:
        pass


class VerificationResultRepository(ABC):
    @abstractmethod
    async def create(self, verification: VerificationResult) -> None:
        pass

    @abstractmethod
    async def get(self, verification_id: UUID) -> Optional[VerificationResult]:
        pass

    @abstractmethod
    async def get_by_agent_run(self, agent_run_id: UUID) -> List[VerificationResult]:
        pass

    @abstractmethod
    async def get_by_task_execution(
        self, task_execution_id: UUID
    ) -> List[VerificationResult]:
        pass

    @abstractmethod
    async def update(self, verification: VerificationResult) -> None:
        pass


class PullRequestRepository(ABC):
    @abstractmethod
    async def create(self, pr: PullRequest) -> None:
        pass

    @abstractmethod
    async def get(self, pr_id: UUID) -> Optional[PullRequest]:
        pass

    @abstractmethod
    async def get_by_mission(self, mission_id: UUID) -> List[PullRequest]:
        pass

    @abstractmethod
    async def get_by_task_execution(self, task_execution_id: UUID) -> List[PullRequest]:
        pass

    @abstractmethod
    async def update(self, pr: PullRequest) -> None:
        pass


class WorkerRepository(ABC):
    @abstractmethod
    async def create(self, worker: Worker) -> None:
        pass

    @abstractmethod
    async def get(self, worker_id: UUID) -> Optional[Worker]:
        pass

    @abstractmethod
    async def get_by_status(self, status: str) -> List[Worker]:
        pass

    @abstractmethod
    async def get_available_workers(
        self, capabilities: Optional[List[str]] = None
    ) -> List[Worker]:
        pass

    @abstractmethod
    async def update(self, worker: Worker) -> None:
        pass


class WorkerHeartbeatRepository(ABC):
    @abstractmethod
    async def create(self, heartbeat: "WorkerHeartbeat") -> None:
        pass

    @abstractmethod
    async def get(self, heartbeat_id: UUID) -> Optional["WorkerHeartbeat"]:
        pass

    @abstractmethod
    async def get_by_worker(self, worker_id: UUID) -> List["WorkerHeartbeat"]:
        pass

    @abstractmethod
    async def get_by_task_execution(
        self, task_execution_id: UUID
    ) -> List["WorkerHeartbeat"]:
        pass

    @abstractmethod
    async def update(self, heartbeat: "WorkerHeartbeat") -> None:
        pass


class TaskLeaseRepository(ABC):
    @abstractmethod
    async def create(self, lease: "TaskLease") -> None:
        pass

    @abstractmethod
    async def get(self, lease_id: UUID) -> Optional["TaskLease"]:
        pass

    @abstractmethod
    async def get_by_worker(self, worker_id: UUID) -> List["TaskLease"]:
        pass

    @abstractmethod
    async def get_by_task_execution(self, task_execution_id: UUID) -> List["TaskLease"]:
        pass

    @abstractmethod
    async def get_stale_leases(self, before: datetime) -> List["TaskLease"]:
        pass

    @abstractmethod
    async def update(self, lease: "TaskLease") -> None:
        pass

    @abstractmethod
    async def claim_task(
        self, task_id: UUID, worker_id: UUID, lease_ttl_seconds: int
    ) -> Optional["TaskLease"]:
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
    agents: AgentRepository
    agent_runs: AgentRunRepository
    tool_calls: ToolCallRepository
    verification_results: VerificationResultRepository
    pull_requests: PullRequestRepository
    workers: WorkerRepository
    worker_heartbeats: WorkerHeartbeatRepository
    task_leases: TaskLeaseRepository

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


# Forward references
from core.domain.execution.entities import Artifact, CommandResult, ExecutionEnvironment
