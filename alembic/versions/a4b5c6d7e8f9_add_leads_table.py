"""add leads table

Revision ID: a4b5c6d7e8f9
Revises: 9f2c1a7d4e55
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a4b5c6d7e8f9"
down_revision = "9f2c1a7d4e55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create enum type if it does not exist
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lead_status') THEN
                CREATE TYPE lead_status AS ENUM ('new', 'contacted', 'converted', 'archived');
            END IF;
        END $$;
        """
    )

    # 2. Create leads table if it does not exist
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL,
            company_name VARCHAR(255),
            phone VARCHAR(50),
            entities_count INTEGER,
            notes TEXT,
            status lead_status NOT NULL DEFAULT 'new',
            ip_address VARCHAR(100),
            user_agent TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_email ON leads (email);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_status ON leads (status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_created_at ON leads (created_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS leads CASCADE;")
    op.execute("DROP TYPE IF EXISTS lead_status;")
