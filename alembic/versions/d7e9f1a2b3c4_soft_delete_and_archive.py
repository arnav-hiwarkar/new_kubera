"""soft-delete users (deleted_at) and archive companies (archived_at)

Revision ID: d7e9f1a2b3c4
Revises: a2b3c4d5e6f7
Create Date: 2026-07-20 00:00:00.000000

Adds the markers behind operator soft-delete/archive:
- company_users.deleted_at — a soft-deleted user (login disabled, email freed,
  row kept so historical work still shows full_name).
- companies.archived_at — an archived company (all logins disabled, name/admin
  email freed for reuse, encrypted data retained).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e9f1a2b3c4'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_users", "deleted_at")
    op.drop_column("companies", "archived_at")
