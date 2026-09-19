from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .enums import MissionStatus


class Mission(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    repository_id: str
    source: str
    status: MissionStatus = MissionStatus.CREATED
    risk_level: str = "medium"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
