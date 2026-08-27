"""user_password_controls_and_avatar

Revision ID: f1a2b3c4d5e6
Revises: 7e5ea3f3eed7
Create Date: 2026-08-28 03:08:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = '7e5ea3f3eed7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_users",
        sa.Column("can_change_password", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "company_users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_users",
        sa.Column("avatar_path", sa.String(), nullable=True),
    )
    op.add_column(
        "company_users",
        sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_users", "avatar_updated_at")
    op.drop_column("company_users", "avatar_path")
    op.drop_column("company_users", "password_changed_at")
    op.drop_column("company_users", "can_change_password")
