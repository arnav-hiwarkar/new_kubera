"""add leads table

Revision ID: a4b5c6d7e8f9
Revises: 9f2c1a7d4e55
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "a4b5c6d7e8f9"
down_revision = "9f2c1a7d4e55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    lead_status_enum = sa.Enum("new", "contacted", "converted", "archived", name="lead_status")
    lead_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "leads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("entities_count", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("new", "contacted", "converted", "archived", name="lead_status"), nullable=False, server_default="new"),
        sa.Column("ip_address", sa.String(100), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_created_at", "leads", [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_table("leads")
    op.execute("DROP TYPE IF EXISTS lead_status")
