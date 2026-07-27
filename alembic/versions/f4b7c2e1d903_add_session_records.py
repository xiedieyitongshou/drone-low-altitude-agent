"""add session records

Revision ID: f4b7c2e1d903
Revises: ee7f4c2b9a10
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4b7c2e1d903"
down_revision: Union[str, Sequence[str], None] = "ee7f4c2b9a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("last_context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "session_id", name="uq_session_records_user_session"),
    )
    op.create_index(op.f("ix_session_records_session_id"), "session_records", ["session_id"], unique=False)
    op.create_index(op.f("ix_session_records_user_id"), "session_records", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_session_records_user_id"), table_name="session_records")
    op.drop_index(op.f("ix_session_records_session_id"), table_name="session_records")
    op.drop_table("session_records")
