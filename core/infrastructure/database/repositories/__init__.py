"""Aggregate repository package.

Split from the former repositories.py GOD FILE (Phase 1).
Import path preserved: `from core.infrastructure.database.repositories import X`.
"""

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
from core.infrastructure.database.repositories.uow import SQLAlchemyUnitOfWork
from core.infrastructure.database.repositories.worker_repository import (
    SQLAlchemyTaskLeaseRepository,
    SQLAlchemyWorkerHeartbeatRepository,
    SQLAlchemyWorkerRepository,
)

__all__ = [
    "SQLAlchemyMissionRepository",
    "SQLAlchemyEventRepository",
    "SQLAlchemyTaskRepository",
    "SQLAlchemyTaskDependencyRepository",
    "SQLAlchemyTaskExecutionRepository",
    "SQLAlchemyApprovalRepository",
    "SQLAlchemyPlanRepository",
    "SQLAlchemyPullRequestRepository",
    "SQLAlchemyExecutionEnvironmentRepository",
    "SQLAlchemyCommandExecutionRepository",
    "SQLAlchemyArtifactRepository",
    "SQLAlchemyAgentRepository",
    "SQLAlchemyAgentRunRepository",
    "SQLAlchemyToolCallRepository",
    "SQLAlchemyVerificationResultRepository",
    "SQLAlchemyWorkerRepository",
    "SQLAlchemyWorkerHeartbeatRepository",
    "SQLAlchemyTaskLeaseRepository",
    "SQLAlchemyUnitOfWork",
]
