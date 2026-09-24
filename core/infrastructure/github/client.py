import base64
import hashlib
import hmac
import os
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx

from core.infrastructure.github.interfaces import (
    GitHubCheckRun,
    GitHubClient,
    GitHubPullRequest,
    GitHubRepository,
    GitHubReview,
    GitHubWebhookEvent,
)


class GitHubHttpClient(GitHubClient):
    """HTTP client for GitHub REST API."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        timeout: float = 30.0,
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "AURA-Automation/1.0",
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> dict:
        client = await self._get_client()
        url = path if path.startswith("/") else f"/{path}"
        response = await client.request(method, url, params=params, json=json)
        response.raise_for_status()
        return response.json()

    async def get_rate_limit(self) -> dict:
        response = await self.request("GET", "/rate_limit")
        return response

    async def get_repository(self, owner: str, repo: str) -> Optional[GitHubRepository]:
        try:
            data = await self.request("GET", f"/repos/{owner}/{repo}")
            return GitHubRepository(
                id=data["id"],
                name=data["name"],
                full_name=data["full_name"],
                owner_login=data["owner"]["login"],
                default_branch=data["default_branch"],
                clone_url=data["clone_url"],
                ssh_url=data["ssh_url"],
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

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
        data = await self.request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
                "draft": draft,
            },
        )
        return self._parse_pull_request(data)

    async def update_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
    ) -> GitHubPullRequest:
        payload = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        data = await self.request(
            "PATCH", f"/repos/{owner}/{repo}/pulls/{pr_number}", json=payload
        )
        return self._parse_pull_request(data)

    async def get_pull_request(
        self, owner: str, repo: str, pr_number: int
    ) -> Optional[GitHubPullRequest]:
        try:
            data = await self.request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")
            return self._parse_pull_request(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        head_branch: Optional[str] = None,
        base_branch: Optional[str] = None,
    ) -> list[GitHubPullRequest]:
        params = {"state": state, "per_page": 100}
        if head_branch:
            params["head"] = f"{owner}:{head_branch}"
        if base_branch:
            params["base"] = base_branch
        data = await self.request("GET", f"/repos/{owner}/{repo}/pulls", params=params)
        return [self._parse_pull_request(pr) for pr in data]

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_method: str = "merge",
    ) -> bool:
        try:
            await self.request(
                "PUT",
                f"/repos/{owner}/{repo}/pulls/{pr_number}/merge",
                json={
                    "commit_title": commit_title,
                    "commit_message": commit_message,
                    "merge_method": merge_method,
                },
            )
            return True
        except httpx.HTTPStatusError:
            return False

    async def get_pull_request_reviews(
        self, owner: str, repo: str, pr_number: int
    ) -> list[GitHubReview]:
        data = await self.request(
            "GET", f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        )
        return [
            GitHubReview(
                id=r["id"],
                user_login=r["user"]["login"],
                state=r["state"],
                body=r.get("body"),
                submitted_at=datetime.fromisoformat(
                    r["submitted_at"].replace("Z", "+00:00")
                ),
                commit_sha=r.get("commit_id", ""),
            )
            for r in data
        ]

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
        payload: dict = {
            "name": name,
            "head_sha": head_sha,
            "status": status,
        }
        if conclusion:
            payload["conclusion"] = conclusion
        if output_title:
            output_dict: dict = {"title": output_title}
            if output_summary:
                output_dict["summary"] = output_summary
            if output_text:
                output_dict["text"] = output_text
            payload["output"] = output_dict
        if details_url:
            payload["details_url"] = details_url
        if external_id:
            payload["external_id"] = external_id

        data = await self.request(
            "POST", f"/repos/{owner}/{repo}/check-runs", json=payload
        )
        return self._parse_check_run(data)

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
        payload: dict = {}
        if status:
            payload["status"] = status
        if conclusion:
            payload["conclusion"] = conclusion
        if output_title:
            output_dict: dict = {"title": output_title}
            if output_summary:
                output_dict["summary"] = output_summary
            if output_text:
                output_dict["text"] = output_text
            payload["output"] = output_dict

        data = await self.request(
            "PATCH",
            f"/repos/{owner}/{repo}/check-runs/{check_run_id}",
            json=payload,
        )
        return self._parse_check_run(data)

    async def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").encode()
        if not secret:
            return False
        expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        expected_signature = f"sha256={expected}"
        return hmac.compare_digest(expected_signature, signature)

    async def parse_webhook_event(
        self, payload: bytes, signature: str, event_type: str
    ) -> Optional[GitHubWebhookEvent]:
        valid = await self.verify_webhook_signature(payload, signature)
        if not valid:
            return None
        import json

        return GitHubWebhookEvent(
            event_type=event_type,
            delivery_id="",  # Would come from headers
            payload=json.loads(payload),
            signature=signature,
            timestamp=datetime.utcnow(),
        )

    def _parse_pull_request(self, data: dict) -> GitHubPullRequest:
        return GitHubPullRequest(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            source_branch=data["head"]["ref"],
            target_branch=data["base"]["ref"],
            source_commit_sha=data["head"]["sha"],
            merge_commit_sha=data.get("merge_commit_sha"),
            author_login=data["user"]["login"],
            created_at=datetime.fromisoformat(
                data["created_at"].replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"].replace("Z", "+00:00")
            ),
            merged_at=(
                datetime.fromisoformat(data["merged_at"].replace("Z", "+00:00"))
                if data.get("merged_at")
                else None
            ),
            merged_by=(
                data.get("merged_by", {}).get("login")
                if data.get("merged_by")
                else None
            ),
            url=data["html_url"],
            diff_url=data["diff_url"],
            commits_url=data["commits_url"],
            reviews_url=data["reviews_url"],
            draft=data.get("draft", False),
        )

    def _parse_check_run(self, data: dict) -> GitHubCheckRun:
        return GitHubCheckRun(
            name=data["name"],
            status=data["status"],
            conclusion=data.get("conclusion"),
            output_title=data.get("output", {}).get("title"),
            output_summary=data.get("output", {}).get("summary"),
            output_text=data.get("output", {}).get("text"),
            details_url=data.get("details_url"),
            external_id=data.get("external_id"),
            started_at=datetime.fromisoformat(
                data["started_at"].replace("Z", "+00:00")
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
                if data.get("completed_at")
                else None
            ),
        )
