from enum import Enum

class PlanStatus(Enum):
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
