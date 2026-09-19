from uuid import UUID

from core.application.interfaces import UnitOfWork
from core.domain.events.entities import Event
from core.domain.execution.entities import (CommandResult, ExecutionCommand,
                                            ExecutionEnvironment)
from core.domain.execution.enums import CommandStatus, EnvironmentStatus
from core.domain.execution.interfaces import GitWorktreeManager, SandboxManager
from core.domain.tasks.enums import TaskStatus


class ExecutionService:
    def __init__(
        self,
        uow: UnitOfWork,
        worktree_manager: GitWorktreeManager,
        sandbox_manager: SandboxManager,
    ):
        self.uow = uow
        self.worktree_manager = worktree_manager
        self.sandbox_manager = sandbox_manager

    async def create_environment(
        self, mission_id: UUID, task_id: UUID, execution_id: UUID, repository_id: str
    ) -> ExecutionEnvironment:
        async with self.uow:
            # Idempotency check
            # Real implementation would query DB, simplified here

            env = ExecutionEnvironment(
                mission_id=mission_id, task_id=task_id, execution_id=execution_id
            )
            await self.uow.execution_environments.create(env)
            await self.uow.commit()

        try:
            # Get base SHA
            base_sha = await self.worktree_manager.get_base_commit(repository_id)
            env.base_commit_sha = base_sha

            # Create Worktree
            worktree_path = await self.worktree_manager.create(env, repository_id)
            env.worktree_path = worktree_path

            # Create Sandbox
            await self.sandbox_manager.create(env)

            env.status = EnvironmentStatus.READY

        except Exception as e:
            env.status = EnvironmentStatus.FAILED
            env.failure_reason = str(e)
            # Rollback logic could be placed here

        async with self.uow:
            await self.uow.execution_environments.update(env)
            await self.uow.events.append(
                Event(
                    event_type=(
                        "execution.environment.created"
                        if env.status == EnvironmentStatus.READY
                        else "execution.environment.failed"
                    ),
                    mission_id=mission_id,
                    metadata={
                        "environment_id": str(env.id),
                        "status": env.status.value,
                        "failure_reason": env.failure_reason,
                    },
                )
            )
            await self.uow.commit()

        return env

    async def execute_command(
        self, environment_id: UUID, command: ExecutionCommand
    ) -> CommandResult:
        async with self.uow:
            env = await self.uow.execution_environments.get(environment_id)
            if not env or env.status != EnvironmentStatus.READY:
                raise ValueError("Environment not ready")

        result = await self.sandbox_manager.execute(env, command)

        async with self.uow:
            await self.uow.command_executions.create(result)
            await self.uow.events.append(
                Event(
                    event_type="command.completed",
                    mission_id=env.mission_id,
                    metadata={
                        "environment_id": str(env.id),
                        "command_id": str(result.id),
                        "status": result.status.value,
                        "exit_code": result.exit_code,
                    },
                )
            )
            await self.uow.commit()

        return result

    async def cleanup_environment(self, environment_id: UUID) -> None:
        async with self.uow:
            env = await self.uow.execution_environments.get(environment_id)
            if not env:
                return
            env.status = EnvironmentStatus.CLEANING_UP
            await self.uow.execution_environments.update(env)
            await self.uow.commit()

        try:
            await self.sandbox_manager.destroy(env)
            await self.worktree_manager.remove(env)
            env.status = EnvironmentStatus.DESTROYED
        except Exception as e:
            env.status = EnvironmentStatus.FAILED
            env.failure_reason = f"Cleanup failed: {e}"

        async with self.uow:
            await self.uow.execution_environments.update(env)
            await self.uow.events.append(
                Event(
                    event_type=(
                        "execution.environment.destroyed"
                        if env.status == EnvironmentStatus.DESTROYED
                        else "execution.environment.cleanup_failed"
                    ),
                    mission_id=env.mission_id,
                    metadata={
                        "environment_id": str(env.id),
                        "status": env.status.value,
                    },
                )
            )
            await self.uow.commit()
