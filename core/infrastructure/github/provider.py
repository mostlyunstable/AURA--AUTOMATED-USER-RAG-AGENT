import os
from typing import Optional

from core.domain.pull_requests.entities import PullRequest
from core.domain.pull_requests.enums import PullRequestProvider, PullRequestStatus
from core.infrastructure.github.client import GitHubHttpClient
from core.infrastructure.github.interfaces import (
    GitHubCheckRun,
    GitHubProvider,
    GitHubPullRequest,
    GitHubRepository,
    GitHubReview,
    GitHubWebhookEvent,
)


class GitHubProviderImpl(GitHubProvider):
    """GitHub provider implementation using REST API."""

    def __init__(self):
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_APP_TOKEN")
        if not token:
            raise ValueError(
                "GITHUB_TOKEN or GITHUB_APP_TOKEN environment variable required"
            )
        self.client = GitHubHttpClient(token)

    async def close(self) -> None:
        await self.client.close()

    async def get_repository(self, owner: str, repo: str) -> Optional[GitHubRepository]:
        return await self.client.get_repository(owner, repo)

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
        return await self.client.create_pull_request(
            owner, repo, title, body, head_branch, base_branch, draft
        )

    async def update_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
    ) -> GitHubPullRequest:
        return await self.client.update_pull_request(
            owner, repo, pr_number, title, body, state
        )

    async def get_pull_request(
        self, owner: str, repo: str, pr_number: int
    ) -> Optional[GitHubPullRequest]:
        return await self.client.get_pull_request(owner, repo, pr_number)

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        head_branch: Optional[str] = None,
        base_branch: Optional[str] = None,
    ) -> list[GitHubPullRequest]:
        return await self.client.list_pull_requests(
            owner, repo, state, head_branch, base_branch
        )

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_method: str = "merge",
    ) -> bool:
        return await self.client.merge_pull_request(
            owner, repo, pr_number, commit_title, commit_message, merge_method
        )

    async def get_pull_request_reviews(
        self, owner: str, repo: str, pr_number: int
    ) -> list:
        return await self.client.get_pull_request_reviews(owner, repo, pr_number)

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
        return await self.client.create_check_run(
            owner,
            repo,
            name,
            head_sha,
            status,
            conclusion,
            output_title,
            output_summary,
            output_text,
            details_url,
            external_id,
        )

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
        return await self.client.update_check_run(
            owner,
            repo,
            check_run_id,
            status,
            conclusion,
            output_title,
            output_summary,
            output_text,
        )

    async def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        return await self.client.verify_webhook_signature(payload, signature)

    async def parse_webhook_event(
        self, payload: bytes, signature: str, event_type: str
    ) -> Optional[GitHubWebhookEvent]:
        return await self.client.parse_webhook_event(payload, signature, event_type)

    # Convenience methods for AURA domain entities

    async def create_pull_request_from_domain(
        self, pr: PullRequest, repository_owner: str, repository_name: str
    ) -> GitHubPullRequest:
        """Create a GitHub PR from a domain PullRequest entity."""
        return await self.create_pull_request(
            owner=repository_owner,
            repo=repository_name,
            title=pr.title,
            body=pr.description or "",
            head_branch=pr.source_branch,
            base_branch=pr.target_branch,
            draft=pr.status == PullRequestStatus.DRAFT,
        )

    async def update_pull_request_from_domain(
        self, pr: PullRequest, repository_owner: str, repository_name: str
    ) -> GitHubPullRequest:
        """Update GitHub PR from domain entity."""
        if pr.provider_pr_id is None:
            raise ValueError("provider_pr_id is required for update")
        state_map = {
            PullRequestStatus.OPEN: "open",
            PullRequestStatus.CLOSED: "closed",
        }
        return await self.update_pull_request(
            owner=repository_owner,
            repo=repository_name,
            pr_number=pr.provider_pr_id,
            title=pr.title,
            body=pr.description,
            state=state_map.get(pr.status),
        )

    async def sync_pull_request_status(
        self, pr: PullRequest, repository_owner: str, repository_name: str
    ) -> Optional[PullRequest]:
        """Sync PR status from GitHub to domain entity."""
        if pr.provider_pr_id is None:
            return None
        gh_pr = await self.get_pull_request(
            repository_owner, repository_name, pr.provider_pr_id
        )
        if not gh_pr:
            return None

        status_map = {
            "open": PullRequestStatus.OPEN,
            "closed": PullRequestStatus.CLOSED,
            "merged": PullRequestStatus.MERGED,
            "draft": PullRequestStatus.DRAFT,
        }

        pr.status = status_map.get(gh_pr.state, pr.status)
        pr.provider_url = gh_pr.url
        pr.source_commit_sha = gh_pr.source_commit_sha
        pr.merge_commit_sha = gh_pr.merge_commit_sha
        pr.merged_at = gh_pr.merged_at
        pr.merged_by = gh_pr.merged_by

        return pr

    async def create_verification_check_run(
        self,
        owner: str,
        repo: str,
        head_sha: str,
        name: str,
        success: bool,
        summary: str,
        details: Optional[str] = None,
    ) -> GitHubCheckRun:
        """Create a verification check run on GitHub."""
        return await self.create_check_run(
            owner=owner,
            repo=repo,
            name=f"verification/{name}",
            head_sha=head_sha,
            status="completed",
            conclusion="success" if success else "failure",
            output_title=name,
            output_summary=summary,
            output_text=details,
        )

    async def update_verification_check_run(
        self,
        owner: str,
        repo: str,
        check_run_id: int,
        in_progress: bool = True,
        success: Optional[bool] = None,
        summary: Optional[str] = None,
        details: Optional[str] = None,
    ) -> GitHubCheckRun:
        """Update a verification check run."""
        status = "in_progress" if in_progress else "completed"
        conclusion = None
        if success is not None:
            conclusion = "success" if success else "failure"

        return await self.update_check_run(
            owner="",  # Will be filled from context
            repo="",
            check_run_id=check_run_id,
            status=status,
            conclusion=conclusion,
            output_title="Verification",
            output_summary=summary,
            output_text=details,
        )
