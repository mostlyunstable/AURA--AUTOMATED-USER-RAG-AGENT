from typing import List
from uuid import UUID

from core.application.interfaces import UnitOfWork
from core.domain.events.entities import Event
from core.domain.missions.enums import MissionStatus
from core.domain.tasks.entities import Task
from core.domain.tasks.enums import TaskStatus
from core.domain.tasks.state_machine import TaskStateMachine


class TaskScheduler:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def schedule_ready_tasks(self, mission_id: UUID) -> List[Task]:
        ready_tasks = []
        async with self.uow:
            mission = await self.uow.missions.get(mission_id)
            if not mission or mission.status != MissionStatus.EXECUTING:
                return []

            tasks = await self.uow.tasks.get_by_mission(mission_id)
            deps = await self.uow.task_dependencies.get_dependencies_for_mission(
                mission_id
            )

            task_dict = {t.id: t for t in tasks}

            for task in tasks:
                if task.status != TaskStatus.PENDING:
                    continue

                # Check dependencies
                task_deps = [d for d in deps if d.task_id == task.id]
                all_succeeded = True
                for d in task_deps:
                    parent = task_dict.get(d.depends_on_task_id)
                    if not parent or parent.status != TaskStatus.SUCCEEDED:
                        all_succeeded = False
                        break

                if all_succeeded:
                    TaskStateMachine.transition(task, TaskStatus.READY)
                    await self.uow.tasks.update(task)

                    event = Event(
                        event_type="task.ready",
                        mission_id=mission_id,
                        task_id=task.id,
                        metadata={},
                    )
                    await self.uow.events.append(event)

                    TaskStateMachine.transition(task, TaskStatus.QUEUED)
                    await self.uow.tasks.update(task)

                    queued_event = Event(
                        event_type="task.queued",
                        mission_id=mission_id,
                        task_id=task.id,
                        metadata={},
                    )
                    await self.uow.events.append(queued_event)
                    ready_tasks.append(task)

            if ready_tasks:
                await self.uow.commit()

        return ready_tasks
