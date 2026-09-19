"""AURA-006: Add verification tables

Revision ID: e8957405ae91
Revises: d186a8709edf
Create Date: 2026-09-19 23:30:16.321138

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e8957405ae91"
down_revision: Union[str, Sequence[str], None] = "d186a8709edf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create verification_results table
    op.create_table(
        "verification_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "agent_run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id"), nullable=False
        ),
        sa.Column(
            "task_execution_id",
            sa.Uuid(),
            sa.ForeignKey("task_executions.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("failed_checks", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("changed_files", sa.JSON(), nullable=False),
        sa.Column("test_results", sa.JSON(), nullable=False),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_verification_results_agent_run_id", "verification_results", ["agent_run_id"]
    )
    op.create_index(
        "ix_verification_results_task_execution_id",
        "verification_results",
        ["task_execution_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_verification_results_task_execution_id", table_name="verification_results"
    )
    op.drop_index(
        "ix_verification_results_agent_run_id", table_name="verification_results"
    )
    op.drop_table("verification_results")
