import asyncio
import os
import shutil
from typing import Optional

from core.domain.execution.entities import ExecutionEnvironment
from core.domain.execution.interfaces import GitWorktreeManager
from core.infrastructure.metrics.execution import (
    aura_worktrees_created_total,
    aura_worktrees_removed_total,
)


class LocalGitWorktreeManager(GitWorktreeManager):
    def __init__(self, worktree_root: str = "~/.aura/worktrees"):
        self.worktree_root = os.path.abspath(os.path.expanduser(worktree_root))
        os.makedirs(self.worktree_root, exist_ok=True)

    async def get_base_commit(self, repository_id: str) -> str:
        # In a real environment, repository_id would be resolved to a path.
        # Here we mock it if the repo does not exist, or run git rev-parse HEAD.
        repo_path = os.path.abspath(repository_id)
        if not os.path.exists(repo_path) or not os.path.exists(
            os.path.join(repo_path, ".git")
        ):
            return "mock-sha-123"

        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            repo_path,
            "rev-parse",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        return stdout.decode().strip()

    async def create(
        self, environment: ExecutionEnvironment, repository_id: str
    ) -> str:
        repo_path = os.path.abspath(repository_id)
        worktree_path = os.path.join(
            self.worktree_root,
            f"{environment.mission_id}",
            f"{environment.task_id}",
            f"{environment.execution_id}",
        )

        # Ensure path is inside worktree_root
        if not os.path.abspath(worktree_path).startswith(self.worktree_root):
            raise ValueError("Worktree path traversal detected")

        branch_name = f"aura/task/{environment.execution_id}"

        if os.path.exists(repo_path) and os.path.exists(
            os.path.join(repo_path, ".git")
        ):
            # Create git worktree
            process = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                repo_path,
                "worktree",
                "add",
                "-b",
                branch_name,
                worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(f"Git worktree creation failed: {stderr.decode()}")
        else:
            # Fallback for testing environments where the repo might not be a real git repo
            os.makedirs(worktree_path, exist_ok=True)

        # Place ownership marker
        with open(os.path.join(worktree_path, ".aura-environment"), "w") as f:
            f.write(f"environment_id={environment.id}\n")

        aura_worktrees_created_total.inc()
        return worktree_path

    async def remove(self, environment: ExecutionEnvironment) -> None:
        if not environment.worktree_path:
            return

        if not os.path.abspath(environment.worktree_path).startswith(
            self.worktree_root
        ):
            raise ValueError("Worktree path traversal detected")

        # First remove git worktree reference
        repo_path = None  # Ideally passed down or parsed, assume cleanup via shutil for now if branch is checked out
        # ...

        if os.path.exists(environment.worktree_path):
            shutil.rmtree(environment.worktree_path, ignore_errors=True)
            aura_worktrees_removed_total.inc()
