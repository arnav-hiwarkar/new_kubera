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

    # The old index allowed one finalized run per (company, FY, book), so a database
    # may legitimately hold two finalized runs for a single financial year — one per
    # book. Narrowing the index to (company, FY) would abort on exactly that data.
    # Demote the superseded ones to draft rather than deleting them: a finalized run
    # owns computed depreciation lines that a statutory report may already cite, so
    # they are kept and only their status is downgraded. The most recently finalized
    # run for each financial year is the one that stays finalized.
    op.execute(
        sa.text(
            """
            UPDATE depreciation_runs AS d
               SET status = 'draft'
             WHERE d.status = 'finalized'
               AND EXISTS (
                   SELECT 1
                     FROM depreciation_runs AS keep
                    WHERE keep.status = 'finalized'
                      AND keep.company_id = d.company_id
                      AND keep.financial_year_id = d.financial_year_id
                      -- COALESCE because a legacy finalized row may have a NULL
                      -- finalized_at, and a NULL in a row comparison yields NULL,
                      -- not true — which would leave both rows finalized and the
                      -- unique index still unbuildable.
                      AND (COALESCE(keep.finalized_at, TIMESTAMPTZ 'epoch'), keep.id)
                        > (COALESCE(d.finalized_at, TIMESTAMPTZ 'epoch'), d.id)
               )
            """
        )
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
