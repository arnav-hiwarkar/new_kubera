"""add company smtp configs and email logs

Revision ID: ddf024af58cd
Revises: e9f0a1b2c3d4
Create Date: 2026-08-28 23:39:21.799606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ddf024af58cd'
down_revision: Union[str, None] = 'e9f0a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('company_smtp_configs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('host', sa.String(length=255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('user', sa.String(length=255), nullable=False),
        sa.Column('encrypted_password', sa.LargeBinary(), nullable=False),
        sa.Column('password_nonce', sa.LargeBinary(), nullable=False),
        sa.Column('use_tls', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('use_ssl', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('from_email', sa.String(length=255), nullable=False),
        sa.Column('from_name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_tested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_company_smtp_configs_company_id'), 'company_smtp_configs', ['company_id'], unique=True)

    op.create_table('email_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=True),
        sa.Column('sender_email', sa.String(length=255), nullable=False),
        sa.Column('sender_name', sa.String(length=255), nullable=False),
        sa.Column('recipient_email', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=500), nullable=False),
        sa.Column('template_name', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('message_id', sa.String(length=255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_email_logs_company_id'), 'email_logs', ['company_id'], unique=False)
    op.create_index(op.f('ix_email_logs_created_at'), 'email_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_email_logs_recipient_email'), 'email_logs', ['recipient_email'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_email_logs_recipient_email'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_created_at'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_company_id'), table_name='email_logs')
    op.drop_table('email_logs')
    op.drop_index(op.f('ix_company_smtp_configs_company_id'), table_name='company_smtp_configs')
    op.drop_table('company_smtp_configs')
