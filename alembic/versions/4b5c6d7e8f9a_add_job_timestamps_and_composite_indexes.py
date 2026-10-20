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
    # 1. Add started_at and completed_at to processing_jobs
    op.add_column('processing_jobs', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('processing_jobs', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))

    # 2. Composite indexes on processing_jobs
    op.create_index('ix_processing_jobs_project_status_created', 'processing_jobs', ['project_id', 'status', 'created_at'], unique=False)
    op.create_index('ix_processing_jobs_project_created', 'processing_jobs', ['project_id', 'created_at'], unique=False)

    # 3. Composite indexes on documents
    op.create_index('ix_documents_project_created', 'documents', ['project_id', 'created_at'], unique=False)
    op.create_index('ix_documents_project_filename', 'documents', ['project_id', 'filename'], unique=False)

    # 4. Composite indexes on document_chunks
    op.create_index('ix_document_chunks_project_document', 'document_chunks', ['project_id', 'document_id'], unique=False)
    op.create_index('ix_document_chunks_document_index', 'document_chunks', ['document_id', 'chunk_index'], unique=False)

    # 5. Composite index on projects
    op.create_index('ix_projects_tenant_created', 'projects', ['tenant_id', 'created_at'], unique=False)


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
