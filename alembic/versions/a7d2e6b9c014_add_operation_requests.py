"""Add durable operation receipts for client retries.

Revision ID: a7d2e6b9c014
Revises: c6a2f41d8e90
"""

from alembic import op
import sqlalchemy as sa


revision = "a7d2e6b9c014"
down_revision = "c6a2f41d8e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_requests",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "operation", "idempotency_key", name="uq_operation_requests_user_operation_key"),
    )


def downgrade() -> None:
    op.drop_table("operation_requests")
