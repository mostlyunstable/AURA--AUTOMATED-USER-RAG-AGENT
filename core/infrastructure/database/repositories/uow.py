from sqlalchemy.ext.asyncio import AsyncSession

from core.application.interfaces import UnitOfWork
from core.infrastructure.database.repositories.agent_repository import (
    SQLAlchemyAgentRepository,
    SQLAlchemyAgentRunRepository,
    SQLAlchemyToolCallRepository,
    SQLAlchemyVerificationResultRepository,
)
from core.infrastructure.database.repositories.approval_repository import (
    SQLAlchemyApprovalRepository,
)
from core.infrastructure.database.repositories.execution_repository import (
    SQLAlchemyArtifactRepository,
    SQLAlchemyCommandExecutionRepository,
    SQLAlchemyExecutionEnvironmentRepository,
)
from core.infrastructure.database.repositories.mission_repository import (
    SQLAlchemyEventRepository,
    SQLAlchemyMissionRepository,
)
from core.infrastructure.database.repositories.plan_repository import (
    SQLAlchemyPlanRepository,
)
from core.infrastructure.database.repositories.pull_request_repository import (
    SQLAlchemyPullRequestRepository,
)
from core.infrastructure.database.repositories.task_repository import (
    SQLAlchemyTaskDependencyRepository,
    SQLAlchemyTaskExecutionRepository,
    SQLAlchemyTaskRepository,
)
from core.infrastructure.database.repositories.worker_repository import (
    SQLAlchemyTaskLeaseRepository,
    SQLAlchemyWorkerHeartbeatRepository,
    SQLAlchemyWorkerRepository,
)


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
