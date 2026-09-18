from enum import Enum

class EnvironmentStatus(Enum):
    CREATING = "CREATING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CLEANING_UP = "CLEANING_UP"
    DESTROYED = "DESTROYED"

class CommandStatus(Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    REJECTED = "REJECTED"

class ArtifactType(Enum):
    PATCH = "PATCH"
    TEST_REPORT = "TEST_REPORT"
    LOG = "LOG"
    BUILD_OUTPUT = "BUILD_OUTPUT"
    DIFF = "DIFF"
    SOURCE = "SOURCE"
    OTHER = "OTHER"
