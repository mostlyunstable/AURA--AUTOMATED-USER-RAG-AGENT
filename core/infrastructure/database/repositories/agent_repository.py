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
from core.domain.agents.enums import (
    AgentCapability,
    AgentRunStatus,
    AgentStatus,
    AgentType,
    ToolCallStatus,
)
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
