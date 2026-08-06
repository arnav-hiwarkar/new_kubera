"""compliance: archive records without deleting them or their files

Archiving a meeting record also archives its docVault document. The prior
document status is snapshotted so unarchiving restores it exactly, rather than
resetting to 'uploaded' the way the docVault drawer's restore does.

Revision ID: b5e1d84c07a2
Revises: a3f7c9d2e5b8
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b5e1d84c07a2"
down_revision: Union[str, None] = "a3f7c9d2e5b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "meeting_records",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Plain varchar, not the documentstatus enum: this is a snapshot of a past
    # value, so it must not be coupled to future enum changes.
    op.add_column(
        "meeting_records",
        sa.Column("archived_document_status", sa.String(length=50), nullable=True),
    )
    # A document can be locked without being archived, so the lock state has to be
    # snapshotted too or unarchiving would silently unlock it.
    op.add_column(
        "meeting_records",
        sa.Column("archived_document_editable", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    # Non-destructive: every record survives, it just stops being archived.
    op.drop_column("meeting_records", "archived_document_editable")
    op.drop_column("meeting_records", "archived_document_status")
    op.drop_column("meeting_records", "archived_at")
