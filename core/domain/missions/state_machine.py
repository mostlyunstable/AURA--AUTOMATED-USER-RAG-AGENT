from .entities import Mission
from .enums import MissionStatus

class InvalidMissionTransition(Exception):
    pass

class MissionStateMachine:
    VALID_TRANSITIONS = {
        MissionStatus.CREATED: [MissionStatus.PLANNING, MissionStatus.CANCELLED],
        MissionStatus.PLANNING: [MissionStatus.PLANNED, MissionStatus.FAILED_PERMANENTLY, MissionStatus.CANCELLED],
        MissionStatus.PLANNED: [MissionStatus.PLANNING, MissionStatus.APPROVED_FOR_EXECUTION, MissionStatus.CANCELLED],
        MissionStatus.APPROVED_FOR_EXECUTION: [MissionStatus.EXECUTING, MissionStatus.CANCELLED],
        MissionStatus.EXECUTING: [MissionStatus.VERIFYING, MissionStatus.RECOVERING, MissionStatus.CANCELLED, MissionStatus.BLOCKED, MissionStatus.FAILED_PERMANENTLY],
        MissionStatus.VERIFYING: [MissionStatus.VERIFIED, MissionStatus.RECOVERING, MissionStatus.FAILED_PERMANENTLY],
        MissionStatus.RECOVERING: [MissionStatus.EXECUTING, MissionStatus.FAILED_PERMANENTLY],
        MissionStatus.VERIFIED: [MissionStatus.PR_READY],
        MissionStatus.PR_READY: [MissionStatus.AWAITING_HUMAN_APPROVAL],
        MissionStatus.AWAITING_HUMAN_APPROVAL: [MissionStatus.MERGED, MissionStatus.CANCELLED],
        MissionStatus.MERGED: [],
        MissionStatus.CANCELLED: [],
        MissionStatus.ABORTED: [],
        MissionStatus.BLOCKED: [MissionStatus.PLANNING, MissionStatus.EXECUTING, MissionStatus.CANCELLED],
        MissionStatus.FAILED_PERMANENTLY: []
    }

    @classmethod
    def transition(cls, mission: Mission, new_status: MissionStatus) -> Mission:
        if new_status not in cls.VALID_TRANSITIONS[mission.status]:
            raise InvalidMissionTransition(f"Cannot transition from {mission.status} to {new_status}")
        mission.status = new_status
        return mission
