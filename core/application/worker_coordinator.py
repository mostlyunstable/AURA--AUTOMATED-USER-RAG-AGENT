import asyncio
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from core.application.interfaces import UnitOfWork
from core.domain.agents.entities import Agent
from core.domain.agents.enums import AgentRunStatus
from core.domain.events.entities import Event
from core.domain.missions.enums import MissionStatus
from core.domain.tasks.entities import Task, TaskExecution
from core.domain.tasks.enums import TaskExecutionStatus, TaskStatus, TaskType
from core.domain.tasks.state_machine import (
    InvalidTaskTransition,
    TaskStateMachine,
)
from core.domain.workers.entities import TaskLease, Worker
from core.domain.workers.enums import WorkerCapability, WorkerStatus
from core.domain.workers.state_machine import (
    InvalidWorkerTransition,
    WorkerStateMachine,
)
from core.infrastructure.metrics.execution import (
    aura_worker_lease_renewals_total,
    aura_worker_recoveries_total,
    aura_worker_tasks_claimed_total,
    aura_worker_tasks_completed_total,
    aura_worker_tasks_failed_total,
    aura_worker_tasks_requeued_total,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


TASK_TYPE_CAPABILITIES: Dict[TaskType, WorkerCapability] = {
    TaskType.IMPLEMENTATION: WorkerCapability.CODING,
    TaskType.TESTING: WorkerCapability.TESTING,
    TaskType.SECURITY_REVIEW: WorkerCapability.SECURITY_REVIEW,
    TaskType.CODE_REVIEW: WorkerCapability.CODING,
    TaskType.VERIFICATION: WorkerCapability.TESTING,
    TaskType.ANALYSIS: WorkerCapability.RESEARCH,
    TaskType.PLANNING: WorkerCapability.RESEARCH,
}


class StaleOwnershipError(Exception):
    """Raised when a worker no longer owns the lease it is acting on."""


class WorkerCoordinator:
    """Orchestrate one worker: poll, claim, execute, verify, complete, recover.

    The coordinator owns no execution machinery itself. It delegates to the
    existing TaskScheduler state, ExecutionService, AgentRuntime,
    VerificationEngine, and ToolGateway boundaries. All durable state lives
    in PostgreSQL; the process holds no authoritative in-memory state.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        mission_id: UUID,
        agent: Agent,
        execution_service_factory: Callable[[UnitOfWork], Any],
        agent_runtime_factory: Callable[[UnitOfWork], Any],
        verification_factory: Callable[[UnitOfWork], Any],
        worker_name: str = "aura-worker",
        capabilities: Optional[List[str]] = None,
        poll_interval_seconds: float = 5.0,
        lease_ttl_seconds: int = 90,
        heartbeat_interval_seconds: int = 30,
        max_recovery_attempts: int = 3,
        shutdown_timeout_seconds: int = 30,
    ):
        self.uow_factory = uow_factory
        self.mission_id = mission_id
        self.agent = agent
        self.execution_service_factory = execution_service_factory
        self.agent_runtime_factory = agent_runtime_factory
        self.verification_factory = verification_factory
        self.worker_name = worker_name
        self.capabilities = capabilities or [c.value for c in WorkerCapability]
        self.poll_interval_seconds = poll_interval_seconds
        self.lease_ttl_seconds = lease_ttl_seconds
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.max_recovery_attempts = max_recovery_attempts
        self.shutdown_timeout_seconds = shutdown_timeout_seconds

        self.worker: Optional[Worker] = None
        self.running = False
        self.draining = False
        self._current_lease_id: Optional[UUID] = None
        self._shutdown_event = asyncio.Event()
        self._worker_internal: Optional[Worker] = None

    @property
    def _worker(self) -> Worker:
        if self._worker_internal is None:
            raise RuntimeError("Worker not registered. Call register() first.")
        return self._worker_internal

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def register(self) -> Worker:
        """Register this worker (or re-activate a previous registration)."""
        async with self.uow_factory() as uow:
            workers = await uow.workers.get_by_status(WorkerStatus.REGISTERED.value)
            existing = next((w for w in workers if w.name == self.worker_name), None)
            if existing is not None:
                worker = existing
            else:
                worker = Worker(
                    name=self.worker_name,
                    status=WorkerStatus.REGISTERED,
                    capabilities=list(self.capabilities),
                )
                await uow.workers.create(worker)
            try:
                WorkerStateMachine.transition(worker, WorkerStatus.AVAILABLE)
            except InvalidWorkerTransition:
                pass
            worker.last_heartbeat_at = utc_now()
            worker.updated_at = utc_now()
            await uow.workers.update(worker)
            await uow.events.append(
                Event(
                    event_type="worker.registered",
                    mission_id=self.mission_id,
                    agent_id=self.agent.id,
                    metadata={"worker_id": str(worker.id), "name": worker.name},
                )
            )
            await uow.commit()
            self._worker_internal = worker
            return worker

    async def run_forever(self) -> None:
        """Poll, claim, and execute until stopped."""
        await self.register()
        self.running = True
        self.draining = False
        while self.running and not self.draining:
            try:
                claimed = await self.poll_once()
                if not claimed:
                    await asyncio.sleep(self.poll_interval_seconds)
            except Exception:
                await asyncio.sleep(self.poll_interval_seconds)

    async def shutdown(self, graceful: bool = True) -> None:
        """Stop polling; optionally wait for in-flight work, then release it."""
        self.running = False
        self.draining = True
        if graceful and self._current_lease_id is not None:
            start = time.time()
            while (time.time() - start) < self.shutdown_timeout_seconds:
                if self._current_lease_id is None:
                    break
                await asyncio.sleep(1)
        # Never leave an owned lease behind: expire it so another worker
        # can recover the task. The task itself is NOT marked complete.
        if self._current_lease_id is not None:
            await self._release_lease(self._current_lease_id)
            self._current_lease_id = None
        if self._worker is not None:
            await self._set_worker_status(WorkerStatus.STOPPED)
        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Polling and claiming
    # ------------------------------------------------------------------

    async def poll_once(self) -> Optional[TaskExecution]:
        """Poll once: claim one task and execute it to completion.

        Returns the TaskExecution, or None when no work was available.
        """
        if self.draining or not self.running:
            return None
        claimed = await self.claim_next_task()
        if claimed is None:
            return None
        task, execution, lease = claimed
        self._current_lease_id = lease.id
        try:
            await self.execute_claimed(task, execution, lease)
        finally:
            if self._current_lease_id == lease.id:
                self._current_lease_id = None
        return execution

    async def claim_next_task(
        self,
    ) -> Optional[tuple[Task, TaskExecution, TaskLease]]:
        """Find an eligible task and claim it atomically."""
        async with self.uow_factory() as uow:
            mission = await uow.missions.get(self.mission_id)
            if not mission or mission.status != MissionStatus.EXECUTING:
                return None

            tasks = await uow.tasks.get_by_mission(self.mission_id)
            deps = await uow.task_dependencies.get_dependencies_for_mission(
                self.mission_id
            )
            task_dict = {t.id: t for t in tasks}

            for task in sorted(tasks, key=lambda t: (t.priority, t.created_at)):
                if task.status != TaskStatus.QUEUED:
                    continue
                if not self._has_required_capabilities(task):
                    continue
                task_deps = [d for d in deps if d.task_id == task.id]
                blocked = False
                for dep in task_deps:
                    parent = task_dict.get(dep.depends_on_task_id)
                    if not parent or parent.status != TaskStatus.SUCCEEDED:
                        blocked = True
                        break
                if blocked:
                    continue

                claimed = await uow.tasks.claim_task(task.id, self._worker.id)
                if claimed is None:
                    # Lost the race; try the next candidate.
                    continue

                execution = TaskExecution(
                    task_id=claimed.id,
                    agent_id=self.agent.id,
                    attempt_number=claimed.attempt_count,
                    status=TaskExecutionStatus.RUNNING,
                )
                await uow.task_executions.add(execution)

                now = utc_now()
                lease = TaskLease(
                    worker_id=self._worker.id,
                    task_id=claimed.id,
                    task_execution_id=execution.id,
                    claimed_at=now,
                    lease_expires_at=now + timedelta(seconds=self.lease_ttl_seconds),
                    last_heartbeat_at=now,
                )
                await uow.task_leases.create(lease)

                try:
                    WorkerStateMachine.transition(self._worker, WorkerStatus.BUSY)
                    await uow.workers.update(self._worker)
                except InvalidWorkerTransition:
                    pass

                await uow.events.append(
                    Event(
                        event_type="task.claimed",
                        mission_id=self.mission_id,
                        task_id=claimed.id,
                        agent_id=self.agent.id,
                        metadata={
                            "worker_id": str(self._worker.id),
                            "task_execution_id": str(execution.id),
                            "lease_id": str(lease.id),
                        },
                    )
                )
                await uow.commit()
                aura_worker_tasks_claimed_total.inc()
                return claimed, execution, lease

        return None

    def _has_required_capabilities(self, task: Task) -> bool:
        required = TASK_TYPE_CAPABILITIES.get(task.task_type)
        if required is None:
            return False
        return required.value in self.capabilities

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute_claimed(
        self, task: Task, execution: TaskExecution, lease: TaskLease
    ) -> None:
        """Execute a claimed task: environment, agent, verification, completion."""
        heartbeat = asyncio.create_task(self._heartbeat_loop(lease.id))
        try:
            async with self.uow_factory() as uow:
                execution_service = self.execution_service_factory(uow)
                mission = await uow.missions.get(self.mission_id)
            if not mission:
                raise RuntimeError("Mission not found")

            env = await execution_service.create_environment(
                self.mission_id,
                task.id,
                execution.id,
                mission.repository_id,
            )
            if not env.worktree_path:
                raise RuntimeError("Execution environment has no worktree")

            async with self.uow_factory() as uow:
                runtime = self.agent_runtime_factory(uow)
                agent_run = await runtime.run(
                    task_id=task.id,
                    task_execution_id=execution.id,
                    agent_id=self.agent.id,
                    worktree_path=env.worktree_path,
                    repository_id=mission.repository_id,
                )

            await self._assert_ownership(lease.id)

            from core.domain.agents.verification import TaskContext

            context = TaskContext(
                mission_id=self.mission_id,
                task_id=task.id,
                task_execution_id=execution.id,
                agent_run_id=agent_run.id,
                repository_root=mission.repository_id,
                worktree_path=env.worktree_path,
                task_objective=task.description,
            )
            async with self.uow_factory() as uow:
                verification_engine = self.verification_factory(uow)
                verification = await verification_engine.verify(
                    context, agent_run.id, env.worktree_path, execution.id
                )

            await self._assert_ownership(lease.id)

            if verification.success:
                await self._complete_task(task, execution, lease, agent_run)
            else:
                await self._fail_task(
                    task,
                    execution,
                    lease,
                    reason=f"Verification failed: {verification.failure_reason or 'checks failed'}",
                    retryable=True,
                )
        except StaleOwnershipError:
            # Another worker owns the task now; do not touch it.
            raise
        except Exception as exc:
            await self._fail_task(
                task, execution, lease, reason=str(exc), retryable=True
            )
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Heartbeat and recovery
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self, lease_id: UUID) -> None:
        """Renew the lease until it is released or lost."""
        while self.running and not self.draining:
            await asyncio.sleep(self.heartbeat_interval_seconds)
            try:
                renewed = await self.renew_lease(lease_id)
            except StaleOwnershipError:
                return
            except Exception:
                return
            if not renewed:
                return

    async def renew_lease(self, lease_id: UUID) -> bool:
        """Renew a lease if this worker still owns it. Returns False if lost."""
        async with self.uow_factory() as uow:
            lease = await uow.task_leases.get(lease_id)
            if (
                lease is None
                or lease.worker_id != self._worker.id
                or lease.lease_expires_at <= utc_now()
            ):
                return False
            lease.lease_expires_at = utc_now() + timedelta(
                seconds=self.lease_ttl_seconds
            )
            lease.last_heartbeat_at = utc_now()
            lease.renewed_count += 1
            lease.updated_at = utc_now()
            await uow.task_leases.update(lease)
            from core.domain.workers.entities import WorkerHeartbeat

            await uow.worker_heartbeats.create(
                WorkerHeartbeat(
                    worker_id=self._worker.id,
                    task_execution_id=lease.task_execution_id,
                    task_id=lease.task_id,
                    lease_expires_at=lease.lease_expires_at,
                )
            )
            await self.worker_heartbeat_touched()
            await uow.commit()
            from core.infrastructure.metrics.execution import (
                aura_worker_lease_renewals_total as renewals,
            )

            renewals.inc()
            return True

    async def worker_heartbeat_touched(self) -> None:
        async with self.uow_factory() as uow:
            worker = await uow.workers.get(self._worker.id)
            if worker:
                worker.last_heartbeat_at = utc_now()
                worker.updated_at = utc_now()
                await uow.workers.update(worker)
                await uow.commit()

    async def _assert_ownership(self, lease_id: UUID) -> TaskLease:
        """Re-read the lease; raise if this worker no longer owns it."""
        async with self.uow_factory() as uow:
            lease = await uow.task_leases.get(lease_id)
            if (
                lease is None
                or lease.worker_id != self._worker.id
                or lease.lease_expires_at <= utc_now()
            ):
                raise StaleOwnershipError(f"Lease {lease_id} no longer owned")
            return lease

    async def _release_lease(self, lease_id: UUID) -> None:
        """Expire our own lease without touching task state."""
        async with self.uow_factory() as uow:
            lease = await uow.task_leases.get(lease_id)
            if lease is not None and lease.worker_id == self._worker.id:
                lease.lease_expires_at = utc_now()
                lease.updated_at = utc_now()
                await uow.task_leases.update(lease)
                await uow.commit()

    async def recover_stale(self) -> int:
        """Requeue tasks whose leases expired. Returns count recovered."""
        recovered = 0
        async with self.uow_factory() as uow:
            stale = await uow.task_leases.get_stale_leases(before=utc_now())
            for lease in stale:
                # Re-read inside the loop to avoid acting on a lease that
                # was renewed concurrently.
                fresh = await uow.task_leases.get(lease.id)
                if fresh is None or fresh.lease_expires_at > utc_now():
                    continue
                task = await uow.tasks.get(fresh.task_id)
                if task is None or task.status not in (
                    TaskStatus.RUNNING,
                    TaskStatus.QUEUED,
                ):
                    continue
                execution = await uow.task_executions.get(fresh.task_execution_id)
                if execution is not None and execution.status not in (
                    TaskExecutionStatus.SUCCEEDED,
                ):
                    execution.status = TaskExecutionStatus.FAILED
                    execution.error = "Worker lease expired; task recovered"
                    execution.completed_at = utc_now()
                    await uow.task_executions.update(execution)
                if task.attempt_count >= task.max_attempts:
                    continue
                try:
                    TaskStateMachine.transition(task, TaskStatus.FAILED)
                    TaskStateMachine.transition(task, TaskStatus.RETRYING)
                    TaskStateMachine.transition(task, TaskStatus.QUEUED)
                except InvalidTaskTransition:
                    continue
                task.updated_at = utc_now()
                await uow.tasks.update(task)
                await uow.events.append(
                    Event(
                        event_type="task.recovered",
                        mission_id=task.mission_id,
                        task_id=task.id,
                        agent_id=self.agent.id,
                        metadata={
                            "previous_execution_id": str(fresh.task_execution_id),
                            "previous_worker_id": str(fresh.worker_id),
                        },
                    )
                )
                await uow.commit()
                aura_worker_recoveries_total.inc()
                recovered += 1
        return recovered

    # ------------------------------------------------------------------
    # Completion and failure
    # ------------------------------------------------------------------

    async def _complete_task(
        self, task: Task, execution: TaskExecution, lease: TaskLease, agent_run
    ) -> None:
        await self._assert_ownership(lease.id)
        async with self.uow_factory() as uow:
            fresh_task = await uow.tasks.get(task.id)
            if fresh_task is None:
                raise RuntimeError("Task disappeared")
            try:
                TaskStateMachine.transition(fresh_task, TaskStatus.SUCCEEDED)
            except InvalidTaskTransition as exc:
                raise RuntimeError(f"Cannot complete task: {exc}") from exc
            fresh_task.updated_at = utc_now()
            await uow.tasks.update(fresh_task)

            fresh_exec = await uow.task_executions.get(execution.id)
            if fresh_exec is not None:
                fresh_exec.status = TaskStatus.SUCCEEDED
                fresh_exec.completed_at = utc_now()
                fresh_exec.result_metadata = {
                    **fresh_exec.result_metadata,
                    "agent_run_id": str(agent_run.id),
                }
                await uow.task_executions.update(fresh_exec)

            lease.lease_expires_at = utc_now()
            lease.updated_at = utc_now()
            await uow.task_leases.update(lease)

            await uow.events.append(
                Event(
                    event_type="task.completed",
                    mission_id=fresh_task.mission_id,
                    task_id=fresh_task.id,
                    agent_id=self.agent.id,
                    metadata={
                        "task_execution_id": str(execution.id),
                        "agent_run_id": str(agent_run.id),
                    },
                )
            )
            await uow.commit()
            aura_worker_tasks_completed_total.inc()

    async def _fail_task(
        self,
        task: Task,
        execution: TaskExecution,
        lease: TaskLease,
        reason: str,
        retryable: bool,
    ) -> None:
        async with self.uow_factory() as uow:
            fresh_task = await uow.tasks.get(task.id)
            fresh_exec = await uow.task_executions.get(execution.id)
            if fresh_task is None:
                return
            try:
                TaskStateMachine.transition(fresh_task, TaskStatus.FAILED)
            except InvalidTaskTransition:
                pass
            else:
                fresh_task.updated_at = utc_now()
                await uow.tasks.update(fresh_task)
            if fresh_exec is not None:
                fresh_exec.status = TaskStatus.FAILED
                fresh_exec.completed_at = utc_now()
                fresh_exec.error = reason
                await uow.task_executions.update(fresh_exec)

            can_retry = retryable and fresh_task.attempt_count < fresh_task.max_attempts
            if can_retry:
                try:
                    TaskStateMachine.transition(fresh_task, TaskStatus.RETRYING)
                    TaskStateMachine.transition(fresh_task, TaskStatus.QUEUED)
                except InvalidTaskTransition:
                    can_retry = False
                else:
                    fresh_task.updated_at = utc_now()
                    await uow.tasks.update(fresh_task)
                    await uow.events.append(
                        Event(
                            event_type="task.requeued",
                            mission_id=fresh_task.mission_id,
                            task_id=fresh_task.id,
                            agent_id=self.agent.id,
                            metadata={
                                "reason": reason,
                                "attempt": fresh_task.attempt_count,
                            },
                        )
                    )
                    aura_worker_tasks_requeued_total.inc()
            if not can_retry:
                await uow.events.append(
                    Event(
                        event_type="task.failed",
                        mission_id=fresh_task.mission_id,
                        task_id=fresh_task.id,
                        agent_id=self.agent.id,
                        metadata={"reason": reason},
                    )
                )
                aura_worker_tasks_failed_total.inc()

            # Always release our lease.
            fresh_lease = await uow.task_leases.get(lease.id)
            if fresh_lease is not None and fresh_lease.worker_id == self._worker.id:
                fresh_lease.lease_expires_at = utc_now()
                fresh_lease.updated_at = utc_now()
                await uow.task_leases.update(fresh_lease)
            await uow.commit()

    async def _set_worker_status(self, status) -> None:
        async with self.uow_factory() as uow:
            worker = await uow.workers.get(self._worker.id)
            if worker is None:
                return
            try:
                WorkerStateMachine.transition(worker, status)
            except InvalidWorkerTransition:
                return
            worker.updated_at = utc_now()
            await uow.workers.update(worker)
            await uow.commit()
