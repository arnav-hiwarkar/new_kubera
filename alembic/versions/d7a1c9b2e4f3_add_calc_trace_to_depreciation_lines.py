"""add_calc_trace_to_depreciation_lines

Revision ID: d7a1c9b2e4f3
Revises: c1f2e3d4a5b6
Create Date: 2026-08-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd7a1c9b2e4f3'
down_revision: Union[str, None] = 'c1f2e3d4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, with no backfill. A trace records how a figure was arrived at using the
    # inputs of the moment; synthesising one now for a run computed months ago would
    # attach today's inputs to yesterday's number. Lines without a trace are shown as
    # exactly that, and the UI offers a clearly-labelled projection instead.
    for table in ("asset_depreciation_lines", "it_block_depreciation_lines"):
        op.add_column(
            table,
            sa.Column(
                "calc_trace",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade() -> None:
    for table in ("asset_depreciation_lines", "it_block_depreciation_lines"):
        op.drop_column(table, "calc_trace")
