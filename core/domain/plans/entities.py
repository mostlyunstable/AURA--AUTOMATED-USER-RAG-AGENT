from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.domain.plans.enums import PlanStatus
from core.domain.tasks.enums import TaskType


class PlanTask(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1, max_length=2000)
    task_type: TaskType
    priority: int = Field(default=0)
    dependencies: List[str] = Field(default_factory=list)  # string titles or IDs
    required_capabilities: List[str] = Field(default_factory=list)
    estimated_complexity: str = Field(default="medium")


class PlanRisk(BaseModel):
    description: str
    mitigation: str


class PlanAssumption(BaseModel):
    description: str


class ValidationStrategy(BaseModel):
    approach: str
    tests_required: bool


class PlannerOutput(BaseModel):
    summary: str
    assumptions: List[PlanAssumption] = Field(default_factory=list, max_length=20)
    risks: List[PlanRisk] = Field(default_factory=list, max_length=20)
    tasks: List[PlanTask] = Field(default_factory=list, max_length=50)
    validation_strategy: ValidationStrategy


class EngineeringPlan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    planner_agent_id: str
    planner_version: str
    provider: str
    model: str
    output: PlannerOutput
    status: PlanStatus = PlanStatus.GENERATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
