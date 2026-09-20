"""AURA-008: Add worker, worker_heartbeat, and task_lease tables

Revision ID: 37ee5f6cfaa9
Revises: b15ee7ab0547
Create Date: 2026-09-20 13:25:51.729598

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "37ee5f6cfaa9"
down_revision: Union[str, Sequence[str], None] = "b15ee7ab0547"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create workers table
    op.create_table(
        "workers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workers_status", "workers", ["status"])

    # Create worker_heartbeats table
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), sa.ForeignKey("workers.id"), nullable=False),
        sa.Column("task_execution_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_worker_heartbeats_worker_id", "worker_heartbeats", ["worker_id"]
    )
    op.create_index(
        "ix_worker_heartbeats_task_execution_id",
        "worker_heartbeats",
        ["task_execution_id"],
    )

    # Create task_leases table
    op.create_table(
        "task_leases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.Uuid(), sa.ForeignKey("workers.id"), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column(
            "task_execution_id",
            sa.Uuid(),
            sa.ForeignKey("task_executions.id"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renewed_count", sa.Integer(), default=0, nullable=False),
        sa.Column("metadata_", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_leases_worker_id", "task_leases", ["worker_id"])
    op.create_index("ix_task_leases_task_id", "task_leases", ["task_id"])
    op.create_index(
        "ix_task_leases_task_execution_id", "task_leases", ["task_execution_id"]
    )
    op.create_index(
        "ix_task_leases_lease_expires_at", "task_leases", ["lease_expires_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_task_leases_lease_expires_at", table_name="task_leases")
    op.drop_index("ix_task_leases_task_execution_id", table_name="task_leases")
    op.drop_index("ix_task_leases_task_id", table_name="task_leases")
    op.drop_index("ix_task_leases_worker_id", table_name="task_leases")
    op.drop_table("task_leases")
    op.drop_index(
        "ix_worker_heartbeats_task_execution_id", table_name="worker_heartbeats"
    )
    op.drop_index("ix_worker_heartbeats_worker_id", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
    op.drop_index("ix_workers_status", table_name="workers")
    op.drop_table("workers")
