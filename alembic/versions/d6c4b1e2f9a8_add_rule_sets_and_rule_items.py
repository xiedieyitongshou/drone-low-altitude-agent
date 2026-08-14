"""add rule sets and rule items

Revision ID: d6c4b1e2f9a8
Revises: a1d9c3f2e8b4
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6c4b1e2f9a8"
down_revision: Union[str, Sequence[str], None] = "a1d9c3f2e8b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rule_sets",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("validation_errors_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "name", "version", name="uq_rule_sets_owner_name_version"),
    )
    op.create_index(op.f("ix_rule_sets_name"), "rule_sets", ["name"], unique=False)
    op.create_index(op.f("ix_rule_sets_task_type"), "rule_sets", ["task_type"], unique=False)
    op.create_index(op.f("ix_rule_sets_version"), "rule_sets", ["version"], unique=False)
    op.create_index(op.f("ix_rule_sets_status"), "rule_sets", ["status"], unique=False)
    op.create_index(op.f("ix_rule_sets_visibility"), "rule_sets", ["visibility"], unique=False)
    op.create_index(op.f("ix_rule_sets_owner_user_id"), "rule_sets", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_rule_sets_tenant_id"), "rule_sets", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_rule_sets_is_default"), "rule_sets", ["is_default"], unique=False)
    op.create_index(op.f("ix_rule_sets_source"), "rule_sets", ["source"], unique=False)

    op.create_table(
        "rule_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("rule_set_id", sa.String(length=64), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("operator", sa.String(length=16), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("threshold_text", sa.String(length=255), nullable=True),
        sa.Column("threshold_values_json", sa.JSON(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("risk_tag", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rule_items_rule_set_id"), "rule_items", ["rule_set_id"], unique=False)
    op.create_index(op.f("ix_rule_items_metric"), "rule_items", ["metric"], unique=False)
    op.create_index(op.f("ix_rule_items_decision"), "rule_items", ["decision"], unique=False)
    op.create_index(op.f("ix_rule_items_risk_tag"), "rule_items", ["risk_tag"], unique=False)
    op.create_index(op.f("ix_rule_items_priority"), "rule_items", ["priority"], unique=False)
    op.create_index(op.f("ix_rule_items_enabled"), "rule_items", ["enabled"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_rule_items_enabled"), table_name="rule_items")
    op.drop_index(op.f("ix_rule_items_priority"), table_name="rule_items")
    op.drop_index(op.f("ix_rule_items_risk_tag"), table_name="rule_items")
    op.drop_index(op.f("ix_rule_items_decision"), table_name="rule_items")
    op.drop_index(op.f("ix_rule_items_metric"), table_name="rule_items")
    op.drop_index(op.f("ix_rule_items_rule_set_id"), table_name="rule_items")
    op.drop_table("rule_items")

    op.drop_index(op.f("ix_rule_sets_source"), table_name="rule_sets")
    op.drop_index(op.f("ix_rule_sets_is_default"), table_name="rule_sets")
    op.drop_index(op.f("ix_rule_sets_tenant_id"), table_name="rule_sets")
    op.drop_index(op.f("ix_rule_sets_owner_user_id"), table_name="rule_sets")
    op.drop_index(op.f("ix_rule_sets_visibility"), table_name="rule_sets")
    op.drop_index(op.f("ix_rule_sets_status"), table_name="rule_sets")
    op.drop_index(op.f("ix_rule_sets_version"), table_name="rule_sets")
    op.drop_index(op.f("ix_rule_sets_task_type"), table_name="rule_sets")
    op.drop_index(op.f("ix_rule_sets_name"), table_name="rule_sets")
    op.drop_table("rule_sets")
