from enum import Enum


class WorkerStatus(str, Enum):
    REGISTERED = "REGISTERED"
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    STOPPED = "STOPPED"
    STALE = "STALE"


class WorkerCapability(str, Enum):
    CODING = "CODING"
    TESTING = "TESTING"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    DOCUMENTATION = "DOCUMENTATION"
    RESEARCH = "RESEARCH"


class WorkerCapabilityRequirement(str, Enum):
    CODING = "CODING"
    TESTING = "TESTING"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    DOCUMENTATION = "DOCUMENTATION"
    RESEARCH = "RESEARCH"
