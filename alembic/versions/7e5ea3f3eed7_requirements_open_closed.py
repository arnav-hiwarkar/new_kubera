"""requirements_open_closed

Revision ID: 7e5ea3f3eed7
Revises: a4b5c6d7e8f9
Create Date: 2026-08-27 22:46:05.647770

This migration collapses the RequirementRequest lifecycle to open/closed,
drops legacy metadata fields, makes requirement responses multi-document via
the requirement_response_documents join table, and adds round_number.

Downgrade is LOSSY BY DESIGN: requirements that were submitted or clarification_needed
are indistinguishable from pending after upgrade, and the eleven dropped columns
are permanently deleted.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '7e5ea3f3eed7'
down_revision: Union[str, None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create requirement_response_documents table
    op.create_table(
        "requirement_response_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("response_id", UUID(as_uuid=True),
                  sa.ForeignKey("requirement_responses.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("document_id", UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.UniqueConstraint("response_id", "document_id", name="uq_req_response_document"),
    )

    # 2. Backfill requirement_response_documents from legacy single-document responses
    op.execute("""
        INSERT INTO requirement_response_documents (id, response_id, document_id, filename)
        SELECT gen_random_uuid(), rr.id, rr.document_id,
               COALESCE(dv.original_filename, d.title, 'document')
        FROM requirement_responses rr
        JOIN documents d ON d.id = rr.document_id
        LEFT JOIN document_versions dv ON dv.id = d.current_version_id
        WHERE rr.document_id IS NOT NULL;
    """)

    # 3. Add round_number to requirement_responses, backfill with window function, set NOT NULL, add unique constraint
    op.execute("ALTER TABLE requirement_responses ADD COLUMN round_number INTEGER;")
    op.execute("""
        WITH ranked AS (
          SELECT id, row_number() OVER (PARTITION BY requirement_id ORDER BY created_at, id) AS rn
          FROM requirement_responses)
        UPDATE requirement_responses r SET round_number = ranked.rn
        FROM ranked WHERE ranked.id = r.id;
    """)
    op.execute("ALTER TABLE requirement_responses ALTER COLUMN round_number SET NOT NULL;")
    op.create_unique_constraint("uq_req_response_round", "requirement_responses", ["requirement_id", "round_number"])

    # 4. Drop requirement_responses.document_id
    op.drop_column("requirement_responses", "document_id")

    # 5. Swap the status enum: ('pending', 'submitted', 'clarification_needed', 'accepted') -> ('open', 'closed')
    op.execute("CREATE TYPE request_status_new AS ENUM ('open', 'closed');")
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN status DROP DEFAULT;")
    op.execute("""
        ALTER TABLE requirement_requests
          ALTER COLUMN status TYPE request_status_new
          USING (CASE WHEN status::text = 'accepted' THEN 'closed' ELSE 'open' END)::request_status_new;
    """)
    op.execute("DROP TYPE request_status;")
    op.execute("ALTER TYPE request_status_new RENAME TO request_status;")
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN status SET DEFAULT 'open';")

    # 6. Backfill seq_number, then enforce NOT NULL
    op.execute("""
        WITH ranked AS (
          SELECT id, row_number() OVER (PARTITION BY engagement_id ORDER BY created_at, id) AS rn
          FROM requirement_requests WHERE seq_number IS NULL)
        UPDATE requirement_requests r
        SET seq_number = ranked.rn + COALESCE(
              (SELECT max(seq_number) FROM requirement_requests x
               WHERE x.engagement_id = r.engagement_id), 0)
        FROM ranked WHERE ranked.id = r.id;
    """)
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN seq_number SET NOT NULL;")

    # 7. Drop the 11 columns from requirement_requests and drop expected_format enum
    for col in (
        "title",
        "additional_details",
        "period_from",
        "period_to",
        "entity",
        "responsible_person_id",
        "expected_format",
        "auditor_notes",
        "parent_requirement_id",
        "clarification_note",
        "company_eta",
    ):
        op.drop_column("requirement_requests", col)
    op.execute("DROP TYPE IF EXISTS expected_format;")

    # 8. Add closed_by, closed_at to requirement_requests
    op.add_column("requirement_requests", sa.Column(
        "closed_by", UUID(as_uuid=True),
        sa.ForeignKey("auditors.id", ondelete="SET NULL"), nullable=True))
    op.add_column("requirement_requests", sa.Column(
        "closed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE requirement_requests SET closed_at = updated_at WHERE status = 'closed';")


def downgrade() -> None:
    # 1. Drop closed_at and closed_by from requirement_requests
    op.drop_column("requirement_requests", "closed_at")
    op.drop_column("requirement_requests", "closed_by")

    # 2. Re-create expected_format enum and add 11 dropped columns to requirement_requests
    op.execute("CREATE TYPE expected_format AS ENUM ('text', 'file', 'any');")
    op.add_column("requirement_requests", sa.Column("title", sa.String(255), server_default="Requirement", nullable=False))
    op.add_column("requirement_requests", sa.Column("additional_details", sa.Text(), nullable=True))
    op.add_column("requirement_requests", sa.Column("period_from", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("period_to", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("entity", sa.String(255), nullable=True))
    op.add_column("requirement_requests", sa.Column(
        "responsible_person_id", UUID(as_uuid=True),
        sa.ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("requirement_requests", sa.Column(
        "expected_format",
        sa.Enum("text", "file", "any", name="expected_format", create_type=False),
        server_default="any", nullable=False))
    op.add_column("requirement_requests", sa.Column("auditor_notes", sa.Text(), nullable=True))
    op.add_column("requirement_requests", sa.Column(
        "parent_requirement_id", UUID(as_uuid=True),
        sa.ForeignKey("requirement_requests.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("requirement_requests", sa.Column("clarification_note", sa.Text(), nullable=True))
    op.add_column("requirement_requests", sa.Column("company_eta", sa.Date(), nullable=True))

    # 3. Swap status enum back to 4 states
    op.execute("CREATE TYPE request_status_old AS ENUM ('pending', 'submitted', 'clarification_needed', 'accepted');")
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN status DROP DEFAULT;")
    op.execute("""
        ALTER TABLE requirement_requests
          ALTER COLUMN status TYPE request_status_old
          USING (CASE WHEN status::text = 'closed' THEN 'accepted' ELSE 'pending' END)::request_status_old;
    """)
    op.execute("DROP TYPE request_status;")
    op.execute("ALTER TYPE request_status_old RENAME TO request_status;")
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN status SET DEFAULT 'pending';")

    # 4. Make seq_number nullable again
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN seq_number DROP NOT NULL;")

    # 5. Restore document_id on requirement_responses from first join row
    op.add_column("requirement_responses", sa.Column(
        "document_id", UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True))
    op.execute("""
        UPDATE requirement_responses r
        SET document_id = sub.document_id
        FROM (
            SELECT DISTINCT ON (response_id) response_id, document_id
            FROM requirement_response_documents
            WHERE document_id IS NOT NULL
            ORDER BY response_id, id
        ) sub
        WHERE sub.response_id = r.id;
    """)

    # 6. Drop round_number constraint and column
    op.drop_constraint("uq_req_response_round", "requirement_responses", type_="unique")
    op.drop_column("requirement_responses", "round_number")

    # 7. Drop requirement_response_documents
    op.drop_table("requirement_response_documents")
