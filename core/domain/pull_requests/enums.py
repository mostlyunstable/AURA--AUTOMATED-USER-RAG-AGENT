from enum import Enum


class PullRequestStatus(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    MERGED = "MERGED"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class PullRequestProvider(str, Enum):
    GITHUB = "GITHUB"
    GITLAB = "GITLAB"
    BITBUCKET = "BITBUCKET"
