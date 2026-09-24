"""AURA-008: fix metadata column names

Revision ID: 08895ec291a9
Revises: 37ee5f6cfaa9
Create Date: 2026-09-20 16:26:45.551812

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "08895ec291a9"
down_revision: Union[str, Sequence[str], None] = "37ee5f6cfaa9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The AURA-007/AURA-008 migrations created these columns as "metadata_",
    # but every historical migration and all ORM models map the attribute
    # to a database column named "metadata". Rename for consistency.
    for table in ("pull_requests", "workers", "worker_heartbeats", "task_leases"):
        op.alter_column(
            table,
            "metadata_",
            new_column_name="metadata",
            existing_type=sa.JSON(),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("pull_requests", "workers", "worker_heartbeats", "task_leases"):
        op.alter_column(
            table,
            "metadata",
            new_column_name="metadata_",
            existing_type=sa.JSON(),
        )
