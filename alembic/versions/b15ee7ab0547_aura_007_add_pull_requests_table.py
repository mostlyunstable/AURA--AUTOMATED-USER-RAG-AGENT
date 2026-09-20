"""AURA-007: Add pull_requests table

Revision ID: b15ee7ab0547
Revises: e8957405ae91
Create Date: 2026-09-20 11:49:42.065480

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b15ee7ab0547"
down_revision: Union[str, Sequence[str], None] = "e8957405ae91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "mission_id", sa.Uuid(), sa.ForeignKey("missions.id"), nullable=False
        ),
        sa.Column(
            "task_execution_id",
            sa.Uuid(),
            sa.ForeignKey("task_executions.id"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id"), nullable=True
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_pr_id", sa.Integer(), nullable=True),
        sa.Column("provider_url", sa.String(500), nullable=True),
        sa.Column("source_branch", sa.String(255), nullable=False),
        sa.Column(
            "target_branch", sa.String(255), nullable=False, server_default="main"
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("source_commit_sha", sa.String(100), nullable=True),
        sa.Column("merge_commit_sha", sa.String(100), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_by", sa.String(255), nullable=True),
        sa.Column("approval_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pull_requests_mission_id", "pull_requests", ["mission_id"])
    op.create_index(
        "ix_pull_requests_task_execution_id", "pull_requests", ["task_execution_id"]
    )
    op.create_index("ix_pull_requests_agent_run_id", "pull_requests", ["agent_run_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_pull_requests_agent_run_id", table_name="pull_requests")
    op.drop_index("ix_pull_requests_task_execution_id", table_name="pull_requests")
    op.drop_index("ix_pull_requests_mission_id", table_name="pull_requests")
    op.drop_table("pull_requests")
