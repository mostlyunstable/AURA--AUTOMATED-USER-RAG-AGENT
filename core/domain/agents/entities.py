from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.domain.agents.enums import (
    AgentCapability,
    AgentRunStatus,
    AgentStatus,
    AgentType,
    ToolCallStatus,
)


def utc_now():
    return datetime.now(timezone.utc)


class Agent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    agent_type: AgentType
    version: str = "1.0.0"
    capabilities: List[AgentCapability] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    task_id: UUID
    task_execution_id: UUID
    agent_id: UUID
    status: AgentRunStatus = AgentRunStatus.CREATED
    iteration_count: int = 0
    tool_call_count: int = 0
    max_iterations: int = 50
    max_tool_calls: int = 100
    max_runtime_seconds: int = 1800
    max_failed_actions: int = 5
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    final_result: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ToolCall(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    agent_run_id: UUID
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    policy_decision: ToolCallStatus = ToolCallStatus.PENDING
    policy_reason: Optional[str] = None
    status: ToolCallStatus = ToolCallStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


class AgentDecision(BaseModel):
    action_type: str
    target: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    rationale: str
    expected_result: str
    confidence: Optional[float] = None
    correlation_id: Optional[str] = None
