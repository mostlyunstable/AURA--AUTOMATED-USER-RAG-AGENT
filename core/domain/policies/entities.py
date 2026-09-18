from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from typing import List

class Policy(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    version: str = "1.0.0"
    allowed_capabilities: List[str]
    denied_capabilities: List[str]
    status: str = "active"
