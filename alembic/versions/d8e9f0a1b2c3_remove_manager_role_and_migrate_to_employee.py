"""remove_manager_role_and_migrate_to_employee

Revision ID: d8e9f0a1b2c3
Revises: f1a2b3c4d5e6
Create Date: 2026-08-28 04:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update any existing manager accounts to employee
    op.execute("UPDATE company_users SET role = 'employee' WHERE role = 'manager'")


def downgrade() -> None:
    pass
