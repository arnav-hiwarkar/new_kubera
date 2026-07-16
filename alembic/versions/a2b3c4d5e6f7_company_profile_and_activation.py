"""company profile fields, admin activation key, and FK cascade for company delete

Revision ID: a2b3c4d5e6f7
Revises: a1a6d2477372
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'a1a6d2477372'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables whose company_id FK must cascade so a company can be hard-deleted.
# (document_types and ledger_groups already cascade — omitted.)
_CASCADE_TABLES = [
    "activity_logs",
    "assets",
    "audit_engagements",
    "buckets",
    "company_keys",
    "company_users",
    "custom_field_definitions",
    "documents",
    "kra_items",
    "meeting_records",
    "sales_records",
    "trial_balance_accounts",
]


def _fk_name(table: str) -> str:
    return f"{table}_company_id_fkey"


def upgrade() -> None:
    # --- Company profile columns ---
    op.add_column("companies", sa.Column("legal_name", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("cin", sa.String(length=21), nullable=True))
    op.add_column("companies", sa.Column("pan", sa.String(length=10), nullable=True))
    op.add_column("companies", sa.Column("gstin", sa.String(length=15), nullable=True))
    op.add_column("companies", sa.Column("tan", sa.String(length=10), nullable=True))
    op.add_column("companies", sa.Column("address_line1", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("address_line2", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("companies", sa.Column("state", sa.String(length=100), nullable=True))
    op.add_column("companies", sa.Column("pincode", sa.String(length=6), nullable=True))
    op.add_column("companies", sa.Column("contact_email", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("contact_phone", sa.String(length=20), nullable=True))
    op.add_column("companies", sa.Column("date_of_incorporation", sa.Date(), nullable=True))
    op.add_column("companies", sa.Column("website", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("industry", sa.String(length=255), nullable=True))
    op.add_column("companies", sa.Column("logo_path", sa.String(), nullable=True))
    op.add_column(
        "companies",
        sa.Column("profile_completed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # --- Admin activation columns ---
    op.add_column("companies", sa.Column("activation_key_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "companies",
        sa.Column("activation_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("activation_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Flip company_id FKs to ON DELETE CASCADE ---
    for table in _CASCADE_TABLES:
        op.drop_constraint(_fk_name(table), table, type_="foreignkey")
        op.create_foreign_key(
            _fk_name(table),
            table,
            "companies",
            ["company_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table in _CASCADE_TABLES:
        op.drop_constraint(_fk_name(table), table, type_="foreignkey")
        op.create_foreign_key(
            _fk_name(table),
            table,
            "companies",
            ["company_id"],
            ["id"],
        )

    for col in [
        "activation_used_at",
        "activation_expires_at",
        "activation_key_hash",
        "profile_completed",
        "logo_path",
        "industry",
        "website",
        "date_of_incorporation",
        "contact_phone",
        "contact_email",
        "pincode",
        "state",
        "city",
        "address_line2",
        "address_line1",
        "tan",
        "gstin",
        "pan",
        "cin",
        "legal_name",
    ]:
        op.drop_column("companies", col)
