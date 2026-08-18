"""add_disposed_by_to_assets

Revision ID: b733bb6c7dae
Revises: e559f8bdfd18
Create Date: 2026-08-18 21:11:34.860625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b733bb6c7dae'
down_revision: Union[str, None] = 'e559f8bdfd18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column(
            "disposed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_assets_disposed_by", "assets", ["disposed_by"])


def downgrade() -> None:
    op.drop_index("ix_assets_disposed_by", table_name="assets")
    op.drop_column("assets", "disposed_by")

