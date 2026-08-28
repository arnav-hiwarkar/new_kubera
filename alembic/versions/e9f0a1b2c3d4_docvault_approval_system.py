"""docvault approval system

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-28 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, None] = 'd8e9f0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('approver_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('documents', sa.Column('approval_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('approval_notes', sa.String(length=1000), nullable=True))
    op.create_foreign_key('fk_documents_approver_id', 'documents', 'company_users', ['approver_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_documents_approver_id', 'documents', ['approver_id'])
    op.create_index('ix_documents_company_approver_status', 'documents', ['company_id', 'approver_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_documents_company_approver_status', table_name='documents')
    op.drop_index('ix_documents_approver_id', table_name='documents')
    op.drop_constraint('fk_documents_approver_id', 'documents', type_='foreignkey')
    op.drop_column('documents', 'approval_notes')
    op.drop_column('documents', 'approved_at')
    op.drop_column('documents', 'approval_requested_at')
    op.drop_column('documents', 'approver_id')
