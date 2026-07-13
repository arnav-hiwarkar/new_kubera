"""auditease slice3: make docvault created_by nullable

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('documents', 'created_by', existing_type=sa.UUID(), nullable=True)
    op.alter_column('document_versions', 'uploaded_by', existing_type=sa.UUID(), nullable=True)
    op.alter_column('buckets', 'created_by', existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column('buckets', 'created_by', existing_type=sa.UUID(), nullable=False)
    op.alter_column('document_versions', 'uploaded_by', existing_type=sa.UUID(), nullable=False)
    op.alter_column('documents', 'created_by', existing_type=sa.UUID(), nullable=False)
