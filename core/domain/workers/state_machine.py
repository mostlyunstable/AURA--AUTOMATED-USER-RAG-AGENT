from typing import Set

from core.domain.workers.entities import Worker
from core.domain.workers.enums import WorkerStatus


class InvalidWorkerTransition(Exception):
    pass


class WorkerStateMachine:
    VALID_TRANSITIONS = {
        WorkerStatus.REGISTERED: {WorkerStatus.AVAILABLE, WorkerStatus.STOPPED},
        WorkerStatus.AVAILABLE: {
            WorkerStatus.BUSY,
            WorkerStatus.DRAINING,
            WorkerStatus.STOPPED,
            WorkerStatus.STALE,
        },
        WorkerStatus.BUSY: {
            WorkerStatus.AVAILABLE,
            WorkerStatus.DRAINING,
            WorkerStatus.STOPPED,
            WorkerStatus.STALE,
        },
        WorkerStatus.DRAINING: {WorkerStatus.STOPPED, WorkerStatus.STALE},
        WorkerStatus.STOPPED: {WorkerStatus.REGISTERED},
        WorkerStatus.STALE: {WorkerStatus.STOPPED},
    }

    @classmethod
    def can_transition(cls, from_status: WorkerStatus, to_status: WorkerStatus) -> bool:
        return to_status in cls.VALID_TRANSITIONS.get(from_status, set())

    @classmethod
    def transition(cls, worker: "Worker", new_status: WorkerStatus) -> "Worker":
        if not cls.can_transition(worker.status, new_status):
            raise InvalidWorkerTransition(
                f"Cannot transition worker from {worker.status.value} to {new_status.value}"
            )
        worker.status = new_status
        worker.updated_at = utc_now()
        return worker


def utc_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
