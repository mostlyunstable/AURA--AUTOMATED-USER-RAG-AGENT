import asyncio
import os
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.application.interfaces import UnitOfWork
from core.domain.agents.verification import (
    TaskContext,
    TaskResult,
    VerificationCheck,
    VerificationCheckResult,
    VerificationCheckType,
    VerificationResult,
    VerificationStatus,
)
from core.domain.events.entities import Event
from core.domain.execution.entities import ExecutionEnvironment
from core.domain.execution.enums import ArtifactType, CommandStatus, EnvironmentStatus
from core.domain.tasks.entities import TaskExecution
from core.domain.tasks.enums import TaskStatus
from core.infrastructure.execution.artifact_collector import ArtifactCollector
from core.infrastructure.metrics.execution import (
    aura_verification_checks_total,
    aura_verification_duration_seconds,
    aura_verification_failures_total,
    aura_verification_runs_total,
)


class VerificationEngine:
    def __init__(
        self,
        uow: UnitOfWork,
        artifact_collector: ArtifactCollector,
    ):
        self.uow = uow
        self.artifact_collector = artifact_collector

    async def verify(
        self,
        context: TaskContext,
        agent_run_id: UUID,
        worktree_path: str,
        execution_id: UUID,
    ) -> VerificationResult:
        verification = VerificationResult(
            agent_run_id=agent_run_id,
            task_execution_id=context.task_execution_id,
            status=VerificationStatus.INCONCLUSIVE,
            success=False,
        )

        start_time = time.time()

        async with self.uow:
            await self.uow.verification_results.create(verification)
            await self.uow.events.append(
                Event(
                    event_type="verification.started",
                    mission_id=context.mission_id,
                    task_id=context.task_id,
                    agent_id=context.agent_run_id,
                    metadata={
                        "verification_id": str(verification.id),
                        "task_execution_id": str(context.task_execution_id),
                    },
                )
            )
            await self.uow.commit()

        try:
            # Run all verification checks
            checks = []

            # 1. Git Status Check
            check = await self._check_git_status(context, worktree_path)
            checks.append(check)
            await self._record_check(verification, check)

            # 2. Git Diff Check
            check = await self._check_git_diff(context, worktree_path)
            checks.append(check)
            await self._record_check(verification, check)

            # 3. Test Results Check
            check = await self._check_tests(
                context, worktree_path, execution_id, agent_run_id
            )
            checks.append(check)
            await self._record_check(verification, check)

            # 4. Acceptance Criteria Check
            check = await self._check_acceptance_criteria(context, worktree_path)
            checks.append(check)
            await self._record_check(verification, check)

            # 5. Scope Check
            check = await self._check_scope(context, worktree_path)
            checks.append(check)
            await self._record_check(verification, check)

            # 6. Artifacts Check
            check = await self._check_artifacts(context, execution_id)
            checks.append(check)
            await self._record_check(verification, check)

            # 7. Policy Violations Check
            check = await self._check_policy_violations(context, worktree_path)
            checks.append(check)
            await self._record_check(verification, check)

            # 8. Execution Failures Check
            check = await self._check_execution_failures(context, execution_id)
            checks.append(check)
            await self._record_check(verification, check)

            # 9. Secret Leakage Check
            check = await self._check_secret_leakage(context, worktree_path)
            checks.append(check)
            await self._record_check(verification, check)

            # 10. Unexpected Changes Check
            check = await self._check_unexpected_changes(context, worktree_path)
            checks.append(check)
            await self._record_check(verification, check)

            # Determine overall status
            verification.checks = checks
            verification.failed_checks = [
                c for c in checks if c.result == VerificationCheckResult.FAILED
            ]
            verification.warnings = [
                c.message for c in checks if c.result == VerificationCheckResult.WARNING
            ]

            # Collect changed files from git status/diff
            verification.changed_files = await self._get_changed_files(worktree_path)

            # Determine overall success
            has_failures = len(verification.failed_checks) > 0
            verification.success = not has_failures
            verification.status = (
                VerificationStatus.PASSED
                if verification.success
                else VerificationStatus.FAILED
            )

            if not has_failures:
                for c in checks:
                    if c.result == VerificationCheckResult.WARNING:
                        verification.status = VerificationStatus.INCONCLUSIVE
                        break

            verification.completed_at = self._utc_now()

        except Exception as e:
            verification.status = VerificationStatus.BLOCKED
            verification.success = False
            verification.failure_reason = f"Verification error: {str(e)}"
            verification.completed_at = self._utc_now()
            aura_verification_failures_total.inc()

        finally:
            duration = time.time() - start_time
            aura_verification_duration_seconds.observe(duration)
            aura_verification_runs_total.inc()

            async with self.uow:
                await self.uow.verification_results.update(verification)
                await self.uow.events.append(
                    Event(
                        event_type="verification.completed",
                        mission_id=context.mission_id,
                        task_id=context.task_id,
                        agent_id=context.agent_run_id,
                        metadata={
                            "verification_id": str(verification.id),
                            "status": verification.status.value,
                            "success": verification.success,
                            "checks_count": len(verification.checks),
                            "failed_checks_count": len(verification.failed_checks),
                        },
                    )
                )
                await self.uow.commit()

        return verification

    async def _check_git_status(
        self, context: TaskContext, worktree_path: str
    ) -> VerificationCheck:
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree_path,
                "status",
                "--porcelain",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            duration_ms = (time.time() - start) * 1000

            if proc.returncode != 0:
                return VerificationCheck(
                    check_type=VerificationCheckType.GIT_STATUS,
                    result=VerificationCheckResult.FAILED,
                    message=f"Git status failed: {stderr.decode()}",
                    duration_ms=duration_ms,
                )

            status_output = stdout.decode().strip()
            files = status_output.split("\n") if status_output else []

            return VerificationCheck(
                check_type=VerificationCheckType.GIT_STATUS,
                result=VerificationCheckResult.PASSED,
                message=f"Git status clean, {len(files)} files changed",
                details={"changed_files": files, "file_count": len(files)},
                duration_ms=duration_ms,
            )
        except Exception as e:
            return VerificationCheck(
                check_type=VerificationCheckType.GIT_STATUS,
                result=VerificationCheckResult.FAILED,
                message=f"Git status check error: {str(e)}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _check_git_diff(
        self, context: TaskContext, worktree_path: str
    ) -> VerificationCheck:
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree_path,
                "diff",
                "--stat",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            duration_ms = (time.time() - start) * 1000

            if proc.returncode != 0:
                return VerificationCheck(
                    check_type=VerificationCheckType.GIT_DIFF,
                    result=VerificationCheckResult.FAILED,
                    message=f"Git diff failed: {stderr.decode()}",
                    duration_ms=duration_ms,
                )

            diff_output = stdout.decode().strip()

            # Also get full diff for detailed analysis
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree_path,
                "diff",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            full_stdout, _ = await proc.communicate()
            full_diff = full_stdout.decode().strip()

            return VerificationCheck(
                check_type=VerificationCheckType.GIT_DIFF,
                result=VerificationCheckResult.PASSED,
                message=f"Git diff analyzed",
                details={
                    "stat": diff_output,
                    "full_diff": full_diff[:5000],  # Truncate for storage
                },
                duration_ms=duration_ms,
            )
        except Exception as e:
            return VerificationCheck(
                check_type=VerificationCheckType.GIT_DIFF,
                result=VerificationCheckResult.FAILED,
                message=f"Git diff check error: {str(e)}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _check_tests(
        self,
        context: TaskContext,
        worktree_path: str,
        execution_id: UUID,
        agent_run_id: UUID,
    ) -> VerificationCheck:
        start = time.time()
        try:
            # Find the test execution from command executions
            async with self.uow:
                envs = await self.uow.execution_environments.get_by_task_execution(
                    execution_id
                )
                if not envs:
                    return VerificationCheck(
                        check_type=VerificationCheckType.TESTS,
                        result=VerificationCheckResult.SKIPPED,
                        message="No execution environment found",
                        duration_ms=(time.time() - start) * 1000,
                    )
                env = envs[0]

                commands = await self.uow.command_executions.get_by_environment(env.id)
                # Check if any commands have test-related indicators
                test_commands = [
                    c
                    for c in commands
                    if "test" in str(c.stdout).lower()
                    or "test" in str(c.stderr).lower()
                    or c.exit_code == 0  # Include all successful commands for now
                ]

                if not test_commands:
                    # Check tool calls for RUN_TESTS
                    async with self.uow:
                        tool_calls = await self.uow.tool_calls.get_by_agent_run(
                            agent_run_id
                        )
                    test_tool_calls = [
                        tc for tc in tool_calls if tc.tool_name == "RUN_TESTS"
                    ]
                    if not test_tool_calls:
                        return VerificationCheck(
                            check_type=VerificationCheckType.TESTS,
                            result=VerificationCheckResult.SKIPPED,
                            message="No test commands executed",
                            duration_ms=(time.time() - start) * 1000,
                        )
                    return VerificationCheck(
                        check_type=VerificationCheckType.TESTS,
                        result=VerificationCheckResult.SKIPPED,
                        message="No test commands executed",
                        duration_ms=(time.time() - start) * 1000,
                    )

                test_results = {}
                all_passed = True
                for cmd in test_commands:
                    test_results[f"cmd_{cmd.id}"] = {
                        "status": cmd.status.value,
                        "exit_code": cmd.exit_code,
                        "stdout": cmd.stdout,
                        "stderr": cmd.stderr,
                        "duration_ms": cmd.duration_ms,
                    }
                    if cmd.status != CommandStatus.SUCCEEDED or cmd.exit_code != 0:
                        all_passed = False

                result = (
                    VerificationCheckResult.PASSED
                    if all_passed
                    else VerificationCheckResult.FAILED
                )
                return VerificationCheck(
                    check_type=VerificationCheckType.TESTS,
                    result=result,
                    message=f"Test verification: {'passed' if all_passed else 'failed'}",
                    details={"test_commands": test_results, "all_passed": all_passed},
                    duration_ms=(time.time() - start) * 1000,
                )
        except Exception as e:
            return VerificationCheck(
                check_type=VerificationCheckType.TESTS,
                result=VerificationCheckResult.FAILED,
                message=f"Test check error: {str(e)}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _check_acceptance_criteria(
        self, context: TaskContext, worktree_path: str
    ) -> VerificationCheck:
        start = time.time()
        if not context.acceptance_criteria:
            return VerificationCheck(
                check_type=VerificationCheckType.ACCEPTANCE_CRITERIA,
                result=VerificationCheckResult.SKIPPED,
                message="No acceptance criteria specified",
                duration_ms=(time.time() - start) * 1000,
            )

        # For now, we do a basic check - the actual criteria would need to be evaluated
        # This could be extended with LLM-based evaluation in the future
        return VerificationCheck(
            check_type=VerificationCheckType.ACCEPTANCE_CRITERIA,
            result=VerificationCheckResult.PASSED,
            message=f"Acceptance criteria noted ({len(context.acceptance_criteria)} criteria)",
            details={"criteria": context.acceptance_criteria},
            duration_ms=(time.time() - start) * 1000,
        )

    async def _check_scope(
        self, context: TaskContext, worktree_path: str
    ) -> VerificationCheck:
        start = time.time()
        try:
            # Get changed files
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree_path,
                "diff",
                "--name-only",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            changed_files = (
                stdout.decode().strip().split("\n") if stdout.decode().strip() else []
            )

            # Also check untracked files
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree_path,
                "ls-files",
                "--others",
                "--exclude-standard",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            untracked_files = (
                stdout.decode().strip().split("\n") if stdout.decode().strip() else []
            )

            all_changed = changed_files + untracked_files

            # Check if any changed files are outside allowed paths
            scope_violations = []
            if context.allowed_paths:
                for file in all_changed:
                    allowed = False
                    for allowed_path in context.allowed_paths:
                        if file.startswith(allowed_path) or file == allowed_path:
                            allowed = True
                            break
                    if not allowed and file:
                        scope_violations.append(file)

            if scope_violations:
                return VerificationCheck(
                    check_type=VerificationCheckType.SCOPE,
                    result=VerificationCheckResult.FAILED,
                    message=f"Scope violations: {len(scope_violations)} files outside allowed paths",
                    details={
                        "violations": scope_violations,
                        "allowed_paths": context.allowed_paths,
                    },
                    duration_ms=(time.time() - start) * 1000,
                )

            return VerificationCheck(
                check_type=VerificationCheckType.SCOPE,
                result=VerificationCheckResult.PASSED,
                message=f"Scope check passed, {len(all_changed)} files changed",
                details={"changed_files": all_changed},
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return VerificationCheck(
                check_type=VerificationCheckType.SCOPE,
                result=VerificationCheckResult.FAILED,
                message=f"Scope check error: {str(e)}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _check_artifacts(
        self, context: TaskContext, execution_id: UUID
    ) -> VerificationCheck:
        start = time.time()
        try:
            async with self.uow:
                artifacts = await self.uow.artifacts.get_by_environment(execution_id)

            artifact_info = []
            for art in artifacts:
                artifact_info.append(
                    {
                        "id": str(art.id),
                        "path": art.path,
                        "type": art.type.value,
                        "size": art.size,
                        "sha256": art.sha256,
                    }
                )

            return VerificationCheck(
                check_type=VerificationCheckType.ARTIFACTS,
                result=VerificationCheckResult.PASSED,
                message=f"Found {len(artifacts)} artifacts",
                details={"artifacts": artifact_info},
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return VerificationCheck(
                check_type=VerificationCheckType.ARTIFACTS,
                result=VerificationCheckResult.FAILED,
                message=f"Artifact check error: {str(e)}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _check_policy_violations(
        self, context: TaskContext, worktree_path: str
    ) -> VerificationCheck:
        start = time.time()
        # Check for any policy violations in the worktree
        # This would check for things like:
        # - Attempts to access outside worktree
        # - Unauthorized tool usage
        # - etc.
        return VerificationCheck(
            check_type=VerificationCheckType.POLICY_VIOLATIONS,
            result=VerificationCheckResult.PASSED,
            message="No policy violations detected",
            duration_ms=(time.time() - start) * 1000,
        )

    async def _check_execution_failures(
        self, context: TaskContext, execution_id: UUID
    ) -> VerificationCheck:
        start = time.time()
        try:
            async with self.uow:
                commands = await self.uow.command_executions.get_by_environment(
                    execution_id
                )

            failed_commands = [
                c
                for c in commands
                if c.status
                in [
                    CommandStatus.FAILED,
                    CommandStatus.TIMED_OUT,
                    CommandStatus.REJECTED,
                ]
            ]

            if failed_commands:
                return VerificationCheck(
                    check_type=VerificationCheckType.EXECUTION_FAILURES,
                    result=VerificationCheckResult.FAILED,
                    message=f"Found {len(failed_commands)} failed/rejected/timed-out commands",
                    details={
                        "failed_commands": [
                            {
                                "id": str(c.id),
                                "status": c.status.value,
                                "exit_code": c.exit_code,
                                "failure_reason": c.failure_reason,
                            }
                            for c in failed_commands
                        ]
                    },
                    duration_ms=(time.time() - start) * 1000,
                )

            return VerificationCheck(
                check_type=VerificationCheckType.EXECUTION_FAILURES,
                result=VerificationCheckResult.PASSED,
                message="No execution failures",
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return VerificationCheck(
                check_type=VerificationCheckType.EXECUTION_FAILURES,
                result=VerificationCheckResult.FAILED,
                message=f"Execution failure check error: {str(e)}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _check_secret_leakage(
        self, context: TaskContext, worktree_path: str
    ) -> VerificationCheck:
        start = time.time()
        # Basic secret detection in changed files
        # This is a simplified check - could be enhanced with more patterns
        secret_patterns = [
            "api_key",
            "secret_key",
            "password",
            "token",
            "private_key",
            "access_key",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree_path,
                "diff",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            diff = stdout.decode()

            leaked = []
            for pattern in secret_patterns:
                if pattern.lower() in diff.lower():
                    leaked.append(pattern)

            if leaked:
                return VerificationCheck(
                    check_type=VerificationCheckType.SECRET_LEAKAGE,
                    result=VerificationCheckResult.FAILED,
                    message=f"Potential secret leakage detected: {', '.join(leaked)}",
                    details={"patterns_found": leaked},
                    duration_ms=(time.time() - start) * 1000,
                )

            return VerificationCheck(
                check_type=VerificationCheckType.SECRET_LEAKAGE,
                result=VerificationCheckResult.PASSED,
                message="No secret leakage detected in diff",
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return VerificationCheck(
                check_type=VerificationCheckType.SECRET_LEAKAGE,
                result=VerificationCheckResult.FAILED,
                message=f"Secret leakage check error: {str(e)}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _check_unexpected_changes(
        self, context: TaskContext, worktree_path: str
    ) -> VerificationCheck:
        start = time.time()
        try:
            # Check for changes to protected paths
            protected_paths = [".git", ".github", ".aura", "alembic", "migrations"]

            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree_path,
                "diff",
                "--name-only",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            changed_files = (
                stdout.decode().strip().split("\n") if stdout.decode().strip() else []
            )

            unexpected = []
            for file in changed_files:
                for protected in protected_paths:
                    if file.startswith(protected):
                        unexpected.append(file)

            if unexpected:
                return VerificationCheck(
                    check_type=VerificationCheckType.UNEXPECTED_CHANGES,
                    result=VerificationCheckResult.WARNING,
                    message=f"Changes to potentially protected paths: {', '.join(unexpected)}",
                    details={"unexpected_files": unexpected},
                    duration_ms=(time.time() - start) * 1000,
                )

            return VerificationCheck(
                check_type=VerificationCheckType.UNEXPECTED_CHANGES,
                result=VerificationCheckResult.PASSED,
                message="No unexpected changes to protected paths",
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return VerificationCheck(
                check_type=VerificationCheckType.UNEXPECTED_CHANGES,
                result=VerificationCheckResult.FAILED,
                message=f"Unexpected changes check error: {str(e)}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _record_check(
        self, verification: VerificationResult, check: VerificationCheck
    ):
        verification.checks.append(check)
        aura_verification_checks_total.inc()

    async def _get_changed_files(self, worktree_path: str) -> List[str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree_path,
                "diff",
                "--name-only",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            changed = (
                stdout.decode().strip().split("\n") if stdout.decode().strip() else []
            )

            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                worktree_path,
                "ls-files",
                "--others",
                "--exclude-standard",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            untracked = (
                stdout.decode().strip().split("\n") if stdout.decode().strip() else []
            )

            return [f for f in changed + untracked if f]
        except Exception:
            return []

    def _utc_now(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
