"""add job timestamps and composite indexes

Revision ID: 4b5c6d7e8f9a
Revises: 39fae4a3336b
Create Date: 2026-10-20 21:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b5c6d7e8f9a'
down_revision: Union[str, None] = '39fae4a3336b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Add tenant_id and owner_api_key to projects if missing
    project_cols = [c["name"] for c in inspector.get_columns("projects")]
    if "tenant_id" not in project_cols:
        op.add_column("projects", sa.Column("tenant_id", sa.String(length=255), nullable=True))
        op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"], unique=False)
    if "owner_api_key" not in project_cols:
        op.add_column("projects", sa.Column("owner_api_key", sa.String(length=255), nullable=True))
        op.create_index("ix_projects_owner_api_key", "projects", ["owner_api_key"], unique=False)

    # 2. Add started_at and completed_at to processing_jobs if missing
    job_cols = [c["name"] for c in inspector.get_columns("processing_jobs")]
    if "started_at" not in job_cols:
        op.add_column("processing_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    if "completed_at" not in job_cols:
        op.add_column("processing_jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    def create_index_if_missing(idx_name: str, table_name: str, columns: list[str]) -> None:
        existing = [idx["name"] for idx in inspector.get_indexes(table_name)]
        if idx_name not in existing:
            op.create_index(idx_name, table_name, columns, unique=False)

    # 3. Composite indexes on processing_jobs
    create_index_if_missing("ix_processing_jobs_project_status_created", "processing_jobs", ["project_id", "status", "created_at"])
    create_index_if_missing("ix_processing_jobs_project_created", "processing_jobs", ["project_id", "created_at"])

    # 4. Composite indexes on documents
    create_index_if_missing("ix_documents_project_created", "documents", ["project_id", "created_at"])
    create_index_if_missing("ix_documents_project_filename", "documents", ["project_id", "filename"])

    # 5. Composite indexes on document_chunks
    create_index_if_missing("ix_document_chunks_project_document", "document_chunks", ["project_id", "document_id"])
    create_index_if_missing("ix_document_chunks_document_index", "document_chunks", ["document_id", "chunk_index"])

    # 6. Composite index on projects
    create_index_if_missing("ix_projects_tenant_created", "projects", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index('ix_projects_tenant_created', table_name='projects')
    op.drop_index('ix_document_chunks_document_index', table_name='document_chunks')
    op.drop_index('ix_document_chunks_project_document', table_name='document_chunks')
    op.drop_index('ix_documents_project_filename', table_name='documents')
    op.drop_index('ix_documents_project_created', table_name='documents')
    op.drop_index('ix_processing_jobs_project_created', table_name='processing_jobs')
    op.drop_index('ix_processing_jobs_project_status_created', table_name='processing_jobs')
    op.drop_column('processing_jobs', 'completed_at')
    op.drop_column('processing_jobs', 'started_at')
