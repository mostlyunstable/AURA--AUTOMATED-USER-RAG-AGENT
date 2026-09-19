from typing import List, Protocol

from core.domain.execution.entities import (Artifact, CommandResult,
                                            ExecutionCommand,
                                            ExecutionEnvironment)


class GitWorktreeManager(Protocol):
    async def create(
        self, environment: ExecutionEnvironment, repository_id: str
    ) -> str:
        """Returns the created worktree path"""
        ...

    async def remove(self, environment: ExecutionEnvironment) -> None: ...

    async def get_base_commit(self, repository_id: str) -> str: ...


class SandboxManager(Protocol):
    async def create(self, environment: ExecutionEnvironment) -> None: ...

    async def destroy(self, environment: ExecutionEnvironment) -> None: ...

    async def execute(
        self, environment: ExecutionEnvironment, command: ExecutionCommand
    ) -> CommandResult: ...
