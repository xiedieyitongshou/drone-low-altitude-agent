"""Persist knowledge publication progress for crash recovery.

Revision ID: e3b7a9d20c64
Revises: d8a4c6e1f025
"""

from alembic import op
import sqlalchemy as sa


revision = "e3b7a9d20c64"
down_revision = "d8a4c6e1f025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL identifies records produced before recoverable publication existed.
    op.add_column("knowledge_index_jobs", sa.Column("index_version", sa.String(64), nullable=True))
    op.add_column("knowledge_index_jobs", sa.Column("publication_phase", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_index_jobs", "publication_phase")
    op.drop_column("knowledge_index_jobs", "index_version")
