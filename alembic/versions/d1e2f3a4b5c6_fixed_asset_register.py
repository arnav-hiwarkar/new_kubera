"""Fixed asset register: rebuild assets, add masters, acquisitions, documents

Revision ID: d1e2f3a4b5c6
Revises: c8d9e0f1a2b3
Create Date: 2026-07-31

DESTRUCTIVE. The previous `assets` table was an 11-column tracker and is dropped
outright, along with its `asset_category` / `asset_status` enum types, rather than
migrated: `category` was a fixed 5-value enum with no room for a Schedule II tree,
there was no acquisition/unit split, and no cost or depreciation structure to map
onto. Confirmed with the product owner that no live company holds asset data.

`downgrade()` recreates the old table's *structure* so the schema round-trips, but
the rows are gone for good. Take a dump first if there is anything you care about.

Enum types are created explicitly up front (rather than implicitly by the first
create_table that mentions them) because depreciation_method and itc_treatment are
each used by two tables; letting SQLAlchemy emit CREATE TYPE per column would fail
on the second one.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d1e2f3a4b5c6"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


MONEY = sa.Numeric(15, 2)

NEW_ENUMS = {
    "it_block_class": ("building", "furniture", "plant_machinery", "intangible"),
    "depreciation_method": ("slm", "wdv"),
    "itc_treatment": ("eligible", "blocked", "partial"),
    "asset_lookup_kind": ("branch", "cost_centre", "department", "location"),
    "discount_type": ("amount", "percent"),
    "asset_lifecycle_status": ("draft", "ready", "capitalized", "disposed"),
    "asset_operational_status": ("in_use", "idle", "under_maintenance", "in_storage"),
    "asset_condition": ("new", "good", "fair", "poor", "unusable"),
    "asset_doc_role": (
        "invoice",
        "purchase_order",
        "grn",
        "eway_bill",
        "approval",
        "asset_photo",
        "serial_photo",
        "warranty",
        "insurance",
        "amc",
        "test_certificate",
        "manual",
        "customs",
        "lease",
        "other",
    ),
}


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created type; never emit CREATE TYPE again."""
    return postgresql.ENUM(*NEW_ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # --- Out with the old tracker ---
    op.drop_table("assets")
    for old in ("asset_category", "asset_status"):
        op.execute(f"DROP TYPE IF EXISTS {old}")

    for name, values in NEW_ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # --- Income Tax Act Appendix I blocks (seeded globally: company_id NULL) ---
    op.create_table(
        "it_asset_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dep_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("block_class", _enum("it_block_class"), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_it_asset_blocks_company_id", "it_asset_blocks", ["company_id"])
    # NULLS NOT DISTINCT so re-seeding collides with the existing global rows
    # instead of silently duplicating them (every global row has company_id NULL).
    op.execute(
        "CREATE UNIQUE INDEX uq_it_asset_blocks_company_code "
        "ON it_asset_blocks (company_id, lower(code)) NULLS NOT DISTINCT"
    )

    # --- Schedule II Part C category tree ---
    op.create_table(
        "asset_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_categories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column("default_useful_life_months", sa.Integer, nullable=True),
        sa.Column("default_dep_method", _enum("depreciation_method"), nullable=True),
        sa.Column("default_residual_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "default_it_block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("it_asset_blocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("default_itc_treatment", _enum("itc_treatment"), nullable=True),
        sa.Column("tag_prefix", sa.String(12), nullable=True),
        sa.Column("applicable_field_groups", postgresql.JSONB, nullable=True),
        sa.Column("schedule_ii_reference", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_asset_categories_company_id", "asset_categories", ["company_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_asset_categories_company_parent_name "
        "ON asset_categories (company_id, parent_id, lower(name)) NULLS NOT DISTINCT"
    )

    # --- Suppliers ---
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("pan", sa.String(10), nullable=True),
        sa.Column("contact_person", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("pincode", sa.String(6), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_suppliers_company_id", "suppliers", ["company_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_suppliers_company_code ON suppliers (company_id, lower(code))"
    )

    # --- Generic dimension values (branch / cost centre / department / location) ---
    op.create_table(
        "asset_lookups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", _enum("asset_lookup_kind"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(50), nullable=True),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_lookups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_asset_lookups_company_id", "asset_lookups", ["company_id"])
    op.create_index("ix_asset_lookups_kind", "asset_lookups", ["kind"])
    op.execute(
        "CREATE UNIQUE INDEX uq_asset_lookups_company_kind_name "
        "ON asset_lookups (company_id, kind, lower(name))"
    )

    # --- Acquisitions (one invoice line) ---
    op.create_table(
        "asset_acquisitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("supplier_name_snapshot", sa.String(255), nullable=True),
        sa.Column("supplier_gstin_snapshot", sa.String(15), nullable=True),
        sa.Column("invoice_number", sa.String(100), nullable=True),
        sa.Column("invoice_date", sa.Date, nullable=True),
        sa.Column("po_number", sa.String(100), nullable=True),
        sa.Column("purchase_date", sa.Date, nullable=True),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("unit_basic_price", MONEY, nullable=True),
        sa.Column("discount_type", _enum("discount_type"), nullable=False, server_default="amount"),
        sa.Column("discount_value", MONEY, nullable=True),
        sa.Column("hsn_sac_code", sa.String(10), nullable=True),
        sa.Column("gst_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_lookups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("place_of_supply_state_code", sa.String(2), nullable=True),
        sa.Column("cgst_amount", MONEY, nullable=True),
        sa.Column("sgst_amount", MONEY, nullable=True),
        sa.Column("igst_amount", MONEY, nullable=True),
        sa.Column("gst_amounts_overridden", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("gst_split_basis", sa.String(24), nullable=True),
        sa.Column("itc_treatment", _enum("itc_treatment"), nullable=True),
        sa.Column("itc_eligible_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("freight_cost", MONEY, nullable=True),
        sa.Column("installation_cost", MONEY, nullable=True),
        sa.Column("other_capitalizable_cost", MONEY, nullable=True),
        # Derived
        sa.Column("gross_basic_price", MONEY, nullable=True),
        sa.Column("discount_amount", MONEY, nullable=True),
        sa.Column("net_basic_price", MONEY, nullable=True),
        sa.Column("total_gst", MONEY, nullable=True),
        sa.Column("recoverable_gst", MONEY, nullable=True),
        sa.Column("capitalizable_gst", MONEY, nullable=True),
        sa.Column("landed_cost", MONEY, nullable=True),
        sa.Column("total_acquisition_outlay", MONEY, nullable=True),
        sa.Column("per_unit_cost", MONEY, nullable=True),
        # Conditional groups
        sa.Column("is_imported", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_leased", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("grn_number", sa.String(100), nullable=True),
        sa.Column("grn_date", sa.Date, nullable=True),
        sa.Column("delivery_challan_number", sa.String(100), nullable=True),
        sa.Column("eway_bill_number", sa.String(20), nullable=True),
        sa.Column("irn", sa.String(64), nullable=True),
        sa.Column("bill_of_entry_number", sa.String(50), nullable=True),
        sa.Column("bill_of_entry_date", sa.Date, nullable=True),
        sa.Column("customs_duty", MONEY, nullable=True),
        sa.Column("foreign_currency", sa.String(3), nullable=True),
        sa.Column("foreign_currency_value", MONEY, nullable=True),
        sa.Column("exchange_rate", sa.Numeric(12, 6), nullable=True),
        sa.Column("lease_type", sa.String(50), nullable=True),
        sa.Column("lessor_name", sa.String(255), nullable=True),
        sa.Column("lease_start_date", sa.Date, nullable=True),
        sa.Column("lease_end_date", sa.Date, nullable=True),
        sa.Column("lease_rental", MONEY, nullable=True),
        sa.Column("project_budget_reference", sa.String(255), nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_asset_acquisitions_quantity_positive"),
    )
    op.create_index("ix_asset_acquisitions_company_id", "asset_acquisitions", ["company_id"])

    # --- Asset units ---
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "acquisition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_acquisitions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("unit_index", sa.Integer, nullable=False, server_default="1"),
        sa.Column("asset_code", sa.String(50), nullable=True),
        sa.Column("asset_name", sa.String(255), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("manufacturer_contact", sa.String(255), nullable=True),
        sa.Column("brand_model", sa.String(255), nullable=True),
        sa.Column("manufacturer_serial_number", sa.String(255), nullable=True),
        sa.Column(
            "lifecycle_status",
            _enum("asset_lifecycle_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("operational_status", _enum("asset_operational_status"), nullable=True),
        sa.Column("condition", _enum("asset_condition"), nullable=True),
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_lookups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "cost_centre_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_lookups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_lookups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_lookups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "custodian_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("custodian_name", sa.String(255), nullable=True),
        sa.Column("custodian_employee_code", sa.String(50), nullable=True),
        sa.Column("available_for_use_date", sa.Date, nullable=True),
        sa.Column("capitalization_date", sa.Date, nullable=True),
        sa.Column("warranty_start_date", sa.Date, nullable=True),
        sa.Column("warranty_months", sa.Integer, nullable=True),
        sa.Column("warranty_expiry_date", sa.Date, nullable=True),
        sa.Column("useful_life_months", sa.Integer, nullable=True),
        sa.Column("dep_method", _enum("depreciation_method"), nullable=True),
        sa.Column("residual_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("residual_value", MONEY, nullable=True),
        sa.Column("useful_life_override_reason", sa.Text, nullable=True),
        sa.Column(
            "it_block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("it_asset_blocks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("it_dep_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("it_put_to_use_date", sa.Date, nullable=True),
        sa.Column("original_cost", MONEY, nullable=True),
        sa.Column("is_pre_cutover", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("opening_accumulated_depreciation", MONEY, nullable=True),
        sa.Column("opening_wdv", MONEY, nullable=True),
        sa.Column("opening_it_wdv", MONEY, nullable=True),
        sa.Column("registration_number", sa.String(50), nullable=True),
        sa.Column("engine_number", sa.String(50), nullable=True),
        sa.Column("chassis_number", sa.String(50), nullable=True),
        sa.Column("imei", sa.String(20), nullable=True),
        sa.Column("mac_address", sa.String(32), nullable=True),
        sa.Column("technical_specs", sa.Text, nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column(
            "parent_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("custom_fields", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "submitted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assets_company_id", "assets", ["company_id"])
    op.create_index("ix_assets_acquisition_id", "assets", ["acquisition_id"])
    op.create_index("ix_assets_category_id", "assets", ["category_id"])
    op.create_index("ix_assets_lifecycle_status", "assets", ["lifecycle_status"])
    # Partial: a draft may not have been tagged yet.
    op.execute(
        "CREATE UNIQUE INDEX uq_assets_company_code ON assets (company_id, lower(asset_code)) "
        "WHERE asset_code IS NOT NULL"
    )

    # --- Roled document links ---
    op.create_table(
        "asset_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "acquisition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_acquisitions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_role", _enum("asset_doc_role"), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(asset_id IS NOT NULL) <> (acquisition_id IS NOT NULL)",
            name="ck_asset_documents_exactly_one_parent",
        ),
    )
    op.create_index("ix_asset_documents_company_id", "asset_documents", ["company_id"])
    op.create_index("ix_asset_documents_asset_id", "asset_documents", ["asset_id"])
    op.create_index("ix_asset_documents_acquisition_id", "asset_documents", ["acquisition_id"])

    # --- Tag counters ---
    op.create_table(
        "asset_code_sequences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prefix", sa.String(24), nullable=False),
        sa.Column("next_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_asset_code_sequences_company_id", "asset_code_sequences", ["company_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_asset_code_sequences_company_prefix "
        "ON asset_code_sequences (company_id, upper(prefix))"
    )

    # --- Seed the statutory reference data ---
    # Imports the same IT_BLOCKS / CATEGORY_TREE constants the app uses, so the
    # figures are defined once. Idempotent, so a later upgrade re-run corrects
    # rates in place rather than duplicating rows.
    from app.services.asset_seed import seed_global_asset_reference_data_sync

    seed_global_asset_reference_data_sync(bind)


def downgrade() -> None:
    bind = op.get_bind()

    for table in (
        "asset_code_sequences",
        "asset_documents",
        "assets",
        "asset_acquisitions",
        "asset_lookups",
        "suppliers",
        "asset_categories",
        "it_asset_blocks",
    ):
        op.drop_table(table)

    for name in NEW_ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")

    # Recreate the old tracker's structure so the schema round-trips. Its rows are
    # not recoverable from here.
    old_category = postgresql.ENUM(
        "hardware", "software", "furniture", "vehicle", "other", name="asset_category"
    )
    old_status = postgresql.ENUM("active", "maintenance", "retired", name="asset_status")
    old_category.create(bind, checkfirst=True)
    old_status.create(bind, checkfirst=True)

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_name", sa.String(255), nullable=False),
        sa.Column("serial_number", sa.String(255), nullable=True),
        sa.Column(
            "category",
            postgresql.ENUM(
                "hardware", "software", "furniture", "vehicle", "other",
                name="asset_category", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "maintenance", "retired", name="asset_status", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("purchase_date", sa.Date, nullable=True),
        sa.Column("purchase_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("depreciation_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "custodian_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("custom_fields", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assets_company_id", "assets", ["company_id"])
