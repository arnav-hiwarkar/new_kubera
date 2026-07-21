"""active-only unique email (partial unique index over deleted_at IS NULL)

Revision ID: e1f2a3b4c5d6
Revises: d7e9f1a2b3c4
Create Date: 2026-07-21 00:00:00.000000

Replaces the global unique constraint on company_users.email with a partial,
case-insensitive unique index that applies only to live accounts (deleted_at IS
NULL). This lets a soft-deleted user's email be reused by a new account while the
old row (and its name) is retained for historical attribution.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd7e9f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Auto-generated name of the original unnamed UniqueConstraint('email').
_OLD_CONSTRAINT = "company_users_email_key"
_NEW_INDEX = "uq_company_users_email_active"


def upgrade() -> None:
    op.execute(f'ALTER TABLE company_users DROP CONSTRAINT "{_OLD_CONSTRAINT}"')
    # Case-insensitive, live-accounts-only uniqueness.
    op.execute(
        f'CREATE UNIQUE INDEX "{_NEW_INDEX}" ON company_users (lower(email)) '
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute(f'DROP INDEX "{_NEW_INDEX}"')
    op.execute(f'ALTER TABLE company_users ADD CONSTRAINT "{_OLD_CONSTRAINT}" UNIQUE (email)')
