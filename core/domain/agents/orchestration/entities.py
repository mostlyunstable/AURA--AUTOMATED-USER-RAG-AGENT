from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.domain.agents.enums import (
    AgentCapability,
    AgentTaskStatus,
    AgentType,
    AssignmentStatus,
    MessageType,
    WorkflowStatus,
)


def utc_now():
    return datetime.now(timezone.utc)


class AgentTask(BaseModel):
    """Orchestration-level task assigned to a specialized agent."""

    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    mission_id: UUID
    task_id: UUID  # Reference to the original Task
    agent_type: AgentType
    required_capabilities: List[AgentCapability] = Field(default_factory=list)
    title: str
    description: str
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    output_payload: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    max_retries: int = 3
    retry_count: int = 0
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    assigned_agent_id: Optional[UUID] = None
    agent_run_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result_metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentDependency(BaseModel):
    """Dependency between agent tasks in a workflow DAG."""

    task_id: UUID
    depends_on_task_id: UUID
    dependency_type: str = "SEQUENTIAL"  # SEQUENTIAL, PARALLEL_GROUP


class AgentMessage(BaseModel):
    """Structured message between agents in a workflow."""

    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    sender_agent_type: str
    recipient_agent_type: str
    message_type: MessageType
    correlation_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class AgentResult(BaseModel):
    """Result from a specialized agent execution."""

    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    agent_type: str
    success: bool
    output_payload: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    artifacts: List[str] = Field(default_factory=list)
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    tokens_used: int = 0
    duration_ms: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class AgentWorkflow(BaseModel):
    """A multi-agent workflow orchestrating multiple agent tasks."""

    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    name: str
    description: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    tasks: List[UUID] = Field(default_factory=list)  # AgentTask IDs
    dependencies: List[AgentDependency] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result_metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentAssignment(BaseModel):
    """Assignment of an agent to a specific task."""

    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    agent_type: str
    agent_id: UUID
    agent_run_id: Optional[UUID] = None
    assigned_at: datetime = Field(default_factory=utc_now)
    acknowledged_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: AssignmentStatus = AssignmentStatus.ASSIGNED
