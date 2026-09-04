"""unique pending auditor invite per engagement+email

Normalizes pending invite emails to lower case, collapses any duplicate
(engagement, email) rows that the previous SELECT-then-INSERT invite path could
race into existence, and adds the unique constraint that makes the invite write
an atomic upsert. Without this, two pending rows for the same engagement+email
turn every later re-invite into a 500 (MultipleResultsFound) and the auditor's
own registration into a permanent 500 (uq_grant_auditor_engagement violation).

Revision ID: a7c4e9b1d2f8
Revises: f5a1b2c3d4e5
Create Date: 2026-09-04 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a7c4e9b1d2f8'
down_revision: Union[str, None] = 'f5a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Normalize casing so the plain unique constraint is case-insensitive in effect.
    op.execute("UPDATE pending_auditor_invites SET email = lower(email)")

    # 2. Collapse duplicates, keeping the most recently created row per
    #    (engagement_id, email) — that row holds the newest token and expiry.
    op.execute(
        """
        DELETE FROM pending_auditor_invites p
        USING pending_auditor_invites q
        WHERE p.engagement_id = q.engagement_id
          AND p.email = q.email
          AND (p.created_at < q.created_at
               OR (p.created_at = q.created_at AND p.id < q.id))
        """
    )

    # 3. Enforce it going forward.
    op.create_unique_constraint(
        'uq_pending_invite_engagement_email',
        'pending_auditor_invites',
        ['engagement_id', 'email'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_pending_invite_engagement_email',
        'pending_auditor_invites',
        type_='unique',
    )
