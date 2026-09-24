from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from core.domain.approvals.entities import Approval
from core.domain.approvals.enums import ApprovalStatus, ApprovalType
from core.domain.events.entities import Event
from core.domain.missions.entities import Mission
from core.domain.missions.enums import MissionStatus
from core.domain.missions.state_machine import MissionStateMachine

from .interfaces import UnitOfWork


class MissionNotFound(Exception):
    pass


class MissionService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def create_mission(
        self,
        title: str,
        description: str,
        repository_id: str,
        source: str,
        risk_level: str = "medium",
    ) -> Mission:
        mission = Mission(
            title=title,
            description=description,
            repository_id=repository_id,
            source=source,
            risk_level=risk_level,
        )
        event = Event(
            event_type="mission.created",
            mission_id=mission.id,
            metadata={"title": title, "repository_id": repository_id, "source": source},
        )
        async with self.uow:
            await self.uow.missions.create(mission)
            await self.uow.events.append(event)
            await self.uow.commit()
        return mission

    async def update_mission_status(
        self, mission_id: UUID, new_status: MissionStatus
    ) -> Mission:
        async with self.uow:
            mission = await self.uow.missions.get(mission_id)
            if not mission:
                raise MissionNotFound(f"Mission {mission_id} not found")

            updated_mission = MissionStateMachine.transition(mission, new_status)
            await self.uow.missions.update(updated_mission)

            event = Event(
                event_type="mission.state_changed",
                mission_id=updated_mission.id,
                metadata={"new_status": new_status},
            )
            await self.uow.events.append(event)
            await self.uow.commit()
            return updated_mission

    async def get_mission(self, mission_id: UUID) -> Optional[Mission]:
        async with self.uow:
            return await self.uow.missions.get(mission_id)

    async def list_missions(self) -> List[Mission]:
        async with self.uow:
            return await self.uow.missions.list_all()

    async def request_approval(
        self, mission_id: UUID, approval_type: ApprovalType
    ) -> Approval:
        async with self.uow:
            mission = await self.uow.missions.get(mission_id)
            if not mission:
                raise MissionNotFound(f"Mission {mission_id} not found")

            approval = Approval(mission_id=mission_id, approval_type=approval_type)
            await self.uow.approvals.create(approval)

            event = Event(
                event_type="mission.execution_approval_requested",
                mission_id=mission_id,
                metadata={"approval_id": str(approval.id), "type": approval_type.value},
            )
            await self.uow.events.append(event)
            await self.uow.commit()
            return approval

    async def resolve_approval(
        self, approval_id: UUID, status: ApprovalStatus, reason: str | None = None
    ) -> Approval:
        async with self.uow:
            approval = await self.uow.approvals.get(approval_id)
            if not approval:
                raise ValueError("Approval not found")

            approval.status = status
            approval.resolved_at = datetime.now(timezone.utc)
            approval.metadata["reason"] = reason
            await self.uow.approvals.update(approval)

            if approval.approval_type == ApprovalType.MERGE:
                event_type = (
                    "mission.merge_approved"
                    if status == ApprovalStatus.APPROVED
                    else "mission.merge_rejected"
                )
            else:
                event_type = (
                    "mission.execution_approved"
                    if status == ApprovalStatus.APPROVED
                    else "mission.execution_rejected"
                )
            event = Event(
                event_type=event_type,
                mission_id=approval.mission_id,
                metadata={"approval_id": str(approval.id), "status": status.value},
            )
            await self.uow.events.append(event)

            # Auto transition if approved
            if (
                status == ApprovalStatus.APPROVED
                and approval.approval_type == ApprovalType.EXECUTION
            ):
                mission = await self.uow.missions.get(approval.mission_id)
                assert mission is not None

                if mission.status == MissionStatus.PLANNED:
                    updated_mission = MissionStateMachine.transition(
                        mission, MissionStatus.APPROVED_FOR_EXECUTION
                    )
                    await self.uow.missions.update(updated_mission)
                    await self.uow.events.append(
                        Event(
                            event_type="mission.state_changed",
                            mission_id=mission.id,
                            metadata={
                                "new_status": MissionStatus.APPROVED_FOR_EXECUTION.value
                            },
                        )
                    )
            elif (
                status == ApprovalStatus.APPROVED
                and approval.approval_type == ApprovalType.MERGE
            ):
                mission = await self.uow.missions.get(approval.mission_id)
                assert mission is not None

                if mission.status == MissionStatus.AWAITING_HUMAN_APPROVAL:
                    updated_mission = MissionStateMachine.transition(
                        mission, MissionStatus.MERGED
                    )
                    await self.uow.missions.update(updated_mission)
                    await self.uow.events.append(
                        Event(
                            event_type="mission.state_changed",
                            mission_id=mission.id,
                            metadata={"new_status": MissionStatus.MERGED.value},
                        )
                    )
            elif status == ApprovalStatus.REJECTED:
                mission = await self.uow.missions.get(approval.mission_id)
                assert mission is not None

                if mission.status == MissionStatus.PLANNED:
                    updated_mission = MissionStateMachine.transition(
                        mission, MissionStatus.BLOCKED
                    )
                    await self.uow.missions.update(updated_mission)
                    await self.uow.events.append(
                        Event(
                            event_type="mission.state_changed",
                            mission_id=mission.id,
                            metadata={"new_status": MissionStatus.BLOCKED.value},
                        )
                    )

            await self.uow.commit()
            return approval
