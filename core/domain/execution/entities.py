from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from uuid import UUID, uuid4
from datetime import datetime, timezone
from core.domain.execution.enums import EnvironmentStatus, CommandStatus, ArtifactType

class ExecutionEnvironment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    task_id: UUID
    execution_id: UUID
    status: EnvironmentStatus = EnvironmentStatus.CREATING
    worktree_path: Optional[str] = None
    base_commit_sha: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

class ExecutionCommand(BaseModel):
    executable: str
    arguments: List[str]
    working_directory: str
    timeout_seconds: int = 300
    environment: Dict[str, str] = Field(default_factory=dict)
    stdin: Optional[str] = None

class CommandResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    environment_id: UUID
    status: CommandStatus
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    timed_out: bool = False
    output_truncated: bool = False
    failure_reason: Optional[str] = None

class Artifact(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    environment_id: UUID
    path: str
    type: ArtifactType
    size: int
    sha256: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, str] = Field(default_factory=dict)
