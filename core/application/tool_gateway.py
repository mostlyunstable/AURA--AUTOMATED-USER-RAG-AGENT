import asyncio
import hashlib
import os
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from core.application.interfaces import ExecutionEnvironmentRepository, UnitOfWork
from core.domain.agents.entities import AgentRun, ToolCall
from core.domain.agents.enums import AgentCapability, ToolCallStatus
from core.domain.agents.interfaces import AgentPolicy, ToolGateway, ToolResult
from core.domain.agents.tools import (
    FinishTaskInput,
    GetGitDiffInput,
    GetGitStatusInput,
    ListDirectoryInput,
    ReadFileInput,
    RunCommandInput,
    RunTestsInput,
    SearchRepositoryInput,
    WriteFileInput,
)
from core.domain.execution.entities import ExecutionCommand, ExecutionEnvironment
from core.domain.execution.enums import CommandStatus
from core.infrastructure.execution.artifact_collector import ArtifactCollector
from core.infrastructure.metrics.execution import (
    aura_agent_tool_calls_total,
    aura_agent_tool_rejections_total,
)


class ToolGatewayImpl(ToolGateway):
    def __init__(
        self,
        uow: UnitOfWork,
        execution_service,
        artifact_collector: ArtifactCollector,
        agent_policy: AgentPolicy,
    ):
        self.uow = uow
        self.execution_service = execution_service
        self.artifact_collector = artifact_collector
        self.agent_policy = agent_policy

    def _check_capability(
        self, capability: AgentCapability
    ) -> tuple[bool, Optional[str]]:
        if not self.agent_policy.is_allowed(capability):
            return False, f"Capability {capability.value} not allowed by policy"
        return True, None

    def _validate_worktree_path(
        self, worktree_path: str, requested_path: str
    ) -> Optional[str]:
        if not worktree_path:
            return None

        worktree_abs = os.path.abspath(worktree_path)
        worktree_real = os.path.realpath(worktree_abs)

        # Resolve requested path
        if os.path.isabs(requested_path):
            target_path = os.path.abspath(requested_path)
        else:
            target_path = os.path.abspath(os.path.join(worktree_abs, requested_path))

        # Prevent path traversal outside worktree
        if not target_path.startswith(worktree_abs):
            return None

        # Follow symlinks and ensure the ultimate target is ALSO inside the worktree
        try:
            real_path = os.path.realpath(target_path)
            if not real_path.startswith(worktree_real):
                return None
            return real_path
        except Exception:
            return None

    async def _record_tool_call(
        self,
        agent_run: AgentRun,
        tool_name: str,
        arguments: Dict[str, Any],
        policy_decision: ToolCallStatus,
        policy_reason: Optional[str] = None,
    ) -> ToolCall:
        tool_call = ToolCall(
            agent_run_id=agent_run.id,
            tool_name=tool_name,
            arguments=arguments,
            policy_decision=policy_decision,
            policy_reason=policy_reason,
            status=(
                ToolCallStatus.ALLOWED
                if policy_decision == ToolCallStatus.ALLOWED
                else ToolCallStatus.REJECTED
            ),
        )
        await self.uow.tool_calls.create(tool_call)
        await self.uow.commit()
        return tool_call

    async def execute_tool(
        self,
        agent_run: AgentRun,
        tool_name: str,
        arguments: Dict[str, Any],
        worktree_path: str,
    ) -> ToolResult:
        # Check policy limits first
        limit_error = self.agent_policy.check_limits(agent_run)
        if limit_error:
            return ToolResult(success=False, error=limit_error)

        # Get tool schema
        from core.domain.agents.tools import TOOL_SCHEMAS

        tool_schema = TOOL_SCHEMAS.get(tool_name)
        if not tool_schema:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        # Check capability
        required_cap = AgentCapability(tool_schema["required_capability"])
        allowed, reason = self._check_capability(required_cap)
        if not allowed:
            await self._record_tool_call(
                agent_run, tool_name, arguments, ToolCallStatus.REJECTED, reason
            )
            aura_agent_tool_rejections_total.inc()
            return ToolResult(success=False, error=reason)

        # Record tool call
        tool_call = await self._record_tool_call(
            agent_run, tool_name, arguments, ToolCallStatus.ALLOWED
        )
        aura_agent_tool_calls_total.inc()

        # Execute the tool
        tool_call.status = ToolCallStatus.RUNNING
        tool_call.started_at = self._utc_now()
        await self.uow.tool_calls.update(tool_call)
        await self.uow.commit()

        try:
            result = await self._execute_tool_impl(
                tool_name, arguments, worktree_path, agent_run
            )
            tool_call.status = (
                ToolCallStatus.COMPLETED if result.success else ToolCallStatus.FAILED
            )
            tool_call.completed_at = self._utc_now()
            tool_call.result_summary = (
                str(result.output)[:500] if result.output else None
            )
            tool_call.failure_reason = result.error
            await self.uow.tool_calls.update(tool_call)
            await self.uow.commit()
            return result
        except Exception as e:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.completed_at = self._utc_now()
            tool_call.failure_reason = str(e)
            await self.uow.tool_calls.update(tool_call)
            await self.uow.commit()
            return ToolResult(success=False, error=str(e))

    async def _execute_tool_impl(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        worktree_path: str,
        agent_run: AgentRun,
    ) -> ToolResult:
        if tool_name == "READ_FILE":
            return await self._read_file(arguments, worktree_path)
        elif tool_name == "LIST_DIRECTORY":
            return await self._list_directory(arguments, worktree_path)
        elif tool_name == "SEARCH_REPOSITORY":
            return await self._search_repository(arguments, worktree_path)
        elif tool_name == "WRITE_FILE":
            return await self._write_file(arguments, worktree_path)
        elif tool_name == "RUN_COMMAND":
            return await self._run_command(arguments, worktree_path, agent_run)
        elif tool_name == "GET_GIT_STATUS":
            return await self._get_git_status(arguments, worktree_path)
        elif tool_name == "GET_GIT_DIFF":
            return await self._get_git_diff(arguments, worktree_path)
        elif tool_name == "RUN_TESTS":
            return await self._run_tests(arguments, worktree_path, agent_run)
        elif tool_name == "FINISH_TASK":
            return await self._finish_task(arguments, agent_run)
        else:
            return ToolResult(success=False, error=f"Tool {tool_name} not implemented")

    async def _read_file(self, arguments: Dict, worktree_path: str) -> ToolResult:
        inp = ReadFileInput(**arguments)
        real_path = self._validate_worktree_path(worktree_path, inp.path)
        if not real_path or not os.path.exists(real_path):
            return ToolResult(success=False, error="File not found or access denied")
        if not os.path.isfile(real_path):
            return ToolResult(success=False, error="Path is not a file")

        # Size limit
        max_size = 1024 * 1024  # 1MB
        if os.path.getsize(real_path) > max_size:
            return ToolResult(success=False, error="File too large")

        try:
            with open(real_path, "r") as f:
                content = f.read()
            return ToolResult(success=True, output=content)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _list_directory(self, arguments: Dict, worktree_path: str) -> ToolResult:
        inp = ListDirectoryInput(**arguments)
        real_path = self._validate_worktree_path(worktree_path, inp.path)
        if not real_path or not os.path.exists(real_path):
            return ToolResult(
                success=False, error="Directory not found or access denied"
            )
        if not os.path.isdir(real_path):
            return ToolResult(success=False, error="Path is not a directory")

        try:
            entries = []
            for entry in os.listdir(real_path):
                full = os.path.join(real_path, entry)
                entries.append(
                    {
                        "name": entry,
                        "type": "directory" if os.path.isdir(full) else "file",
                        "size": os.path.getsize(full) if os.path.isfile(full) else 0,
                    }
                )
            return ToolResult(success=True, output=entries)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _search_repository(
        self, arguments: Dict, worktree_path: str
    ) -> ToolResult:
        inp = SearchRepositoryInput(**arguments)
        real_path = self._validate_worktree_path(worktree_path, inp.path)
        if not real_path or not os.path.exists(real_path):
            return ToolResult(success=False, error="Path not found or access denied")

        try:
            results = []
            for root, dirs, files in os.walk(real_path):
                for file in files:
                    if inp.query.lower() in file.lower():
                        full = os.path.join(root, file)
                        rel = os.path.relpath(full, real_path)
                        results.append({"path": rel, "match": "filename"})
                        if len(results) >= inp.max_results:
                            break
                if len(results) >= inp.max_results:
                    break

            # Also search content (grep-style) - limited
            if len(results) < inp.max_results:
                proc = await asyncio.create_subprocess_exec(
                    "grep",
                    "-r",
                    "-l",
                    inp.query,
                    real_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                for line in stdout.decode().strip().split("\n"):
                    if line:
                        rel = os.path.relpath(line, real_path)
                        results.append({"path": rel, "match": "content"})
                        if len(results) >= inp.max_results:
                            break

            return ToolResult(success=True, output=results)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _write_file(self, arguments: Dict, worktree_path: str) -> ToolResult:
        inp = WriteFileInput(**arguments)
        real_path = self._validate_worktree_path(worktree_path, inp.path)
        if not real_path:
            return ToolResult(success=False, error="Access denied - outside worktree")

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(real_path), exist_ok=True)

        # Size limit
        max_size = 1024 * 1024  # 1MB
        if len(inp.content.encode()) > max_size:
            return ToolResult(success=False, error="Content too large")

        try:
            with open(real_path, "w") as f:
                f.write(inp.content)
            return ToolResult(success=True, output="File written")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _run_command(
        self, arguments: Dict, worktree_path: str, agent_run: AgentRun
    ) -> ToolResult:
        inp = RunCommandInput(**arguments)

        # Create an execution environment if needed
        # For now, we'll use the execution service directly
        # The execution service manages its own environment lifecycle

        # Find or create environment for this task execution
        env = None
        async with self.uow:
            envs = await self.uow.execution_environments.get_by_task_execution(
                agent_run.task_execution_id
            )
            if envs:
                env = envs[0]

        if not env:
            return ToolResult(success=False, error="No execution environment available")

        # Validate working directory
        cmd_wd = self._validate_worktree_path(worktree_path, inp.working_directory)
        if not cmd_wd:
            return ToolResult(success=False, error="Working directory outside worktree")

        # Execute via execution service
        command = ExecutionCommand(
            executable=inp.executable,
            arguments=inp.arguments,
            working_directory=cmd_wd,
            timeout_seconds=inp.timeout_seconds,
        )

        try:
            result = await self.execution_service.execute_command(env.id, command)
            output = {
                "status": result.status.value,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration_ms": result.duration_ms,
                "timed_out": result.timed_out,
                "output_truncated": result.output_truncated,
            }
            return ToolResult(
                success=result.status == CommandStatus.SUCCEEDED,
                output=output,
                error=result.failure_reason,
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _get_git_status(self, arguments: Dict, worktree_path: str) -> ToolResult:
        inp = GetGitStatusInput(**arguments)
        real_path = self._validate_worktree_path(worktree_path, inp.path)
        if not real_path:
            return ToolResult(success=False, error="Access denied")

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                real_path,
                "status",
                "--porcelain",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ToolResult(success=False, error=stderr.decode())
            return ToolResult(success=True, output=stdout.decode().strip())
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _get_git_diff(self, arguments: Dict, worktree_path: str) -> ToolResult:
        inp = GetGitDiffInput(**arguments)
        real_path = self._validate_worktree_path(worktree_path, inp.path)
        if not real_path:
            return ToolResult(success=False, error="Access denied")

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                real_path,
                "diff",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ToolResult(success=False, error=stderr.decode())
            return ToolResult(success=True, output=stdout.decode().strip())
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _run_tests(
        self, arguments: Dict, worktree_path: str, agent_run: AgentRun
    ) -> ToolResult:
        inp = RunTestsInput(**arguments)
        real_path = self._validate_worktree_path(worktree_path, inp.working_directory)
        if not real_path:
            return ToolResult(success=False, error="Access denied")

        # Use RUN_COMMAND tool internally
        command = ExecutionCommand(
            executable=inp.command,
            arguments=inp.arguments,
            working_directory=real_path,
            timeout_seconds=inp.timeout_seconds,
        )

        # Find environment
        env = None
        async with self.uow:
            envs = await self.uow.execution_environments.get_by_task_execution(
                agent_run.task_execution_id
            )
            if envs:
                env = envs[0]

        if not env:
            return ToolResult(success=False, error="No execution environment available")

        try:
            result = await self.execution_service.execute_command(env.id, command)
            output = {
                "status": result.status.value,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration_ms": result.duration_ms,
                "timed_out": result.timed_out,
                "output_truncated": result.output_truncated,
            }
            return ToolResult(
                success=result.status == CommandStatus.SUCCEEDED,
                output=output,
                error=result.failure_reason,
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _finish_task(self, arguments: Dict, agent_run: AgentRun) -> ToolResult:
        inp = FinishTaskInput(**arguments)
        # This is a special tool that signals completion
        # The agent runtime will handle the actual completion
        return ToolResult(
            success=True,
            output={"summary": inp.summary, "success": inp.success},
            metadata={"finish_task": True, "success": inp.success},
        )

    def _utc_now(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)


def get_tool_schemas() -> Dict[str, Any]:
    from core.domain.agents.tools import TOOL_SCHEMAS

    return TOOL_SCHEMAS
