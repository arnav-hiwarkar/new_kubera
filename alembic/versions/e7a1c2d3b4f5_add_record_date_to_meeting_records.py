"""add record_date to meeting_records

Revision ID: e7a1c2d3b4f5
Revises: 0cb481774093
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7a1c2d3b4f5'
down_revision: Union[str, None] = '0cb481774093'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('meeting_records', sa.Column('record_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('meeting_records', 'record_date')
