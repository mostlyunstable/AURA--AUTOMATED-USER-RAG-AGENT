from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now():
    return datetime.now(timezone.utc)


class VerificationStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationCheckType(str, Enum):
    GIT_STATUS = "GIT_STATUS"
    GIT_DIFF = "GIT_DIFF"
    TESTS = "TESTS"
    ACCEPTANCE_CRITERIA = "ACCEPTANCE_CRITERIA"
    SCOPE = "SCOPE"
    ARTIFACTS = "ARTIFACTS"
    POLICY_VIOLATIONS = "POLICY_VIOLATIONS"
    EXECUTION_FAILURES = "EXECUTION_FAILURES"
    SECRET_LEAKAGE = "SECRET_LEAKAGE"
    UNEXPECTED_CHANGES = "UNEXPECTED_CHANGES"


class VerificationCheckResult(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationCheck(BaseModel):
    check_type: VerificationCheckType
    result: VerificationCheckResult
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0


class VerificationResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    agent_run_id: UUID
    task_execution_id: UUID
    status: VerificationStatus
    success: bool
    checks: List[VerificationCheck] = Field(default_factory=list)
    failed_checks: List[VerificationCheck] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    changed_files: List[str] = Field(default_factory=list)
    test_results: Dict[str, Any] = Field(default_factory=dict)
    diff_summary: Optional[str] = None
    failure_reason: Optional[str] = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class TaskContext(BaseModel):
    mission_id: UUID
    task_id: UUID
    task_execution_id: UUID
    agent_run_id: UUID
    repository_root: str
    worktree_path: str
    task_objective: str
    acceptance_criteria: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    allowed_paths: List[str] = Field(default_factory=list)
    available_tools: List[str] = Field(default_factory=list)
    available_capabilities: List[str] = Field(default_factory=list)
    max_iterations: int = 50
    max_tool_calls: int = 100
    max_runtime_seconds: int = 1800
    max_failed_actions: int = 5


class TaskResult(BaseModel):
    task_execution_id: UUID
    agent_run_id: UUID
    verification_result_id: Optional[UUID] = None
    status: str
    success: bool
    changed_files: List[str] = Field(default_factory=list)
    artifacts: List[str] = Field(default_factory=list)
    tests: Dict[str, Any] = Field(default_factory=dict)
    failure_class: Optional[str] = None
    failure_reason: Optional[str] = None
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    iteration_count: int
    tool_call_count: int
    created_at: datetime = Field(default_factory=utc_now)
