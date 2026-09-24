import asyncio
import os
import signal
import time
from typing import Optional

from core.domain.execution.entities import (
    CommandResult,
    ExecutionCommand,
    ExecutionEnvironment,
)
from core.domain.execution.enums import CommandStatus
from core.domain.execution.interfaces import SandboxManager
from core.infrastructure.execution.paths import resolve_within_directory
from core.infrastructure.metrics.execution import *


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

    @staticmethod
    def _kill_process_tree(process: "asyncio.subprocess.Process") -> None:
        """Kill a timed-out process and any descendants it spawned."""
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def redact_secrets(self, text: str) -> str:
        # Simplified redaction. Real implementation would use regex for API keys.
        for secret in ["NVIDIA_API_KEY", "OPENAI_API_KEY", "DATABASE_URL"]:
            val = os.environ.get(secret)
            if val and val in text:
                text = text.replace(val, "[REDACTED]")
        return text

    def _validate_arguments(
        self,
        executable: str,
        arguments: list,
        worktree_path: str,
        resolved_cwd: str,
    ) -> str | None:
        """Validate command arguments for confinement escapes.

        Returns a failure reason when rejected, otherwise None.

        Code-execution tools (python, pytest, node, ...) intentionally accept
        arbitrary code arguments; their boundary is the contained working
        directory plus the filtered environment (full isolation would require
        containers, which is out of scope for the local backend).
        """
        # git flags that redirect the repository context outside the worktree.
        if executable == "git":
            for arg in arguments:
                if (
                    arg == "-C"
                    or arg.startswith("--git-dir")
                    or arg.startswith("--work-tree")
                ):
                    return (
                        f"Argument '{arg}' is not allowed: repository "
                        "redirection escapes the worktree."
                    )
            return None

        # File-oriented commands: every non-flag argument must resolve
        # inside the worktree.
        if executable in ("cat", "ls"):
            for arg in arguments:
                if arg.startswith("-") or arg == "":
                    continue
                if not resolve_within_directory(resolved_cwd, arg):
                    return f"Argument '{arg}' is outside the allowed worktree."
            return None

        # Code-execution tools: reject arguments that look like file paths
        # escaping the worktree. We can't fully prevent code execution
        # (that's what containers are for), but we can prevent obvious
        # path traversal via command arguments.
        code_executables = {"python", "python3", "pytest", "node", "npm", "pnpm", "uv"}
        if executable in code_executables:
            for arg in arguments:
                if arg.startswith("-") or arg == "":
                    continue
                # Check if argument looks like a path and escapes
                if "/" in arg or arg.startswith("~"):
                    if not resolve_within_directory(resolved_cwd, arg):
                        return (
                            f"Argument '{arg}' appears to be a path outside "
                            "the allowed worktree."
                        )
            return None

        return None

    async def execute(
        self, environment: ExecutionEnvironment, command: ExecutionCommand
    ) -> CommandResult:
        aura_commands_requested_total.inc()
        if command.executable not in self.allowed_executables:
            aura_commands_rejected_total.inc()
            return CommandResult(
                environment_id=environment.id,
                status=CommandStatus.REJECTED,
                failure_reason=f"Executable '{command.executable}' is not allowed.",
            )

        # Ensure working directory is inside the worktree
        resolved_cwd = resolve_within_directory(
            environment.worktree_path or "", command.working_directory
        )
        if not resolved_cwd:
            aura_commands_rejected_total.inc()
            return CommandResult(
                environment_id=environment.id,
                status=CommandStatus.REJECTED,
                failure_reason="Working directory is outside the allowed worktree.",
            )

        arg_rejection = self._validate_arguments(
            command.executable,
            command.arguments,
            environment.worktree_path or "",
            resolved_cwd,
        )
        if arg_rejection:
            aura_commands_rejected_total.inc()
            return CommandResult(
                environment_id=environment.id,
                status=CommandStatus.REJECTED,
                failure_reason=arg_rejection,
            )

        aura_commands_allowed_total.inc()
        start = time.time()

        filtered_env = dict(command.environment) if command.environment else {}
        for key in [
            "NVIDIA_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GITHUB_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "DATABASE_URL",
            "POSTGRES_PASSWORD",
            "SSH_AUTH_SOCK",
        ]:
            filtered_env.pop(key, None)

        try:
            # We enforce shell=False inherently here by passing a list.
            # start_new_session puts the child in its own process group so
            # that a timeout kills the whole tree, not just the direct child.
            process = await asyncio.create_subprocess_exec(
                command.executable,
                *command.arguments,
                cwd=resolved_cwd,
                env=filtered_env,  # Filtered environment
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
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
                self._kill_process_tree(process)
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
                aura_command_output_truncated_total.inc()
            if len(stderr) > self.max_stderr:
                stderr = stderr[: self.max_stderr] + "... [TRUNCATED]"
                output_truncated = True
                aura_command_output_truncated_total.inc()

            duration = time.time() - start
            aura_command_duration_seconds.observe(duration)
            if status == CommandStatus.SUCCEEDED:
                aura_commands_succeeded_total.inc()
            elif status == CommandStatus.TIMED_OUT:
                aura_commands_timed_out_total.inc()
            else:
                aura_commands_failed_total.inc()

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
            aura_commands_failed_total.inc()
            return CommandResult(
                environment_id=environment.id,
                status=CommandStatus.FAILED,
                failure_reason="Executable not found",
            )
        except Exception as e:
            aura_commands_failed_total.inc()
            return CommandResult(
                environment_id=environment.id,
                status=CommandStatus.FAILED,
                failure_reason=str(e),
            )
