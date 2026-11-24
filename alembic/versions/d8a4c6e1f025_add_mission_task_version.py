"""Protect mission task writes with an optimistic version counter."""

from alembic import op
import sqlalchemy as sa


revision = "d8a4c6e1f025"
down_revision = "a7d2e6b9c014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mission_tasks", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("mission_tasks", "version")
