"""requirements lifecycle

Revision ID: 9f2c1a7d4e55
Revises: b5d8f2a6c9e1
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "9f2c1a7d4e55"
down_revision = "b5d8f2a6c9e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Status enum swap. PG cannot USE a newly added enum value in the same
    #    transaction that adds it, so flip the column to varchar first.
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN status TYPE varchar USING status::text")
    op.execute("UPDATE requirement_requests SET status = 'pending' WHERE status = 'open'")
    op.execute("UPDATE requirement_requests SET status = 'accepted' WHERE status = 'fulfilled'")
    op.execute("DROP TYPE IF EXISTS request_status")
    op.execute("CREATE TYPE request_status AS ENUM "
               "('pending', 'submitted', 'clarification_needed', 'accepted')")
    op.execute("ALTER TABLE requirement_requests "
               "ALTER COLUMN status TYPE request_status USING status::request_status")

    # 2. Metadata columns.
    op.add_column("requirement_requests", sa.Column("seq_number", sa.Integer(), nullable=True))
    op.add_column("requirement_requests", sa.Column("priority", sa.Integer(), server_default="1", nullable=False))
    op.add_column("requirement_requests", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("company_eta", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("additional_details", sa.Text(), nullable=True))
    op.add_column("requirement_requests", sa.Column("period_from", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("period_to", sa.Date(), nullable=True))
    op.add_column("requirement_requests", sa.Column("entity", sa.String(255), nullable=True))
    op.add_column("requirement_requests", sa.Column(
        "responsible_person_id", UUID(as_uuid=True),
        sa.ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True))
    # op.add_column does not emit CREATE TYPE for an inline sa.Enum, so the type
    # is created explicitly here and dropped in downgrade().
    op.execute("CREATE TYPE expected_format AS ENUM ('text', 'file', 'any')")
    op.add_column("requirement_requests", sa.Column(
        "expected_format",
        sa.Enum("text", "file", "any", name="expected_format", create_type=False),
        server_default="any", nullable=False))
    op.add_column("requirement_requests", sa.Column("auditor_notes", sa.Text(), nullable=True))
    op.add_column("requirement_requests", sa.Column(
        "parent_requirement_id", UUID(as_uuid=True),
        sa.ForeignKey("requirement_requests.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("requirement_requests", sa.Column("clarification_note", sa.Text(), nullable=True))

    # 3. Backfill per-engagement sequence numbers (stable created-order), then lock it down.
    op.execute("""
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY engagement_id ORDER BY created_at, id) AS rn
            FROM requirement_requests
        )
        UPDATE requirement_requests r SET seq_number = n.rn FROM numbered n WHERE n.id = r.id
    """)
    op.create_unique_constraint(
        "uq_requirement_seq", "requirement_requests", ["engagement_id", "seq_number"])

    # 4. Responses table first, THEN legacy fulfilled documents become the first
    #    response row (the insert references the table), then drop the column.
    op.create_table(
        "requirement_responses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("requirement_id", UUID(as_uuid=True),
                  sa.ForeignKey("requirement_requests.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("responded_by", UUID(as_uuid=True),
                  sa.ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("text_answer", sa.Text(), nullable=True),
        sa.Column("document_id", UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("""
        INSERT INTO requirement_responses
            (id, requirement_id, responded_by, text_answer, document_id, created_at)
        SELECT gen_random_uuid(), id, NULL, NULL, fulfilled_document_id, updated_at
        FROM requirement_requests
        WHERE fulfilled_document_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM requirement_responses rr
              WHERE rr.requirement_id = requirement_requests.id)
    """)
    op.drop_column("requirement_requests", "fulfilled_document_id")

    # 6. Query linkage.
    op.add_column("queries", sa.Column(
        "requirement_id", UUID(as_uuid=True),
        sa.ForeignKey("requirement_requests.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("queries", "requirement_id")
    op.add_column("requirement_requests", sa.Column(
        "fulfilled_document_id", UUID(as_uuid=True),
        sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True))
    op.execute("""
        UPDATE requirement_requests r SET fulfilled_document_id = sub.document_id
        FROM (
            SELECT DISTINCT ON (requirement_id) requirement_id, document_id
            FROM requirement_responses WHERE document_id IS NOT NULL
            ORDER BY requirement_id, created_at DESC
        ) sub WHERE sub.requirement_id = r.id
    """)
    op.drop_table("requirement_responses")
    op.drop_constraint("uq_requirement_seq", "requirement_requests", type_="unique")
    for col in ("seq_number", "priority", "due_date", "company_eta", "additional_details",
                "period_from", "period_to", "entity", "responsible_person_id",
                "expected_format", "auditor_notes", "parent_requirement_id",
                "clarification_note"):
        op.drop_column("requirement_requests", col)
    op.execute("DROP TYPE IF EXISTS expected_format")
    op.execute("ALTER TABLE requirement_requests ALTER COLUMN status TYPE varchar USING status::text")
    op.execute("UPDATE requirement_requests SET status = 'open' WHERE status = 'pending'")
    op.execute("UPDATE requirement_requests SET status = 'fulfilled' "
               "WHERE status IN ('submitted', 'clarification_needed', 'accepted')")
    op.execute("DROP TYPE request_status")
    op.execute("CREATE TYPE request_status AS ENUM ('open', 'fulfilled')")
    op.execute("ALTER TABLE requirement_requests "
               "ALTER COLUMN status TYPE request_status USING status::request_status")
