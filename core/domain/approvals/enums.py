from enum import Enum


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalType(str, Enum):
    EXECUTION = "EXECUTION"
    MERGE = "MERGE"
    DEPLOY = "DEPLOY"
