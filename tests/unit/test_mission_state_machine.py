import pytest

from core.domain.missions.entities import Mission
from core.domain.missions.enums import MissionStatus
from core.domain.missions.state_machine import (
    InvalidMissionTransition,
    MissionStateMachine,
)


def test_valid_state_transition():
    mission = Mission(
        title="Test", description="Desc", repository_id="repo1", source="test"
    )
    assert mission.status == MissionStatus.CREATED

    updated_mission = MissionStateMachine.transition(mission, MissionStatus.PLANNING)
    assert updated_mission.status == MissionStatus.PLANNING


def test_invalid_state_transition():
    mission = Mission(
        title="Test", description="Desc", repository_id="repo1", source="test"
    )

    with pytest.raises(InvalidMissionTransition):
        MissionStateMachine.transition(mission, MissionStatus.EXECUTING)


def test_terminal_states():
    terminal_states = [
        MissionStatus.MERGED,
        MissionStatus.CANCELLED,
        MissionStatus.ABORTED,
        MissionStatus.FAILED_PERMANENTLY,
    ]
    for status in terminal_states:
        mission = Mission(
            title="Test",
            description="Desc",
            repository_id="repo",
            source="src",
            status=status,
        )
        with pytest.raises(InvalidMissionTransition):
            MissionStateMachine.transition(mission, MissionStatus.CREATED)


def test_cancellation():
    mission = Mission(
        title="Test",
        description="Desc",
        repository_id="repo",
        source="src",
        status=MissionStatus.EXECUTING,
    )
    updated = MissionStateMachine.transition(mission, MissionStatus.CANCELLED)
    assert updated.status == MissionStatus.CANCELLED


def test_recovery_flow():
    mission = Mission(
        title="Test",
        description="Desc",
        repository_id="repo",
        source="src",
        status=MissionStatus.EXECUTING,
    )
    mission = MissionStateMachine.transition(mission, MissionStatus.RECOVERING)
    assert mission.status == MissionStatus.RECOVERING
    mission = MissionStateMachine.transition(mission, MissionStatus.EXECUTING)
    assert mission.status == MissionStatus.EXECUTING


def test_repeated_transition():
    mission = Mission(
        title="Test",
        description="Desc",
        repository_id="repo",
        source="src",
        status=MissionStatus.EXECUTING,
    )
    with pytest.raises(InvalidMissionTransition):
        MissionStateMachine.transition(mission, MissionStatus.EXECUTING)


def test_malformed_state():
    mission = Mission(
        title="Test", description="Desc", repository_id="repo", source="src"
    )
    mission.status = "FAKE_STATE"  # Bypass pydantic validation for test
    with pytest.raises(KeyError):  # Will fail dictionary lookup
        MissionStateMachine.transition(mission, MissionStatus.EXECUTING)
