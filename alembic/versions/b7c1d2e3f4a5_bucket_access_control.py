"""bucket access control (per-bucket visibility + grants)

Revision ID: b7c1d2e3f4a5
Revises: e1f2a3b4c5d6
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1d2e3f4a5'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bucket_visibility = sa.Enum('everyone', 'restricted', name='bucket_visibility')
    bucket_visibility.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'buckets',
        sa.Column('visibility', bucket_visibility, server_default='everyone', nullable=False),
    )

    op.create_table(
        'bucket_access_grants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('bucket_id', sa.UUID(), nullable=False),
        sa.Column('company_user_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['bucket_id'], ['buckets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_user_id'], ['company_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bucket_id', 'company_user_id', name='uq_bucket_access_grant'),
    )
    op.create_index(op.f('ix_bucket_access_grants_bucket_id'), 'bucket_access_grants', ['bucket_id'], unique=False)
    op.create_index(op.f('ix_bucket_access_grants_company_user_id'), 'bucket_access_grants', ['company_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bucket_access_grants_company_user_id'), table_name='bucket_access_grants')
    op.drop_index(op.f('ix_bucket_access_grants_bucket_id'), table_name='bucket_access_grants')
    op.drop_table('bucket_access_grants')
    op.drop_column('buckets', 'visibility')
    sa.Enum(name='bucket_visibility').drop(op.get_bind(), checkfirst=True)
