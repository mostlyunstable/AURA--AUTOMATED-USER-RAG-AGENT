import os
import shutil
from typing import List
from uuid import UUID

from core.application.interfaces import UnitOfWork
from core.domain.events.entities import Event
from core.domain.execution.enums import EnvironmentStatus

class OrphanRecoveryService:
    def __init__(self, uow: UnitOfWork, worktree_root: str = "~/.aura/worktrees"):
        self.uow = uow
        self.worktree_root = os.path.abspath(os.path.expanduser(worktree_root))

    async def recover_orphans(self) -> None:
        """Scan worktree root for directories not linked to an active environment."""
        if not os.path.exists(self.worktree_root):
            return

        async with self.uow:
            # We fetch all environments that are not destroyed to check against
            # In a real system with many, this might be batched or use a set
            pass

        # We will scan the directories.
        # Directory structure: ~/.aura/worktrees/mission_id/task_id/execution_id
        for mission_dir in os.listdir(self.worktree_root):
            mission_path = os.path.join(self.worktree_root, mission_dir)
            if not os.path.isdir(mission_path):
                continue
            for task_dir in os.listdir(mission_path):
                task_path = os.path.join(mission_path, task_dir)
                if not os.path.isdir(task_path):
                    continue
                for exec_dir in os.listdir(task_path):
                    exec_path = os.path.join(task_path, exec_dir)
                    if not os.path.isdir(exec_path):
                        continue

                    # Check ownership marker
                    marker_path = os.path.join(exec_path, ".aura-environment")
                    if not os.path.exists(marker_path):
                        # Unknown directory, DO NOT DELETE.
                        continue
                        
                    env_id_str = None
                    with open(marker_path, "r") as f:
                        content = f.read().strip()
                        if content.startswith("environment_id="):
                            env_id_str = content.split("=")[1]
                            
                    if not env_id_str:
                        continue
                        
                    try:
                        env_id = UUID(env_id_str)
                    except ValueError:
                        continue

                    # Check DB
                    async with self.uow:
                        env = await self.uow.execution_environments.get(env_id)
                        if not env:
                            # Not found in DB, orphan
                            is_orphan = True
                        elif env.status in [EnvironmentStatus.DESTROYED, EnvironmentStatus.FAILED]:
                            # Finished, but worktree wasn't cleaned properly
                            is_orphan = True
                        else:
                            is_orphan = False

                    if is_orphan:
                        # Clean it up safely
                        async with self.uow:
                            await self.uow.events.append(Event(
                                event_type="execution.environment.orphan_detected",
                                mission_id=env.mission_id if env else UUID(int=0),
                                metadata={"environment_id": env_id_str, "path": exec_path}
                            ))
                            await self.uow.commit()

                        shutil.rmtree(exec_path, ignore_errors=True)
                        
                        async with self.uow:
                            if env:
                                env.status = EnvironmentStatus.DESTROYED
                                await self.uow.execution_environments.update(env)
                            
                            await self.uow.events.append(Event(
                                event_type="execution.environment.recovered",
                                mission_id=env.mission_id if env else UUID(int=0),
                                metadata={"environment_id": env_id_str, "path": exec_path}
                            ))
                            await self.uow.commit()

