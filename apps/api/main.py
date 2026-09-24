import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager
from typing import List, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
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
from core.domain.execution.enums import EnvironmentStatus
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
from core.infrastructure.github.provider import GitHubProviderImpl
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

    # Verify task execution exists and belongs to this mission.
    uow = service.uow
    async with uow:
        task_exec = await uow.task_executions.get(req.task_execution_id)
        if not task_exec:
            raise HTTPException(status_code=404, detail="Task execution not found")
        task = await uow.tasks.get(task_exec.task_id)
        if not task or task.mission_id != mission_id:
            raise HTTPException(
                status_code=403,
                detail="Task execution does not belong to this mission",
            )
        # Verify task execution is complete (SUCCEEDED)
        from core.domain.tasks.enums import TaskExecutionStatus

        if task_exec.status != TaskExecutionStatus.SUCCEEDED:
            raise HTTPException(
                status_code=400,
                detail="Task execution must be SUCCEEDED to create PR",
            )
        # Verify verification passed for this task execution
        verifications = await uow.verification_results.get_by_task_execution(
            req.task_execution_id
        )
        if not verifications:
            raise HTTPException(
                status_code=400,
                detail="No verification results found for this task execution",
            )
        # Check that at least one verification passed
        passed = any(v.success for v in verifications)
        if not passed:
            raise HTTPException(
                status_code=400,
                detail="Verification must pass before creating PR",
            )
        if req.agent_run_id is not None:
            agent_runs = await uow.agent_runs.get_by_task_execution(
                req.task_execution_id
            )
            if all(r.id != req.agent_run_id for r in agent_runs):
                raise HTTPException(
                    status_code=400,
                    detail="agent_run_id does not belong to this task execution",
                )

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

    # The caller must not be able to point execution at an arbitrary repo:
    # only the mission's own repository is allowed.
    if repository_id != mission.repository_id:
        raise HTTPException(
            status_code=403,
            detail="repository_id does not match the mission repository",
        )

    # The task must exist and belong to the mission.
    uow = mission_service.uow
    async with uow:
        task = await uow.tasks.get(task_id)
        if not task or task.mission_id != mission_id:
            raise HTTPException(status_code=404, detail="Task not found")
        execution = await uow.task_executions.get(execution_id)
        if not execution or execution.task_id != task_id:
            raise HTTPException(status_code=404, detail="Task execution not found")

    return await exec_service.create_environment(
        mission_id, task_id, execution_id, repository_id
    )


@app.post("/environments/{environment_id}/execute", response_model=CommandResult)
async def execute_command(
    environment_id: UUID,
    command: ExecutionCommand,
    mission_id: UUID,
    exec_service: ExecutionService = Depends(get_execution_service),
    mission_service: MissionService = Depends(get_mission_service),
):
    # Verify ownership of the environment
    uow = mission_service.uow
    async with uow:
        env = await uow.execution_environments.get(environment_id)
        if not env or env.mission_id != mission_id:
            raise HTTPException(status_code=404, detail="Environment not found")
        if env.status != EnvironmentStatus.READY:
            raise HTTPException(status_code=400, detail="Environment not ready")

    try:
        return await exec_service.execute_command(environment_id, command)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/environments/{environment_id}")
async def cleanup_environment(
    environment_id: UUID,
    mission_id: UUID,
    exec_service: ExecutionService = Depends(get_execution_service),
    mission_service: MissionService = Depends(get_mission_service),
):
    # Verify ownership
    uow = mission_service.uow
    async with uow:
        env = await uow.execution_environments.get(environment_id)
        if not env or env.mission_id != mission_id:
            raise HTTPException(status_code=404, detail="Environment not found")

    await exec_service.cleanup_environment(environment_id)
    return {"status": "cleanup_initiated_or_completed"}


# GitHub Webhook Endpoint
class GitHubWebhookPayload(BaseModel):
    pass  # Generic payload, parsed based on event type


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    service: MissionService = Depends(get_mission_service),
):
    """Handle GitHub webhook events."""
    # Get headers
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    # Read raw body for signature verification
    body = await request.body()

    # Initialize GitHub provider
    provider = GitHubProviderImpl()
    try:
        # Verify signature
        valid = await provider.verify_webhook_signature(body, signature)
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        # Parse event
        event = await provider.parse_webhook_event(body, signature, event_type)
        if not event:
            raise HTTPException(status_code=400, detail="Invalid webhook event")

        # Process event based on type
        if event_type == "pull_request":
            await _handle_pull_request_event(event, service)
        elif event_type == "pull_request_review":
            await _handle_pull_request_review_event(event, service)
        elif event_type == "check_run":
            await _handle_check_run_event(event, service)
        elif event_type == "push":
            await _handle_push_event(event, service)
        else:
            # Log unhandled event type
            print(f"Unhandled GitHub event type: {event_type}")

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        # Log error but don't expose details
        print(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


async def _handle_pull_request_event(event, service: MissionService):
    """Handle pull request events (opened, closed, reopened, synchronized)."""
    payload = event.payload
    action = payload.get("action")
    pr_data = payload.get("pull_request", {})

    if action not in (
        "opened",
        "closed",
        "reopened",
        "synchronize",
        "ready_for_review",
    ):
        return

    pr_number = pr_data.get("number")
    repo = payload.get("repository", {})
    repo_owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")

    uow = SQLAlchemyUnitOfWork(session_factory)
    async with uow:
        # Find PR by provider PR number
        prs = await uow.pull_requests.list_by_repo(pr_number, repo_owner, repo_name)
        # Or query by provider_pr_id
        # This would need a repository method
        pass
        # Update PR status based on action
        # if action == "closed" and pr_data.get("merged"):
        #     pr.status = PullRequestStatus.MERGED
        # elif action == "closed":
        #     pr.status = PullRequestStatus.CLOSED
        # elif action == "opened":
        #     pr.status = PullRequestStatus.OPEN


async def _handle_pull_request_review_event(event, service: MissionService):
    """Handle pull request review events."""
    payload = event.payload
    action = payload.get("action")
    review = payload.get("review", {})
    pr_data = payload.get("pull_request", {})

    if action not in ("submitted", "dismissed"):
        return

    # Handle review state changes
    # Could trigger re-verification if code changed
    pass


async def _handle_check_run_event(event, service: MissionService):
    """Handle check run events (CI results)."""
    payload = event.payload
    action = payload.get("action")
    check_run = payload.get("check_run", {})

    if action not in ("completed", "rerequested"):
        return

    conclusion = check_run.get("conclusion")
    check_name = check_run.get("name", "")

    # If this is a verification check run, update our records
    if check_name.startswith("verification/"):
        # Update verification status based on conclusion
        pass


async def _handle_push_event(event, service: MissionService):
    """Handle push events (for PR synchronization)."""
    payload = event.payload
    ref = payload.get("ref", "")

    # Only care about pushes to branches that have open PRs
    if not ref.startswith("refs/heads/"):
        return

    branch = ref.replace("refs/heads/", "")
    repo = payload.get("repository", {})
    repo_owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")

    # Find open PRs for this branch and sync
    uow = SQLAlchemyUnitOfWork(session_factory)
    async with uow:
        prs = await uow.pull_requests.list_open_by_branch(branch, repo_owner, repo_name)
        for pr in prs:
            # Sync PR with latest commits
            # Update provider_url, source_commit_sha, etc.
            pass
