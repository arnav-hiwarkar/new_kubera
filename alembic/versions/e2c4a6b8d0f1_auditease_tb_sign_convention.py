"""auditease: canonical signed net-debit trial balance + group nature

Introduces the canonical sign model:
  * ledger_groups.nature            -- persisted debit/credit nature on seeded tops
  * trial_balance_accounts.*_net_debit -- signed net debit (the canonical figures)
  * trial_balance_accounts.sign_unresolved / source_row_consistent
  * audit_engagements.tb_sign_convention

Backfill is deliberately CONSERVATIVE. An engagement is migrated automatically only
when its closing balances *prove* the signed convention (they sum to zero and at
least one is negative). Everything else is left with tb_sign_convention = NULL and
sign_unresolved = true, i.e. explicitly "needs review", so no engagement silently
starts reporting numbers derived from a guess. Use scripts/backfill_tb_net_debit.py
or the /trial-balance/sign-convention endpoint to resolve those.

Revision ID: e2c4a6b8d0f1
Revises: d1e2f3a4b5c6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e2c4a6b8d0f1"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


BALANCE_NATURE = postgresql.ENUM("debit", "credit", name="balance_nature")
TB_SIGN_CONVENTION = postgresql.ENUM(
    "signed", "magnitude", "explicit", "derived", name="tb_sign_convention"
)


def upgrade() -> None:
    bind = op.get_bind()
    BALANCE_NATURE.create(bind, checkfirst=True)
    TB_SIGN_CONVENTION.create(bind, checkfirst=True)

    # --- ledger group nature ---
    op.add_column(
        "ledger_groups",
        sa.Column("nature", BALANCE_NATURE, nullable=True),
    )
    for name, nature in (
        ("Assets", "debit"),
        ("Liabilities", "credit"),
        ("Income", "credit"),
        ("Expenditure", "debit"),
    ):
        op.execute(
            sa.text(
                "UPDATE ledger_groups SET nature = CAST(:nature AS balance_nature) "
                "WHERE company_id IS NULL AND level = 0 AND name = :name"
            ).bindparams(nature=nature, name=name)
        )

    # --- canonical net-debit columns ---
    op.add_column(
        "trial_balance_accounts",
        sa.Column("opening_net_debit", sa.Numeric(15, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "trial_balance_accounts",
        sa.Column("closing_net_debit", sa.Numeric(15, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "trial_balance_accounts",
        sa.Column("sign_unresolved", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "trial_balance_accounts",
        sa.Column("source_row_consistent", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "audit_engagements",
        sa.Column("tb_sign_convention", TB_SIGN_CONVENTION, nullable=True),
    )

    # --- conservative backfill: only provably-signed engagements ---
    op.execute(
        """
        WITH provable AS (
            SELECT engagement_id
            FROM trial_balance_accounts
            GROUP BY engagement_id
            HAVING ABS(SUM(closing_balance)) < 0.01 AND MIN(closing_balance) < 0
        )
        UPDATE trial_balance_accounts tba
        SET opening_net_debit = tba.opening_balance,
            closing_net_debit = tba.closing_balance,
            sign_unresolved = false
        FROM provable p
        WHERE tba.engagement_id = p.engagement_id
        """
    )
    op.execute(
        """
        UPDATE audit_engagements ae
        SET tb_sign_convention = 'signed'
        WHERE EXISTS (
            SELECT 1 FROM trial_balance_accounts tba
            WHERE tba.engagement_id = ae.id
            GROUP BY tba.engagement_id
            HAVING ABS(SUM(tba.closing_balance)) < 0.01 AND MIN(tba.closing_balance) < 0
        )
        """
    )
    # Everything not proven above keeps the raw magnitude and is flagged for review.
    op.execute(
        """
        UPDATE trial_balance_accounts tba
        SET opening_net_debit = tba.opening_balance,
            closing_net_debit = tba.closing_balance,
            sign_unresolved = true
        FROM audit_engagements ae
        WHERE tba.engagement_id = ae.id AND ae.tb_sign_convention IS NULL
        """
    )

    # The ORM default governs new rows from here on.
    op.alter_column("trial_balance_accounts", "opening_net_debit", server_default=None)
    op.alter_column("trial_balance_accounts", "closing_net_debit", server_default=None)


def downgrade() -> None:
    op.drop_column("audit_engagements", "tb_sign_convention")
    op.drop_column("trial_balance_accounts", "source_row_consistent")
    op.drop_column("trial_balance_accounts", "sign_unresolved")
    op.drop_column("trial_balance_accounts", "closing_net_debit")
    op.drop_column("trial_balance_accounts", "opening_net_debit")
    op.drop_column("ledger_groups", "nature")
    bind = op.get_bind()
    TB_SIGN_CONVENTION.drop(bind, checkfirst=True)
    BALANCE_NATURE.drop(bind, checkfirst=True)
