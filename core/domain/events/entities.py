from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any

class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    event_type: str
    mission_id: UUID
    task_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)
