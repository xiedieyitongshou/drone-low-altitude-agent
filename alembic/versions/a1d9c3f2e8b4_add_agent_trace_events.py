"""add agent trace events

Revision ID: a1d9c3f2e8b4
Revises: f4b7c2e1d903
Create Date: 2026-08-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1d9c3f2e8b4"
down_revision: Union[str, Sequence[str], None] = "f4b7c2e1d903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_trace_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=True),
        sa.Column("status_before", sa.String(length=32), nullable=True),
        sa.Column("status_after", sa.String(length=32), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_summary_json", sa.JSON(), nullable=True),
        sa.Column("output_summary_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_trace_events_trace_id"), "agent_trace_events", ["trace_id"], unique=False)
    op.create_index(op.f("ix_agent_trace_events_run_id"), "agent_trace_events", ["run_id"], unique=False)
    op.create_index(op.f("ix_agent_trace_events_user_id"), "agent_trace_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_agent_trace_events_session_id"), "agent_trace_events", ["session_id"], unique=False)
    op.create_index(op.f("ix_agent_trace_events_event_type"), "agent_trace_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_agent_trace_events_step_index"), "agent_trace_events", ["step_index"], unique=False)
    op.create_index(op.f("ix_agent_trace_events_tool_name"), "agent_trace_events", ["tool_name"], unique=False)
    op.create_index(op.f("ix_agent_trace_events_error_code"), "agent_trace_events", ["error_code"], unique=False)
    op.create_index("ix_agent_trace_events_trace_step", "agent_trace_events", ["trace_id", "step_index"], unique=False)
    op.create_index("ix_agent_trace_events_run_step", "agent_trace_events", ["run_id", "step_index"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_trace_events_run_step", table_name="agent_trace_events")
    op.drop_index("ix_agent_trace_events_trace_step", table_name="agent_trace_events")
    op.drop_index(op.f("ix_agent_trace_events_error_code"), table_name="agent_trace_events")
    op.drop_index(op.f("ix_agent_trace_events_tool_name"), table_name="agent_trace_events")
    op.drop_index(op.f("ix_agent_trace_events_step_index"), table_name="agent_trace_events")
    op.drop_index(op.f("ix_agent_trace_events_event_type"), table_name="agent_trace_events")
    op.drop_index(op.f("ix_agent_trace_events_session_id"), table_name="agent_trace_events")
    op.drop_index(op.f("ix_agent_trace_events_user_id"), table_name="agent_trace_events")
    op.drop_index(op.f("ix_agent_trace_events_run_id"), table_name="agent_trace_events")
    op.drop_index(op.f("ix_agent_trace_events_trace_id"), table_name="agent_trace_events")
    op.drop_table("agent_trace_events")
