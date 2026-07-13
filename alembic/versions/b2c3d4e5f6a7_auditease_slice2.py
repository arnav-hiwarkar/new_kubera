"""auditease slice2: ledger_groups.level for chart-of-accounts depth

Revision ID: b2c3d4e5f6a7
Revises: a1f2b3c4d5e6
Create Date: 2026-07-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1f2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # level: 0 = seeded top group, 1 = subgroup, 2 = subsubgroup.
    # The four top groups are lazily seeded on first GET /ledger-groups.
    op.add_column(
        'ledger_groups',
        sa.Column('level', sa.Integer(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('ledger_groups', 'level')
