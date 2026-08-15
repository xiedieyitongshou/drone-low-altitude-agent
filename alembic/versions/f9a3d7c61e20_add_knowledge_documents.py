"""add knowledge documents

Revision ID: f9a3d7c61e20
Revises: e8f2c4a91b37
Create Date: 2026-08-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9a3d7c61e20"
down_revision: Union[str, Sequence[str], None] = "e8f2c4a91b37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("knowledge_type", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("province", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("task_types_json", sa.JSON(), nullable=True),
        sa.Column("risk_tags_json", sa.JSON(), nullable=True),
        sa.Column("warning_types_json", sa.JSON(), nullable=True),
        sa.Column("warning_levels_json", sa.JSON(), nullable=True),
        sa.Column("decision_scopes_json", sa.JSON(), nullable=True),
        sa.Column("keywords_json", sa.JSON(), nullable=True),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("index_dirty", sa.Boolean(), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_documents_title"), "knowledge_documents", ["title"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_knowledge_type"), "knowledge_documents", ["knowledge_type"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_category"), "knowledge_documents", ["category"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_region"), "knowledge_documents", ["region"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_province"), "knowledge_documents", ["province"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_city"), "knowledge_documents", ["city"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_visibility"), "knowledge_documents", ["visibility"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_tenant_id"), "knowledge_documents", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_user_id"), "knowledge_documents", ["user_id"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_version"), "knowledge_documents", ["version"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_review_status"), "knowledge_documents", ["review_status"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_is_active"), "knowledge_documents", ["is_active"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_index_dirty"), "knowledge_documents", ["index_dirty"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_effective_at"), "knowledge_documents", ["effective_at"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_expires_at"), "knowledge_documents", ["expires_at"], unique=False)

    op.create_table(
        "knowledge_index_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("index_type", sa.String(length=32), nullable=False),
        sa.Column("triggered_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_index_jobs_status"), "knowledge_index_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_knowledge_index_jobs_index_type"), "knowledge_index_jobs", ["index_type"], unique=False)
    op.create_index(op.f("ix_knowledge_index_jobs_triggered_by_user_id"), "knowledge_index_jobs", ["triggered_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_index_jobs_triggered_by_user_id"), table_name="knowledge_index_jobs")
    op.drop_index(op.f("ix_knowledge_index_jobs_index_type"), table_name="knowledge_index_jobs")
    op.drop_index(op.f("ix_knowledge_index_jobs_status"), table_name="knowledge_index_jobs")
    op.drop_table("knowledge_index_jobs")

    op.drop_index(op.f("ix_knowledge_documents_expires_at"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_effective_at"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_index_dirty"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_is_active"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_review_status"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_version"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_user_id"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_tenant_id"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_visibility"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_city"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_province"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_region"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_category"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_knowledge_type"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_title"), table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
