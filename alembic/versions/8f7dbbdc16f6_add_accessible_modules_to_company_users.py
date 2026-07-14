"""add accessible_modules to company_users

Revision ID: 8f7dbbdc16f6
Revises: e7a1c2d3b4f5
Create Date: 2026-07-14 02:38:56.157695

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8f7dbbdc16f6'
down_revision: Union[str, None] = 'a1a6d2477372'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'company_users',
        sa.Column('accessible_modules', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False)
    )

def downgrade() -> None:
    op.drop_column('company_users', 'accessible_modules')
