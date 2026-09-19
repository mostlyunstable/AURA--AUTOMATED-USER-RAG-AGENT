from .entities import Task
from .enums import TaskStatus


class InvalidTaskTransition(Exception):
    pass


class TaskStateMachine:
    VALID_TRANSITIONS = {
        TaskStatus.PENDING: [TaskStatus.READY, TaskStatus.CANCELLED],
        TaskStatus.READY: [TaskStatus.QUEUED, TaskStatus.BLOCKED, TaskStatus.CANCELLED],
        TaskStatus.QUEUED: [TaskStatus.RUNNING, TaskStatus.CANCELLED],
        TaskStatus.RUNNING: [TaskStatus.SUCCEEDED, TaskStatus.FAILED],
        TaskStatus.FAILED: [TaskStatus.RETRYING],
        TaskStatus.RETRYING: [TaskStatus.QUEUED],
        TaskStatus.BLOCKED: [TaskStatus.READY],
        TaskStatus.SUCCEEDED: [],
        TaskStatus.CANCELLED: [],
    }

    @classmethod
    def transition(cls, task: Task, new_status: TaskStatus) -> Task:
        if new_status not in cls.VALID_TRANSITIONS[task.status]:
            raise InvalidTaskTransition(
                f"Cannot transition Task from {task.status} to {new_status}"
            )
        task.status = new_status
        return task
