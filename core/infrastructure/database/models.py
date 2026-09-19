import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlalchemy.types import Uuid as UUID

from .connection import Base


def utc_now():
    return datetime.now(timezone.utc)


class MissionModel(Base):
    __tablename__ = "missions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    repository_id = Column(String(255), nullable=False)
    source = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)
    risk_level = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AgentModel(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    agent_type = Column(String(50), nullable=False)
    version = Column(String(50), nullable=False)
    capabilities = Column(JSON, nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class PolicyModel(Base):
    __tablename__ = "policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    allowed_capabilities = Column(JSON, nullable=False)
    denied_capabilities = Column(JSON, nullable=False)
    status = Column(String(50), nullable=False)


class EventModel(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(255), nullable=False)
    mission_id = Column(UUID(as_uuid=True), nullable=False)
    task_id = Column(UUID(as_uuid=True), nullable=True)
    agent_id = Column(UUID(as_uuid=True), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now)
    metadata_ = Column("metadata", JSON, nullable=False)


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)
    priority = Column(sa.Integer, default=0)
    assigned_agent_id = Column(UUID(as_uuid=True), nullable=True)
    attempt_count = Column(sa.Integer, default=0)
    max_attempts = Column(sa.Integer, default=3)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class TaskDependencyModel(Base):
    __tablename__ = "task_dependencies"

    task_id = Column(UUID(as_uuid=True), primary_key=True)
    depends_on_task_id = Column(UUID(as_uuid=True), primary_key=True)


class TaskExecutionModel(Base):
    __tablename__ = "task_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), nullable=True)
    attempt_number = Column(sa.Integer, nullable=False)
    status = Column(String(50), nullable=False)
    started_at = Column(DateTime(timezone=True), default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    result_metadata_ = Column("result_metadata", JSON, nullable=False)


class ApprovalModel(Base):
    __tablename__ = "approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    approval_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    requested_at = Column(DateTime(timezone=True), default=utc_now)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(255), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=False)


from sqlalchemy import JSON, ForeignKey


class PlanModel(Base):
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=False)
    planner_agent_id = Column(String, nullable=False)
    planner_version = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    status = Column(String, nullable=False)
    output_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class ExecutionEnvironmentModel(Base):
    __tablename__ = "execution_environments"
    id = Column(UUID(as_uuid=True), primary_key=True)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    execution_id = Column(
        UUID(as_uuid=True), ForeignKey("task_executions.id"), nullable=False
    )
    status = Column(String, nullable=False)
    worktree_path = Column(String, nullable=True)
    base_commit_sha = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(String, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)


class CommandExecutionModel(Base):
    __tablename__ = "command_executions"
    id = Column(UUID(as_uuid=True), primary_key=True)
    environment_id = Column(
        UUID(as_uuid=True), ForeignKey("execution_environments.id"), nullable=False
    )
    status = Column(String, nullable=False)
    exit_code = Column(sa.Integer, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    duration_ms = Column(sa.Float, nullable=False)
    timed_out = Column(sa.Boolean, nullable=False)
    output_truncated = Column(sa.Boolean, nullable=False)
    failure_reason = Column(String, nullable=True)


class ArtifactModel(Base):
    __tablename__ = "artifacts"
    id = Column(UUID(as_uuid=True), primary_key=True)
    environment_id = Column(
        UUID(as_uuid=True), ForeignKey("execution_environments.id"), nullable=False
    )
    path = Column(String, nullable=False)
    type = Column(String, nullable=False)
    size = Column(sa.Integer, nullable=False)
    sha256 = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    task_execution_id = Column(
        UUID(as_uuid=True), ForeignKey("task_executions.id"), nullable=False
    )
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    status = Column(String(50), nullable=False)
    iteration_count = Column(sa.Integer, default=0)
    tool_call_count = Column(sa.Integer, default=0)
    max_iterations = Column(sa.Integer, default=50)
    max_tool_calls = Column(sa.Integer, default=100)
    max_runtime_seconds = Column(sa.Integer, default=1800)
    max_failed_actions = Column(sa.Integer, default=5)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)
    final_result = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ToolCallModel(Base):
    __tablename__ = "tool_calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_run_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False
    )
    tool_name = Column(String(255), nullable=False)
    arguments = Column(JSON, nullable=False)
    policy_decision = Column(String(50), nullable=False)
    policy_reason = Column(Text, nullable=True)
    status = Column(String(50), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    result_summary = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class VerificationResultModel(Base):
    __tablename__ = "verification_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_run_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False
    )
    task_execution_id = Column(
        UUID(as_uuid=True), ForeignKey("task_executions.id"), nullable=False
    )
    status = Column(String(50), nullable=False)
    success = Column(sa.Boolean, nullable=False)
    checks = Column(JSON, nullable=False)
    failed_checks = Column(JSON, nullable=False)
    warnings = Column(JSON, nullable=False)
    changed_files = Column(JSON, nullable=False)
    test_results = Column(JSON, nullable=False)
    diff_summary = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
