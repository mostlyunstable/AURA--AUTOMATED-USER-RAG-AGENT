"""AURA-005: Add agent runtime tables

Revision ID: d186a8709edf
Revises: ec82cfa28661
Create Date: 2026-09-19 22:18:19.906797

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d186a8709edf"
down_revision: Union[str, Sequence[str], None] = "ec82cfa28661"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add agent_type column to agents table
    op.add_column(
        "agents",
        sa.Column(
            "agent_type", sa.String(50), nullable=False, server_default="CODING_AGENT"
        ),
    )

    # Create agent_runs table
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "mission_id", sa.Uuid(), sa.ForeignKey("missions.id"), nullable=False
        ),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column(
            "task_execution_id",
            sa.Uuid(),
            sa.ForeignKey("task_executions.id"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("iteration_count", sa.Integer(), default=0, nullable=False),
        sa.Column("tool_call_count", sa.Integer(), default=0, nullable=False),
        sa.Column("max_iterations", sa.Integer(), default=50, nullable=False),
        sa.Column("max_tool_calls", sa.Integer(), default=100, nullable=False),
        sa.Column("max_runtime_seconds", sa.Integer(), default=1800, nullable=False),
        sa.Column("max_failed_actions", sa.Integer(), default=5, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("final_result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_runs_task_execution_id", "agent_runs", ["task_execution_id"]
    )

    # Create tool_calls table
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "agent_run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id"), nullable=False
        ),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("policy_decision", sa.String(50), nullable=False),
        sa.Column("policy_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_calls_agent_run_id", "tool_calls", ["agent_run_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_tool_calls_agent_run_id", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_index("ix_agent_runs_task_execution_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_column("agents", "agent_type")
