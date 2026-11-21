"""Link Agent business evaluations, conversations and Trace.

Revision ID: c6a2f41d8e90
Revises: b7e6a2c4d913
"""

from alembic import op
import sqlalchemy as sa


revision = "c6a2f41d8e90"
down_revision = "b7e6a2c4d913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, names in (
        ("task_requests", ("user_id", "trace_id")),
        ("conversation_records", ("trace_id", "request_id")),
    ):
        for name in names:
            op.add_column(table, sa.Column(name, sa.String(64), nullable=True))
            op.create_index(f"ix_{table}_{name}", table, [name])


def downgrade() -> None:
    for table, names in (
        ("conversation_records", ("request_id", "trace_id")),
        ("task_requests", ("trace_id", "user_id")),
    ):
        for name in names:
            op.drop_index(f"ix_{table}_{name}", table_name=table)
            op.drop_column(table, name)
