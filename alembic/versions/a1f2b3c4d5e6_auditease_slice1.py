"""auditease slice1: per-engagement TB, draft status, pending invites

Revision ID: a1f2b3c4d5e6
Revises: 18ea14265cbb
Create Date: 2026-07-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1f2b3c4d5e6'
down_revision: Union[str, None] = '18ea14265cbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add 'draft' to the engagement_status enum.
    op.execute("COMMIT")
    op.execute("ALTER TYPE engagement_status ADD VALUE IF NOT EXISTS 'draft'")

    # 2. Trial balance becomes per-engagement. Old rows were company-global and
    #    have no engagement to belong to under the new model — drop them.
    op.execute("DELETE FROM trial_balance_accounts")
    op.add_column(
        'trial_balance_accounts',
        sa.Column('engagement_id', postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_index(
        op.f('ix_trial_balance_accounts_engagement_id'),
        'trial_balance_accounts', ['engagement_id'], unique=False,
    )
    op.create_foreign_key(
        'fk_trial_balance_accounts_engagement_id',
        'trial_balance_accounts', 'audit_engagements',
        ['engagement_id'], ['id'], ondelete='CASCADE',
    )

    # 3. Pending invites (email invited before an auditor account exists).
    op.create_table(
        'pending_auditor_invites',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('engagement_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('token', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['engagement_id'], ['audit_engagements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pending_auditor_invites_engagement_id'), 'pending_auditor_invites', ['engagement_id'], unique=False)
    op.create_index(op.f('ix_pending_auditor_invites_email'), 'pending_auditor_invites', ['email'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pending_auditor_invites_email'), table_name='pending_auditor_invites')
    op.drop_index(op.f('ix_pending_auditor_invites_engagement_id'), table_name='pending_auditor_invites')
    op.drop_table('pending_auditor_invites')

    op.drop_constraint('fk_trial_balance_accounts_engagement_id', 'trial_balance_accounts', type_='foreignkey')
    op.drop_index(op.f('ix_trial_balance_accounts_engagement_id'), table_name='trial_balance_accounts')
    op.drop_column('trial_balance_accounts', 'engagement_id')
    # Note: Postgres cannot easily drop an enum value; 'draft' is left in place.
