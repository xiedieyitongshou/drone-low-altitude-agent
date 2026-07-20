"""add profile and conversation memory

Revision ID: c3f8a91d2b7e
Revises: ba594bf836bf
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3f8a91d2b7e"
down_revision: Union[str, Sequence[str], None] = "ba594bf836bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("default_location", sa.String(length=255), nullable=True),
        sa.Column("default_task_type", sa.String(length=64), nullable=True),
        sa.Column("default_start_time", sa.String(length=32), nullable=True),
        sa.Column("default_end_time", sa.String(length=32), nullable=True),
        sa.Column("output_style", sa.String(length=64), nullable=True),
        sa.Column("common_locations_json", sa.JSON(), nullable=False),
        sa.Column("common_task_types_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_profiles_user_id"), "user_profiles", ["user_id"], unique=True)

    op.create_table(
        "conversation_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("target_endpoint", sa.String(length=128), nullable=True),
        sa.Column("parser_source", sa.String(length=64), nullable=True),
        sa.Column("parsed_json", sa.JSON(), nullable=True),
        sa.Column("context_used", sa.Boolean(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversation_records_conversation_id"), "conversation_records", ["conversation_id"], unique=True)
    op.create_index(op.f("ix_conversation_records_session_id"), "conversation_records", ["session_id"], unique=False)
    op.create_index(op.f("ix_conversation_records_user_id"), "conversation_records", ["user_id"], unique=False)
    op.create_index(op.f("ix_conversation_records_intent"), "conversation_records", ["intent"], unique=False)
    op.create_index(op.f("ix_conversation_records_success"), "conversation_records", ["success"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_conversation_records_success"), table_name="conversation_records")
    op.drop_index(op.f("ix_conversation_records_intent"), table_name="conversation_records")
    op.drop_index(op.f("ix_conversation_records_user_id"), table_name="conversation_records")
    op.drop_index(op.f("ix_conversation_records_session_id"), table_name="conversation_records")
    op.drop_index(op.f("ix_conversation_records_conversation_id"), table_name="conversation_records")
    op.drop_table("conversation_records")
    op.drop_index(op.f("ix_user_profiles_user_id"), table_name="user_profiles")
    op.drop_table("user_profiles")
