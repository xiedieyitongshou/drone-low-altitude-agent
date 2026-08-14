"""add rule snapshots to assessments

Revision ID: e8f2c4a91b37
Revises: d6c4b1e2f9a8
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f2c4a91b37"
down_revision: Union[str, Sequence[str], None] = "d6c4b1e2f9a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cruise_assessments", sa.Column("rule_set_id", sa.String(length=64), nullable=True))
    op.add_column("cruise_assessments", sa.Column("rule_set_version", sa.Integer(), nullable=True))
    op.add_column("cruise_assessments", sa.Column("rule_snapshot_json", sa.JSON(), nullable=True))
    op.add_column("cruise_assessments", sa.Column("rule_hits_json", sa.JSON(), nullable=True))
    op.create_index(op.f("ix_cruise_assessments_rule_set_id"), "cruise_assessments", ["rule_set_id"], unique=False)

    op.add_column("cruise_hourly_assessments", sa.Column("rule_hits_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cruise_hourly_assessments", "rule_hits_json")

    op.drop_index(op.f("ix_cruise_assessments_rule_set_id"), table_name="cruise_assessments")
    op.drop_column("cruise_assessments", "rule_hits_json")
    op.drop_column("cruise_assessments", "rule_snapshot_json")
    op.drop_column("cruise_assessments", "rule_set_version")
    op.drop_column("cruise_assessments", "rule_set_id")
