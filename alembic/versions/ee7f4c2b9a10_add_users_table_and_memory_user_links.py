"""add users table and memory user links

Revision ID: ee7f4c2b9a10
Revises: c3f8a91d2b7e
Create Date: 2026-07-27 00:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ee7f4c2b9a10"
down_revision: Union[str, Sequence[str], None] = "c3f8a91d2b7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _seed_existing_user_ids() -> None:
    bind = op.get_bind()
    now = datetime.utcnow()

    user_ids: set[str] = {"default_user"}
    for table_name in ("user_profiles", "conversation_records"):
        rows = bind.execute(sa.text(f"SELECT DISTINCT user_id FROM {table_name} WHERE user_id IS NOT NULL"))
        user_ids.update(row[0] for row in rows if row[0])

    users_table = sa.table(
        "users",
        sa.column("id", sa.String),
        sa.column("username", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("display_name", sa.String),
        sa.column("role", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    for user_id in sorted(user_ids):
        bind.execute(
            sa.insert(users_table).values(
                id=user_id,
                username=user_id,
                password_hash="UNUSABLE_PASSWORD",
                display_name=user_id,
                role="user",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_index(op.f("ix_users_is_active"), "users", ["is_active"], unique=False)

    _seed_existing_user_ids()

    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.create_foreign_key(
            "fk_user_profiles_user_id_users",
            "users",
            ["user_id"],
            ["id"],
        )

    with op.batch_alter_table("conversation_records") as batch_op:
        batch_op.create_foreign_key(
            "fk_conversation_records_user_id_users",
            "users",
            ["user_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("conversation_records") as batch_op:
        batch_op.drop_constraint("fk_conversation_records_user_id_users", type_="foreignkey")

    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.drop_constraint("fk_user_profiles_user_id_users", type_="foreignkey")

    op.drop_index(op.f("ix_users_is_active"), table_name="users")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
