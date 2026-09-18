from typing import Protocol, List
from core.domain.execution.entities import ExecutionEnvironment, ExecutionCommand, CommandResult, Artifact

class GitWorktreeManager(Protocol):
    async def create(self, environment: ExecutionEnvironment, repository_id: str) -> str:
        """Returns the created worktree path"""
        ...
        
    async def remove(self, environment: ExecutionEnvironment) -> None:
        ...

    async def get_base_commit(self, repository_id: str) -> str:
        ...

class SandboxManager(Protocol):
    async def create(self, environment: ExecutionEnvironment) -> None:
        ...
        
    async def destroy(self, environment: ExecutionEnvironment) -> None:
        ...

    async def execute(self, environment: ExecutionEnvironment, command: ExecutionCommand) -> CommandResult:
        ...
