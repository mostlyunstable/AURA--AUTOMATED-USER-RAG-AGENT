from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.domain.workers.enums import WorkerCapability, WorkerStatus


def utc_now():
    return datetime.now(timezone.utc)


class Worker(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    status: WorkerStatus = WorkerStatus.REGISTERED
    capabilities: List[str] = Field(
        default_factory=list
    )  # Store as strings for flexibility
    capabilities_enum: List[WorkerCapability] = Field(default_factory=list)
    last_heartbeat_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkerHeartbeat(BaseModel):
    worker_id: UUID
    task_execution_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    lease_expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class TaskLease(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    worker_id: UUID
    task_id: UUID
    task_execution_id: UUID
    claimed_at: datetime = Field(default_factory=utc_now)
    lease_expires_at: datetime
    last_heartbeat_at: Optional[datetime] = None
    renewed_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkerRegistration(BaseModel):
    name: str
    capabilities: List[str] = Field(default_factory=list)
    capabilities_enum: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkerStatusUpdate(BaseModel):
    status: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskLeaseClaim(BaseModel):
    task_id: UUID
    task_execution_id: UUID
    worker_id: UUID
    lease_duration_seconds: int = 90  # AURA_WORKER_LEASE_TTL_SECONDS default
    capabilities_required: List[str] = Field(default_factory=list)
