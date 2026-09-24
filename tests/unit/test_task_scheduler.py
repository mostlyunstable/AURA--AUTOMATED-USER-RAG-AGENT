from uuid import uuid4

import pytest

from core.application.task_scheduler import TaskScheduler
from core.domain.missions.entities import Mission
from core.domain.missions.enums import MissionStatus
from core.domain.tasks.entities import Task, TaskDependency
from core.domain.tasks.enums import TaskStatus, TaskType


class MockMissionRepo:
    def __init__(self, mission):
        self.mission = mission

    async def get(self, mission_id):
        return self.mission


class MockTaskRepo:
    def __init__(self, tasks):
        self.tasks = {t.id: t for t in tasks}

    async def get_by_mission(self, mission_id):
        return [t for t in self.tasks.values() if t.mission_id == mission_id]

    async def update(self, task):
        self.tasks[task.id] = task

    async def try_transition_status(self, task_id, from_status, to_status):
        task = self.tasks.get(task_id)
        if task and task.status == from_status:
            task.status = to_status
            return task
        return None


class MockDepRepo:
    def __init__(self, deps):
        self.deps = deps

    async def get_dependencies_for_mission(self, mission_id):
        return list(self.deps)


class MockEventRepo:
    def __init__(self):
        self.events = []

    async def append(self, event):
        self.events.append(event)


class MockUOW:
    def __init__(self, mission, tasks, deps):
        self.missions = MockMissionRepo(mission)
        self.tasks = MockTaskRepo(tasks)
        self.task_dependencies = MockDepRepo(deps)
        self.events = MockEventRepo()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def commit(self):
        self.committed = True


def make_mission():
    return Mission(
        id=uuid4(),
        title="M",
        description="D",
        repository_id="repo",
        source="test",
        status=MissionStatus.EXECUTING,
    )


def make_task(mission_id, title, status=TaskStatus.PENDING):
    return Task(
        mission_id=mission_id,
        title=title,
        description="D",
        task_type=TaskType.IMPLEMENTATION,
        status=status,
    )


@pytest.mark.asyncio
async def test_failed_dependency_blocks_task():
    mission = make_mission()
    parent = make_task(mission.id, "parent", TaskStatus.FAILED)
    child = make_task(mission.id, "child", TaskStatus.PENDING)
    dep = TaskDependency(task_id=child.id, depends_on_task_id=parent.id)

    uow = MockUOW(mission, [parent, child], [dep])
    scheduler = TaskScheduler(uow)

    ready = await scheduler.schedule_ready_tasks(mission.id)

    assert ready == []
    assert uow.tasks.tasks[child.id].status == TaskStatus.BLOCKED
    assert any(e.event_type == "task.blocked" for e in uow.events.events)


@pytest.mark.asyncio
async def test_blocked_task_recovers_when_dependency_succeeds():
    mission = make_mission()
    parent = make_task(mission.id, "parent", TaskStatus.SUCCEEDED)
    child = make_task(mission.id, "child", TaskStatus.BLOCKED)
    dep = TaskDependency(task_id=child.id, depends_on_task_id=parent.id)

    uow = MockUOW(mission, [parent, child], [dep])
    scheduler = TaskScheduler(uow)

    ready = await scheduler.schedule_ready_tasks(mission.id)

    assert [t.id for t in ready] == [child.id]
    assert uow.tasks.tasks[child.id].status == TaskStatus.QUEUED


@pytest.mark.asyncio
async def test_blocked_task_stays_blocked_while_dependency_failed():
    mission = make_mission()
    parent = make_task(mission.id, "parent", TaskStatus.FAILED)
    child = make_task(mission.id, "child", TaskStatus.BLOCKED)
    dep = TaskDependency(task_id=child.id, depends_on_task_id=parent.id)

    uow = MockUOW(mission, [parent, child], [dep])
    scheduler = TaskScheduler(uow)

    ready = await scheduler.schedule_ready_tasks(mission.id)

    # No duplicate blocked event, no crash on re-marking BLOCKED.
    assert ready == []
    assert uow.tasks.tasks[child.id].status == TaskStatus.BLOCKED
    assert not [e for e in uow.events.events if e.event_type == "task.blocked"]
