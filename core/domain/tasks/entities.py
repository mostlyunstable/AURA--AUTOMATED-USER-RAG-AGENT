from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from .enums import TaskStatus, TaskType

def utc_now():
    return datetime.now(timezone.utc)

class Task(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    task_type: TaskType
    priority: int = 0
    assigned_agent_id: Optional[UUID] = None
    attempt_count: int = 0
    max_attempts: int = 3
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class TaskDependency(BaseModel):
    task_id: UUID
    depends_on_task_id: UUID

class TaskExecution(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    agent_id: Optional[UUID] = None
    attempt_number: int
    status: TaskStatus
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result_metadata: Dict[str, Any] = Field(default_factory=dict)
