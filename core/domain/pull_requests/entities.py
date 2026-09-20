from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.domain.pull_requests.enums import PullRequestProvider, PullRequestStatus


def utc_now():
    return datetime.now(timezone.utc)


class PullRequest(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    task_execution_id: UUID
    agent_run_id: Optional[UUID] = None
    provider: PullRequestProvider = PullRequestProvider.GITHUB
    provider_pr_id: Optional[int] = None
    provider_url: Optional[str] = None
    source_branch: str
    target_branch: str = "main"
    title: str
    description: str = ""
    status: PullRequestStatus = PullRequestStatus.DRAFT
    source_commit_sha: Optional[str] = None
    merge_commit_sha: Optional[str] = None
    merged_at: Optional[datetime] = None
    merged_by: Optional[str] = None
    approval_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PullRequestEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pull_request_id: UUID
    event_type: str
    actor: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
