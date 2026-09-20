import os
from contextlib import asynccontextmanager
from typing import List, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, generate_latest
from pydantic import BaseModel

from core.application.execution_service import ExecutionService
from core.application.mission_orchestrator import MissionOrchestrator
from core.application.mission_service import MissionNotFound, MissionService
from core.application.planner_agent import PlannerAgent
from core.domain.approvals.entities import Approval
from core.domain.approvals.enums import ApprovalStatus, ApprovalType
from core.domain.events.entities import Event
from core.domain.execution.entities import (
    CommandResult,
    ExecutionCommand,
    ExecutionEnvironment,
)
from core.domain.llm.interfaces import LLMProvider
from core.domain.missions.entities import Mission
from core.domain.missions.enums import MissionStatus
from core.domain.missions.state_machine import InvalidMissionTransition
from core.domain.plans.entities import EngineeringPlan
from core.domain.plans.enums import PlanStatus
from core.domain.pull_requests.entities import PullRequest
from core.domain.pull_requests.enums import PullRequestProvider, PullRequestStatus
from core.domain.tasks.entities import Task, TaskDependency
from core.domain.tasks.enums import TaskStatus, TaskType
from core.infrastructure.context.forge_adapter import StubForgeContextProvider
from core.infrastructure.context.repository_adapter import StubRepositoryContextProvider
from core.infrastructure.database.connection import get_engine, get_session_maker
from core.infrastructure.database.repositories import SQLAlchemyUnitOfWork
from core.infrastructure.execution.git_worktree import LocalGitWorktreeManager
from core.infrastructure.execution.local_sandbox import LocalSandboxManager
from core.infrastructure.llm.fake_provider import FakeLLMProvider
from core.infrastructure.llm.nvidia_provider import NvidiaLLMProvider
from core.infrastructure.logging.config import configure_logging

configure_logging()
import structlog

logger = structlog.get_logger(__name__)

# Metrics
HTTP_REQUESTS = Counter(
    "http_requests_total", "Total HTTP Requests", ["method", "endpoint", "status"]
)
MISSION_CREATIONS = Counter("mission_creations_total", "Total missions created")
MISSION_TRANSITIONS = Counter(
    "mission_transitions_total", "Total transitions", ["status"]
)
TASKS_CREATED = Counter("aura_tasks_created_total", "Total tasks created")
APPROVALS_TOTAL = Counter("aura_approvals_total", "Total approvals requested")

DB_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://aura:aura@localhost:5432/aura")
engine = get_engine(DB_URL)
session_factory = get_session_maker(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if False:
        from core.infrastructure.database.models import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="AURA - Autonomous Engineering Runtime", lifespan=lifespan)


async def get_mission_service() -> MissionService:
    uow = SQLAlchemyUnitOfWork(session_factory)
    return MissionService(uow)


class CreateMissionRequest(BaseModel):
    title: str
    description: str
    repository_id: str
    source: str
    risk_level: str = "medium"


class TransitionRequest(BaseModel):
    target_state: MissionStatus


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "aura"}


@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    return generate_latest()


@app.post("/missions", response_model=Mission)
async def create_mission(
    req: CreateMissionRequest, service: MissionService = Depends(get_mission_service)
):
    mission = await service.create_mission(
        title=req.title,
        description=req.description,
        repository_id=req.repository_id,
        source=req.source,
        risk_level=req.risk_level,
    )
    MISSION_CREATIONS.inc()
    logger.info("mission_created", mission_id=str(mission.id))
    return mission


@app.get("/missions", response_model=List[Mission])
async def list_missions(service: MissionService = Depends(get_mission_service)):
    return await service.list_missions()


@app.get("/missions/{mission_id}", response_model=Mission)
async def get_mission(
    mission_id: UUID, service: MissionService = Depends(get_mission_service)
):
    mission = await service.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@app.post("/missions/{mission_id}/transition", response_model=Mission)
async def transition_mission(
    mission_id: UUID,
    req: TransitionRequest,
    service: MissionService = Depends(get_mission_service),
):
    try:
        updated = await service.update_mission_status(mission_id, req.target_state)
        MISSION_TRANSITIONS.labels(status=req.target_state.value).inc()
        logger.info(
            "mission_transitioned",
            mission_id=str(mission_id),
            target_state=req.target_state.value,
        )
        return updated
    except MissionNotFound:
        raise HTTPException(status_code=404, detail="Mission not found")
    except InvalidMissionTransition as e:
        logger.warning("invalid_transition", mission_id=str(mission_id), error=str(e))
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/missions/{mission_id}/tasks", response_model=List[Task])
async def list_tasks(
    mission_id: UUID, service: MissionService = Depends(get_mission_service)
):
    uow = service.uow
    async with uow:
        return await uow.tasks.get_by_mission(mission_id)


class CreateTaskRequest(BaseModel):
    title: str
    description: str
    task_type: TaskType
    priority: int = 0
    max_attempts: int = 3


@app.post("/missions/{mission_id}/tasks", response_model=Task)
async def create_task(
    mission_id: UUID,
    req: CreateTaskRequest,
    service: MissionService = Depends(get_mission_service),
):
    uow = service.uow
    orchestrator = MissionOrchestrator(uow)
    task = Task(
        mission_id=mission_id,
        title=req.title,
        description=req.description,
        task_type=req.task_type,
        priority=req.priority,
        max_attempts=req.max_attempts,
    )
    await orchestrator.add_task(task)
    TASKS_CREATED.inc()
    return task


class DependencyRequest(BaseModel):
    depends_on_task_id: UUID


@app.post("/tasks/{task_id}/dependencies")
async def add_dependency(
    task_id: UUID,
    req: DependencyRequest,
    service: MissionService = Depends(get_mission_service),
):
    uow = service.uow
    orchestrator = MissionOrchestrator(uow)

    # We need mission_id.
    async with uow:
        task = await uow.tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        mission_id = task.mission_id

    dep = TaskDependency(task_id=task_id, depends_on_task_id=req.depends_on_task_id)
    try:
        await orchestrator.add_dependency(mission_id, dep)
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": "ok"}


class ApproveRequest(BaseModel):
    approval_type: ApprovalType


@app.post("/missions/{mission_id}/approve", response_model=Approval)
async def request_approve(
    mission_id: UUID,
    req: ApproveRequest,
    service: MissionService = Depends(get_mission_service),
):
    approval = await service.request_approval(mission_id, req.approval_type)

    # Fast-forward auto approval for testing/simplicity
    approval = await service.resolve_approval(
        approval.id, ApprovalStatus.APPROVED, "Auto approved"
    )
    APPROVALS_TOTAL.inc()
    return approval


class RejectRequest(BaseModel):
    approval_type: ApprovalType
    reason: str


class CreatePullRequestRequest(BaseModel):
    task_execution_id: UUID
    agent_run_id: Optional[UUID] = None
    provider: PullRequestProvider = PullRequestProvider.GITHUB
    source_branch: str
    target_branch: str = "main"
    title: str
    description: str = ""


class CreatePullRequestResponse(BaseModel):
    id: UUID
    mission_id: UUID
    task_execution_id: UUID
    agent_run_id: Optional[UUID] = None
    provider: PullRequestProvider
    provider_pr_id: Optional[int] = None
    provider_url: Optional[str] = None
    source_branch: str
    target_branch: str
    title: str
    description: str
    status: PullRequestStatus
    source_commit_sha: Optional[str] = None
    merge_commit_sha: Optional[str] = None
    merged_at: Optional[str] = None
    merged_by: Optional[str] = None
    approval_ids: List[UUID] = []


class MergeApproveRequest(BaseModel):
    approval_type: ApprovalType
    reason: Optional[str] = None


class MergeRejectRequest(BaseModel):
    approval_type: ApprovalType
    reason: str


@app.post("/missions/{mission_id}/pr", response_model=CreatePullRequestResponse)
async def create_pull_request(
    mission_id: UUID,
    req: CreatePullRequestRequest,
    service: MissionService = Depends(get_mission_service),
):
    """Create a pull request from a verified worktree."""
    # Verify mission is in VERIFIED state
    mission = await service.get_mission(mission_id)
    if not mission or mission.status != MissionStatus.VERIFIED:
        raise HTTPException(
            status_code=400, detail="Mission must be in VERIFIED state to create PR"
        )

    # Verify task execution exists
    uow = service.uow
    async with uow:
        task_exec = await uow.task_executions.get_by_task(req.task_execution_id)
        # Simplified - in reality we'd check task_execution exists
        pass

    # For now, create PR record with DRAFT status
    # In real implementation, this would call GitHub API to create the PR
    pr = PullRequest(
        mission_id=mission_id,
        task_execution_id=req.task_execution_id,
        agent_run_id=req.agent_run_id,
        provider=req.provider,
        source_branch=req.source_branch,
        target_branch=req.target_branch,
        title=req.title,
        description=req.description,
        status=PullRequestStatus.DRAFT,
    )

    async with uow:
        await uow.pull_requests.create(pr)
        await uow.events.append(
            Event(
                event_type="pull_request.created",
                mission_id=mission_id,
                metadata={"pull_request_id": str(pr.id), "title": pr.title},
            )
        )
        await uow.commit()

    return CreatePullRequestResponse(
        id=pr.id,
        mission_id=pr.mission_id,
        task_execution_id=pr.task_execution_id,
        agent_run_id=pr.agent_run_id,
        provider=pr.provider,
        provider_pr_id=pr.provider_pr_id,
        provider_url=pr.provider_url,
        source_branch=pr.source_branch,
        target_branch=pr.target_branch,
        title=pr.title,
        description=pr.description,
        status=pr.status,
        source_commit_sha=pr.source_commit_sha,
        merge_commit_sha=pr.merge_commit_sha,
        merged_at=pr.merged_at.isoformat() if pr.merged_at else None,
        merged_by=pr.merged_by,
        approval_ids=pr.approval_ids,
    )


@app.post("/missions/{mission_id}/merge", response_model=Approval)
async def request_merge(
    mission_id: UUID,
    req: MergeApproveRequest,
    service: MissionService = Depends(get_mission_service),
):
    """Request merge approval for a mission."""
    # Verify mission is in AWAITING_HUMAN_APPROVAL state
    mission = await service.get_mission(mission_id)
    if not mission or mission.status != MissionStatus.AWAITING_HUMAN_APPROVAL:
        raise HTTPException(
            status_code=400, detail="Mission must be in AWAITING_HUMAN_APPROVAL state"
        )

    approval = await service.request_approval(mission_id, req.approval_type)
    return approval


@app.post("/missions/{mission_id}/merge/approve", response_model=Approval)
async def approve_merge(
    mission_id: UUID,
    req: MergeApproveRequest,
    service: MissionService = Depends(get_mission_service),
):
    """Approve a merge request."""
    # Verify mission is in AWAITING_HUMAN_APPROVAL state
    mission = await service.get_mission(mission_id)
    if not mission or mission.status != MissionStatus.AWAITING_HUMAN_APPROVAL:
        raise HTTPException(
            status_code=400, detail="Mission must be in AWAITING_HUMAN_APPROVAL state"
        )

    # Get the pending merge approval
    uow = service.uow
    async with uow:
        approvals = await uow.approvals.get_by_mission(mission_id)
        merge_approvals = [
            a
            for a in approvals
            if a.approval_type == ApprovalType.MERGE and a.status == "PENDING"
        ]
        if not merge_approvals:
            raise HTTPException(
                status_code=404, detail="No pending merge approval found"
            )
        approval = merge_approvals[0]

    approval = await service.resolve_approval(
        approval.id, ApprovalStatus.APPROVED, req.reason or "Approved"
    )
    return approval


@app.post("/missions/{mission_id}/merge/reject", response_model=Approval)
async def reject_merge(
    mission_id: UUID,
    req: MergeRejectRequest,
    service: MissionService = Depends(get_mission_service),
):
    """Reject a merge request."""
    # Verify mission is in AWAITING_HUMAN_APPROVAL state
    mission = await service.get_mission(mission_id)
    if not mission or mission.status != MissionStatus.AWAITING_HUMAN_APPROVAL:
        raise HTTPException(
            status_code=400, detail="Mission must be in AWAITING_HUMAN_APPROVAL state"
        )

    # Get the pending merge approval
    uow = service.uow
    async with uow:
        approvals = await uow.approvals.get_by_mission(mission_id)
        merge_approvals = [
            a
            for a in approvals
            if a.approval_type == ApprovalType.MERGE and a.status == "PENDING"
        ]
        if not merge_approvals:
            raise HTTPException(
                status_code=404, detail="No pending merge approval found"
            )
        approval = merge_approvals[0]

    approval = await service.resolve_approval(
        approval.id, ApprovalStatus.REJECTED, req.reason
    )
    return approval


@app.post("/missions/{mission_id}/reject", response_model=Approval)
async def request_reject(
    mission_id: UUID,
    req: RejectRequest,
    service: MissionService = Depends(get_mission_service),
):
    approval = await service.request_approval(mission_id, req.approval_type)
    approval = await service.resolve_approval(
        approval.id, ApprovalStatus.REJECTED, req.reason
    )
    return approval


@app.post("/missions/{mission_id}/plan", response_model=EngineeringPlan)
async def generate_plan(
    mission_id: UUID, service: MissionService = Depends(get_mission_service)
):
    uow = service.uow

    # Use Nvidia if key is present, else Fake
    api_key = os.environ.get("NVIDIA_API_KEY")
    if api_key:
        llm_provider: LLMProvider = NvidiaLLMProvider(api_key=api_key)
    else:
        llm_provider = FakeLLMProvider()

    planner = PlannerAgent(
        uow=uow,
        llm_provider=llm_provider,
        repo_provider=StubRepositoryContextProvider(),
        forge_provider=StubForgeContextProvider(),
    )

    plan = await planner.generate_plan(mission_id)

    # Transition mission to PLANNED if generation successful
    # update_mission_status handles its own uow context
    mission = None
    async with uow:
        mission = await uow.missions.get(mission_id)
    if mission and mission.status == MissionStatus.PLANNING:
        await service.update_mission_status(mission_id, MissionStatus.PLANNED)

    return plan


@app.get("/missions/{mission_id}/plans", response_model=List[EngineeringPlan])
async def list_plans(
    mission_id: UUID, service: MissionService = Depends(get_mission_service)
):
    uow = service.uow
    async with uow:
        return await uow.plans.get_by_mission(mission_id)


@app.get("/plans/{plan_id}", response_model=EngineeringPlan)
async def get_plan(
    plan_id: UUID, service: MissionService = Depends(get_mission_service)
):
    uow = service.uow
    async with uow:
        plan = await uow.plans.get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        return plan


@app.post("/plans/{plan_id}/approve", response_model=EngineeringPlan)
async def approve_plan(
    plan_id: UUID, service: MissionService = Depends(get_mission_service)
):
    uow = service.uow
    async with uow:
        plan = await uow.plans.get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        plan.status = PlanStatus.APPROVED
        await uow.plans.update(plan)
        await uow.commit()
        return plan


@app.post("/plans/{plan_id}/reject", response_model=EngineeringPlan)
async def reject_plan(
    plan_id: UUID, service: MissionService = Depends(get_mission_service)
):
    uow = service.uow
    async with uow:
        plan = await uow.plans.get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        plan.status = PlanStatus.REJECTED
        await uow.plans.update(plan)
        await uow.commit()
        return plan


def get_execution_service(
    service: MissionService = Depends(get_mission_service),
) -> ExecutionService:
    uow = service.uow
    return ExecutionService(
        uow=uow,
        worktree_manager=LocalGitWorktreeManager(),
        sandbox_manager=LocalSandboxManager(),
    )


@app.post(
    "/tasks/{task_id}/executions/{execution_id}/environment",
    response_model=ExecutionEnvironment,
)
async def create_environment(
    mission_id: UUID,
    task_id: UUID,
    execution_id: UUID,
    repository_id: str,
    exec_service: ExecutionService = Depends(get_execution_service),
    mission_service: MissionService = Depends(get_mission_service),
):
    # Verify mission is APPROVED_FOR_EXECUTION or EXECUTING
    mission = await mission_service.get_mission(mission_id)
    if not mission or mission.status not in [
        MissionStatus.APPROVED_FOR_EXECUTION,
        MissionStatus.EXECUTING,
    ]:
        raise HTTPException(
            status_code=403, detail="Mission is not approved for execution"
        )

    return await exec_service.create_environment(
        mission_id, task_id, execution_id, repository_id
    )


@app.post("/environments/{environment_id}/execute", response_model=CommandResult)
async def execute_command(
    environment_id: UUID,
    command: ExecutionCommand,
    exec_service: ExecutionService = Depends(get_execution_service),
):
    try:
        return await exec_service.execute_command(environment_id, command)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/environments/{environment_id}")
async def cleanup_environment(
    environment_id: UUID,
    exec_service: ExecutionService = Depends(get_execution_service),
):
    await exec_service.cleanup_environment(environment_id)
    return {"status": "cleanup_initiated_or_completed"}
