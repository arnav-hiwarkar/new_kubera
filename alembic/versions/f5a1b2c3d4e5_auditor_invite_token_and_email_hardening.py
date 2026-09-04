"""auditor invite token hardening, area_permissions, and lowercase email index

Revision ID: f5a1b2c3d4e5
Revises: 23625093f55a
Create Date: 2026-09-04 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'f5a1b2c3d4e5'
down_revision: Union[str, None] = '23625093f55a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FULL_PERMS = '\'{"trial_balance": true, "entries": true, "requirements": true, "queries": true, "documents": true}\'::jsonb'


def upgrade() -> None:
    # 1. Normalize existing auditor emails to lowercase
    op.execute("UPDATE auditors SET email = lower(email)")
    
    # 2. Drop existing case-sensitive unique constraint and add lower(email) unique index
    op.drop_constraint('auditors_email_key', 'auditors', type_='unique')
    op.create_index('uq_auditors_email_lower', 'auditors', [sa.text('lower(email)')], unique=True)

    # 3. Update pending_auditor_invites
    op.drop_column('pending_auditor_invites', 'token')
    op.add_column('pending_auditor_invites', sa.Column('token_hash', sa.String(length=255), nullable=False, server_default='__expired__'))
    op.add_column('pending_auditor_invites', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now() - interval '1 second'")))
    op.add_column('pending_auditor_invites', sa.Column('area_permissions', JSONB(), nullable=False, server_default=sa.text(_FULL_PERMS)))
    
    # Drop server defaults for token_hash and expires_at after backfill
    op.alter_column('pending_auditor_invites', 'token_hash', server_default=None)
    op.alter_column('pending_auditor_invites', 'expires_at', server_default=None)

    # 4. Add index for fast lookup of active invites by email
    op.create_index('ix_pending_auditor_invites_email_lower_expires', 'pending_auditor_invites', [sa.text('lower(email)'), 'expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_pending_auditor_invites_email_lower_expires', table_name='pending_auditor_invites')
    op.drop_column('pending_auditor_invites', 'area_permissions')
    op.drop_column('pending_auditor_invites', 'expires_at')
    op.drop_column('pending_auditor_invites', 'token_hash')
    op.add_column('pending_auditor_invites', sa.Column('token', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')))
    op.alter_column('pending_auditor_invites', 'token', server_default=None)

    op.drop_index('uq_auditors_email_lower', table_name='auditors')
    op.create_unique_constraint('auditors_email_key', 'auditors', ['email'])
