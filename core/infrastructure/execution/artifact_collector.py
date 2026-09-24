import hashlib
import os
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from core.domain.execution.entities import Artifact, ExecutionEnvironment
from core.domain.execution.enums import ArtifactType
from core.infrastructure.execution.paths import resolve_within_directory
from core.infrastructure.metrics.execution import (
    aura_artifacts_created_total,
    aura_artifacts_rejected_total,
)


class ArtifactCollector:
    def __init__(
        self, worktree_root: str = "~/.aura/worktrees", max_bytes: Optional[int] = None
    ):
        self.worktree_root = os.path.abspath(os.path.expanduser(worktree_root))
        self.max_bytes = max_bytes or int(
            os.environ.get("AURA_MAX_ARTIFACT_BYTES", 10 * 1024 * 1024)
        )

    def _resolve_and_validate_path(
        self, env: ExecutionEnvironment, relative_or_absolute_path: str
    ) -> Optional[str]:
        if not env.worktree_path:
            return None
        return resolve_within_directory(env.worktree_path, relative_or_absolute_path)

    def collect(
        self, env: ExecutionEnvironment, file_path: str, artifact_type: ArtifactType
    ) -> Optional[Artifact]:
        real_path = self._resolve_and_validate_path(env, file_path)

        if (
            not real_path
            or not os.path.exists(real_path)
            or not os.path.isfile(real_path)
        ):
            aura_artifacts_rejected_total.inc()
            return None

        size = os.path.getsize(real_path)
        if size > self.max_bytes:
            aura_artifacts_rejected_total.inc()
            return None

        # Calculate SHA-256 in chunks to avoid blowing up memory
        sha256 = hashlib.sha256()
        with open(real_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)

        artifact = Artifact(
            id=uuid4(),
            environment_id=env.id,
            path=file_path,  # Store the requested path for reference
            type=artifact_type,
            size=size,
            sha256=sha256.hexdigest(),
            created_at=datetime.now(timezone.utc),
            metadata={"real_path": real_path},
        )

        aura_artifacts_created_total.inc()
        return artifact
