"""add_book_to_depreciation_runs

Revision ID: e559f8bdfd18
Revises: f3a5b7c9d1e2
Create Date: 2026-08-18 21:11:30.798149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e559f8bdfd18'
down_revision: Union[str, None] = 'f3a5b7c9d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "depreciation_runs",
        sa.Column("book", sa.String(20), nullable=False, server_default="companies_act"),
    )
    op.create_index(
        "uq_depreciation_runs_company_fy_book_finalized",
        "depreciation_runs",
        ["company_id", "financial_year_id", "book"],
        unique=True,
        postgresql_where=sa.text("status = 'finalized'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_depreciation_runs_company_fy_book_finalized",
        table_name="depreciation_runs",
        postgresql_where=sa.text("status = 'finalized'"),
    )
    op.drop_column("depreciation_runs", "book")

