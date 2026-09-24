from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class GitHubRepository:
    id: int
    name: str
    full_name: str
    owner_login: str
    default_branch: str
    clone_url: str
    ssh_url: str


@dataclass
class GitHubPullRequest:
    number: int
    title: str
    body: Optional[str]
    state: str
    source_branch: str
    target_branch: str
    source_commit_sha: str
    merge_commit_sha: Optional[str]
    author_login: str
    created_at: datetime
    updated_at: datetime
    merged_at: Optional[datetime]
    merged_by: Optional[str]
    url: str
    diff_url: str
    commits_url: str
    reviews_url: str
    draft: bool


@dataclass
class GitHubReview:
    id: int
    user_login: str
    state: str
    body: Optional[str]
    submitted_at: datetime
    commit_sha: str


@dataclass
class GitHubCheckRun:
    name: str
    status: str
    conclusion: Optional[str]
    output_title: Optional[str]
    output_summary: Optional[str]
    output_text: Optional[str]
    details_url: Optional[str]
    external_id: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


@dataclass
class GitHubWebhookEvent:
    event_type: str
    delivery_id: str
    payload: dict
    signature: str
    timestamp: datetime


class GitHubProvider(ABC):
    """Interface for GitHub operations."""

    @abstractmethod
    async def get_repository(self, owner: str, repo: str) -> Optional[GitHubRepository]:
        """Get repository information."""
        pass

    @abstractmethod
    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        draft: bool = False,
    ) -> GitHubPullRequest:
        """Create a new pull request."""
        pass

    @abstractmethod
    async def update_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
    ) -> GitHubPullRequest:
        """Update an existing pull request."""
        pass

    @abstractmethod
    async def get_pull_request(
        self, owner: str, repo: str, pr_number: int
    ) -> Optional[GitHubPullRequest]:
        """Get pull request by number."""
        pass

    @abstractmethod
    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        head_branch: Optional[str] = None,
        base_branch: Optional[str] = None,
    ) -> list[GitHubPullRequest]:
        """List pull requests."""
        pass

    @abstractmethod
    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_method: str = "merge",
    ) -> bool:
        """Merge a pull request."""
        pass

    @abstractmethod
    async def get_pull_request_reviews(
        self, owner: str, repo: str, pr_number: int
    ) -> list[GitHubReview]:
        """Get reviews for a pull request."""
        pass

    @abstractmethod
    async def create_check_run(
        self,
        owner: str,
        repo: str,
        name: str,
        head_sha: str,
        status: str = "in_progress",
        conclusion: Optional[str] = None,
        output_title: Optional[str] = None,
        output_summary: Optional[str] = None,
        output_text: Optional[str] = None,
        details_url: Optional[str] = None,
        external_id: Optional[str] = None,
    ) -> GitHubCheckRun:
        """Create a check run."""
        pass

    @abstractmethod
    async def update_check_run(
        self,
        owner: str,
        repo: str,
        check_run_id: int,
        status: Optional[str] = None,
        conclusion: Optional[str] = None,
        output_title: Optional[str] = None,
        output_summary: Optional[str] = None,
        output_text: Optional[str] = None,
    ) -> GitHubCheckRun:
        """Update a check run."""
        pass

    @abstractmethod
    async def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature."""
        pass

    @abstractmethod
    async def parse_webhook_event(
        self, payload: bytes, signature: str, event_type: str
    ) -> Optional[GitHubWebhookEvent]:
        """Parse and verify webhook event."""
        pass


class GitHubClient(ABC):
    """Low-level GitHub API client."""

    @abstractmethod
    async def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> dict:
        """Make an HTTP request to GitHub API."""
        pass

    @abstractmethod
    async def get_rate_limit(self) -> dict:
        """Get current rate limit status."""
        pass
