"""depreciation_run_unique_per_fy

Revision ID: c1f2e3d4a5b6
Revises: b733bb6c7dae
Create Date: 2026-08-18 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f2e3d4a5b6'
down_revision: Union[str, None] = 'b733bb6c7dae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "uq_depreciation_runs_company_fy_book_finalized",
        table_name="depreciation_runs",
        postgresql_where=sa.text("status = 'finalized'"),
    )
    op.create_index(
        "uq_depreciation_runs_company_fy_finalized",
        "depreciation_runs",
        ["company_id", "financial_year_id"],
        unique=True,
        postgresql_where=sa.text("status = 'finalized'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_depreciation_runs_company_fy_finalized",
        table_name="depreciation_runs",
        postgresql_where=sa.text("status = 'finalized'"),
    )
    op.create_index(
        "uq_depreciation_runs_company_fy_book_finalized",
        "depreciation_runs",
        ["company_id", "financial_year_id", "book"],
        unique=True,
        postgresql_where=sa.text("status = 'finalized'"),
    )
