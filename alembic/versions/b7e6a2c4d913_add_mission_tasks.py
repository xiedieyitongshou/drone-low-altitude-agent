"""add mission tasks

Revision ID: b7e6a2c4d913
Revises: f9a3d7c61e20
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e6a2c4d913"
down_revision: Union[str, Sequence[str], None] = "f9a3d7c61e20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mission_tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("location_text", sa.String(length=255), nullable=True),
        sa.Column("task_date", sa.String(length=32), nullable=True),
        sa.Column("start_time", sa.String(length=32), nullable=True),
        sa.Column("end_time", sa.String(length=32), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=True),
        sa.Column("candidate_locations_json", sa.JSON(), nullable=True),
        sa.Column("selected_window_json", sa.JSON(), nullable=True),
        sa.Column("latest_decision", sa.String(length=32), nullable=True),
        sa.Column("latest_request_id", sa.String(length=64), nullable=True),
        sa.Column("latest_trace_id", sa.String(length=64), nullable=True),
        sa.Column("latest_conversation_id", sa.String(length=64), nullable=True),
        sa.Column("profile_context_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mission_tasks_user_id"), "mission_tasks", ["user_id"], unique=False)
    op.create_index(op.f("ix_mission_tasks_status"), "mission_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_mission_tasks_task_type"), "mission_tasks", ["task_type"], unique=False)
    op.create_index(op.f("ix_mission_tasks_latest_decision"), "mission_tasks", ["latest_decision"], unique=False)
    op.create_index(op.f("ix_mission_tasks_latest_request_id"), "mission_tasks", ["latest_request_id"], unique=False)
    op.create_index(op.f("ix_mission_tasks_latest_trace_id"), "mission_tasks", ["latest_trace_id"], unique=False)
    op.create_index(
        op.f("ix_mission_tasks_latest_conversation_id"),
        "mission_tasks",
        ["latest_conversation_id"],
        unique=False,
    )
    op.create_index("ix_mission_tasks_user_status", "mission_tasks", ["user_id", "status"], unique=False)
    op.create_index("ix_mission_tasks_user_created_at", "mission_tasks", ["user_id", "created_at"], unique=False)

    with op.batch_alter_table("conversation_records") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_conversation_records_task_id_mission_tasks",
            "mission_tasks",
            ["task_id"],
            ["id"],
        )
        batch_op.create_index(op.f("ix_conversation_records_task_id"), ["task_id"], unique=False)

    with op.batch_alter_table("task_requests") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_task_requests_task_id_mission_tasks",
            "mission_tasks",
            ["task_id"],
            ["id"],
        )
        batch_op.create_index(op.f("ix_task_requests_task_id"), ["task_id"], unique=False)

    with op.batch_alter_table("cruise_assessments") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_cruise_assessments_task_id_mission_tasks",
            "mission_tasks",
            ["task_id"],
            ["id"],
        )
        batch_op.create_index(op.f("ix_cruise_assessments_task_id"), ["task_id"], unique=False)

    with op.batch_alter_table("agent_trace_events") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_trace_events_task_id_mission_tasks",
            "mission_tasks",
            ["task_id"],
            ["id"],
        )
        batch_op.create_index(op.f("ix_agent_trace_events_task_id"), ["task_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("agent_trace_events") as batch_op:
        batch_op.drop_index(op.f("ix_agent_trace_events_task_id"))
        batch_op.drop_constraint("fk_agent_trace_events_task_id_mission_tasks", type_="foreignkey")
        batch_op.drop_column("task_id")

    with op.batch_alter_table("cruise_assessments") as batch_op:
        batch_op.drop_index(op.f("ix_cruise_assessments_task_id"))
        batch_op.drop_constraint("fk_cruise_assessments_task_id_mission_tasks", type_="foreignkey")
        batch_op.drop_column("task_id")

    with op.batch_alter_table("task_requests") as batch_op:
        batch_op.drop_index(op.f("ix_task_requests_task_id"))
        batch_op.drop_constraint("fk_task_requests_task_id_mission_tasks", type_="foreignkey")
        batch_op.drop_column("task_id")

    with op.batch_alter_table("conversation_records") as batch_op:
        batch_op.drop_index(op.f("ix_conversation_records_task_id"))
        batch_op.drop_constraint("fk_conversation_records_task_id_mission_tasks", type_="foreignkey")
        batch_op.drop_column("task_id")


    op.drop_index("ix_mission_tasks_user_created_at", table_name="mission_tasks")
    op.drop_index("ix_mission_tasks_user_status", table_name="mission_tasks")
    op.drop_index(op.f("ix_mission_tasks_latest_conversation_id"), table_name="mission_tasks")
    op.drop_index(op.f("ix_mission_tasks_latest_trace_id"), table_name="mission_tasks")
    op.drop_index(op.f("ix_mission_tasks_latest_request_id"), table_name="mission_tasks")
    op.drop_index(op.f("ix_mission_tasks_latest_decision"), table_name="mission_tasks")
    op.drop_index(op.f("ix_mission_tasks_task_type"), table_name="mission_tasks")
    op.drop_index(op.f("ix_mission_tasks_status"), table_name="mission_tasks")
    op.drop_index(op.f("ix_mission_tasks_user_id"), table_name="mission_tasks")
    op.drop_table("mission_tasks")
