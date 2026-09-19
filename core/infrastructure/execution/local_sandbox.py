import asyncio
import os
import time
from typing import Optional

from core.domain.execution.entities import (CommandResult, ExecutionCommand,
                                            ExecutionEnvironment)
from core.domain.execution.enums import CommandStatus
from core.domain.execution.interfaces import SandboxManager


class LocalSandboxManager(SandboxManager):
    def __init__(self):
        self.allowed_executables = set(
            os.environ.get(
                "AURA_ALLOWED_EXECUTABLES",
                "git,python,python3,pytest,node,npm,pnpm,uv,ls,echo,cat",
            ).split(",")
        )
        self.max_stdout = int(os.environ.get("AURA_MAX_STDOUT_BYTES", 1024 * 1024))
        self.max_stderr = int(os.environ.get("AURA_MAX_STDERR_BYTES", 1024 * 1024))

    async def create(self, environment: ExecutionEnvironment) -> None:
        # Local backend doesn't need heavy VM initialization.
        pass

    async def destroy(self, environment: ExecutionEnvironment) -> None:
        pass

    def redact_secrets(self, text: str) -> str:
        # Simplified redaction. Real implementation would use regex for API keys.
        for secret in ["NVIDIA_API_KEY", "OPENAI_API_KEY", "DATABASE_URL"]:
            val = os.environ.get(secret)
            if val and val in text:
                text = text.replace(val, "[REDACTED]")
        return text

    async def execute(
        self, environment: ExecutionEnvironment, command: ExecutionCommand
    ) -> CommandResult:
        if command.executable not in self.allowed_executables:
            return CommandResult(
                environment_id=environment.id,
                status=CommandStatus.REJECTED,
                failure_reason=f"Executable '{command.executable}' is not allowed.",
            )

        # Ensure working directory is inside the worktree
        resolved_cwd = os.path.abspath(command.working_directory)
        if not environment.worktree_path or not resolved_cwd.startswith(
            os.path.abspath(environment.worktree_path)
        ):
            return CommandResult(
                environment_id=environment.id,
                status=CommandStatus.REJECTED,
                failure_reason="Working directory is outside the allowed worktree.",
            )

        start = time.time()

        try:
            # We enforce shell=False inherently here by passing a list
            process = await asyncio.create_subprocess_exec(
                command.executable,
                *command.arguments,
                cwd=resolved_cwd,
                filtered_env = dict(command.environment) if command.environment else {}
                for key in ["NVIDIA_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "DATABASE_URL", "POSTGRES_PASSWORD", "SSH_AUTH_SOCK"]:
                    filtered_env.pop(key, None)

                env=filtered_env,  # Filtered environment
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=command.timeout_seconds
                )
                status = (
                    CommandStatus.SUCCEEDED
                    if process.returncode == 0
                    else CommandStatus.FAILED
                )
                exit_code = process.returncode
                timed_out = False
            except asyncio.TimeoutError:
                process.kill()
                stdout_bytes, stderr_bytes = await process.communicate()
                status = CommandStatus.TIMED_OUT
                exit_code = -1
                timed_out = True

            stdout = self.redact_secrets(stdout_bytes.decode(errors="replace"))
            stderr = self.redact_secrets(stderr_bytes.decode(errors="replace"))

            output_truncated = False
            if len(stdout) > self.max_stdout:
                stdout = stdout[: self.max_stdout] + "... [TRUNCATED]"
                output_truncated = True
            if len(stderr) > self.max_stderr:
                stderr = stderr[: self.max_stderr] + "... [TRUNCATED]"
                output_truncated = True

            return CommandResult(
                environment_id=environment.id,
                status=status,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=(time.time() - start) * 1000,
                timed_out=timed_out,
                output_truncated=output_truncated,
            )

        except FileNotFoundError:
            return CommandResult(
                environment_id=environment.id,
                status=CommandStatus.FAILED,
                failure_reason="Executable not found",
            )
        except Exception as e:
            return CommandResult(
                environment_id=environment.id,
                status=CommandStatus.FAILED,
                failure_reason=str(e),
            )
