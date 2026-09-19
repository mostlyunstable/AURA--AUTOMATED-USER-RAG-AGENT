from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .enums import ApprovalStatus, ApprovalType


def utc_now():
    return datetime.now(timezone.utc)


class Approval(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    approval_type: ApprovalType
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=utc_now)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
