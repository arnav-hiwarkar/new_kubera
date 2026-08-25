"""multi-auditor grants: area_permissions + unique constraint; activity engagement link

Revision ID: b5d8f2a6c9e1
Revises: d7a1c9b2e4f3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'b5d8f2a6c9e1'
down_revision: Union[str, None] = 'd7a1c9b2e4f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FULL_PERMS = '\'{"trial_balance": true, "entries": true, "requirements": true, "queries": true, "documents": true}\'::jsonb'


def upgrade() -> None:
    op.add_column(
        'auditor_engagement_grants',
        sa.Column('area_permissions', JSONB(), nullable=False, server_default=sa.text(_FULL_PERMS)),
    )
    op.create_unique_constraint('uq_grant_auditor_engagement', 'auditor_engagement_grants', ['auditor_id', 'engagement_id'])
    op.add_column('activity_logs', sa.Column('engagement_id', UUID(), nullable=True))
    op.create_index('ix_activity_logs_engagement_id', 'activity_logs', ['engagement_id'])


def downgrade() -> None:
    op.drop_index('ix_activity_logs_engagement_id', table_name='activity_logs')
    op.drop_column('activity_logs', 'engagement_id')
    op.drop_constraint('uq_grant_auditor_engagement', 'auditor_engagement_grants', type_='unique')
    op.drop_column('auditor_engagement_grants', 'area_permissions')
