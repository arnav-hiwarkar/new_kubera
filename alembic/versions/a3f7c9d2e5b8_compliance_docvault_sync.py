"""compliance: nullable doc type, record title, denormalised domain

Prepares meeting_records for docVault import: a synced record arrives with no
document type, so the domain can no longer be derived by joining document_types.

Revision ID: a3f7c9d2e5b8
Revises: 4f6a8b0c2d1e
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3f7c9d2e5b8"
down_revision: Union[str, None] = "4f6a8b0c2d1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The enum already exists (created by the phase 3/4 compliance migration), so
# reference it without letting SQLAlchemy try to CREATE TYPE again.
compliance_domain = postgresql.ENUM(
    "secretarial", "roc", name="compliance_domain", create_type=False
)


def upgrade() -> None:
    op.alter_column("meeting_records", "doc_type_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column("meeting_records", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column("meeting_records", sa.Column("domain", compliance_domain, nullable=True))

    # Backfill the domain from each record's current type before enforcing NOT NULL.
    op.execute(
        """
        UPDATE meeting_records AS mr
        SET domain = dt.domain
        FROM document_types AS dt
        WHERE dt.id = mr.doc_type_id
        """
    )
    # Defensive: every existing row has a type (the column was NOT NULL until now),
    # but do not let a stray orphan block the migration.
    op.execute("UPDATE meeting_records SET domain = 'secretarial' WHERE domain IS NULL")
    op.alter_column("meeting_records", "domain", existing_type=compliance_domain, nullable=False)
    op.create_index("ix_meeting_records_domain", "meeting_records", ["domain"])

    # Seed titles from the linked docVault document so existing records read the
    # same way as newly imported ones.
    op.execute(
        """
        UPDATE meeting_records AS mr
        SET title = d.title
        FROM documents AS d
        WHERE d.id = mr.document_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_meeting_records_domain", table_name="meeting_records")
    op.drop_column("meeting_records", "domain")
    op.drop_column("meeting_records", "title")
    # Untyped records cannot survive a column that is NOT NULL again.
    op.execute("DELETE FROM meeting_records WHERE doc_type_id IS NULL")
    op.alter_column("meeting_records", "doc_type_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
