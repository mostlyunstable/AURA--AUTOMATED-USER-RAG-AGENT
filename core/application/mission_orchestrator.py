from typing import List, Optional
from uuid import UUID

from core.application.interfaces import UnitOfWork
from core.domain.dag.validator import DAGValidator
from core.domain.events.entities import Event
from core.domain.tasks.entities import Task, TaskDependency
from core.domain.tasks.enums import TaskStatus


class MissionOrchestrator:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def add_task(self, task: Task) -> None:
        async with self.uow:
            await self.uow.tasks.create(task)
            event = Event(
                event_type="task.created",
                mission_id=task.mission_id,
                task_id=task.id,
                metadata={"title": task.title},
            )
            await self.uow.events.append(event)
            await self.uow.commit()

    async def add_dependency(
        self, mission_id: UUID, dependency: TaskDependency
    ) -> None:
        async with self.uow:
            t1 = await self.uow.tasks.get(dependency.task_id)
            t2 = await self.uow.tasks.get(dependency.depends_on_task_id)
            if not t1 or not t2:
                raise ValueError("Both tasks must exist")
            if t1.mission_id != mission_id or t2.mission_id != mission_id:
                raise ValueError("Tasks must belong to the mission")

            existing_deps = (
                await self.uow.task_dependencies.get_dependencies_for_mission(
                    mission_id
                )
            )
            DAGValidator.validate_new_dependency(dependency, existing_deps)

            await self.uow.task_dependencies.add(dependency)
            await self.uow.commit()

    async def calculate_progress(self, mission_id: UUID) -> float:
        async with self.uow:
            tasks = await self.uow.tasks.get_by_mission(mission_id)
            if not tasks:
                return 0.0
            succeeded = sum(1 for t in tasks if t.status == TaskStatus.SUCCEEDED)
            return (succeeded / len(tasks)) * 100.0
