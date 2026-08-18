"""financial years, asset disposals, and depreciation runs

Revision ID: f3a5b7c9d1e2
Revises: e2c4a6b8d0f1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f3a5b7c9d1e2"
down_revision = "b5e1d84c07a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. financial_years table
    op.create_table(
        "financial_years",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("company_id", "label", name="uq_company_fy_label"),
    )
    op.create_index("ix_financial_years_company_status", "financial_years", ["company_id", "status"])

    # 2. Add financial_year_id to audit_engagements
    op.add_column("audit_engagements", sa.Column("financial_year_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_audit_engagements_financial_year_id",
        "audit_engagements",
        "financial_years",
        ["financial_year_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_audit_engagements_financial_year_id", "audit_engagements", ["financial_year_id"])

    # 3. Add disposal columns to assets
    op.add_column("assets", sa.Column("disposal_date", sa.Date(), nullable=True))
    op.add_column("assets", sa.Column("disposal_type", sa.String(50), nullable=True))
    op.add_column("assets", sa.Column("sale_proceeds", sa.Numeric(15, 2), nullable=True))
    op.add_column("assets", sa.Column("buyer_name", sa.String(255), nullable=True))
    op.add_column("assets", sa.Column("disposal_invoice_no", sa.String(50), nullable=True))
    op.add_column("assets", sa.Column("disposal_remarks", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("disposal_gain_loss", sa.Numeric(15, 2), nullable=True))
    op.add_column("assets", sa.Column("disposal_it_proceeds", sa.Numeric(15, 2), nullable=True))

    # 4. depreciation_runs table
    op.create_table(
        "depreciation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("financial_year_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("financial_years.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("run_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_depreciation_runs_status", "depreciation_runs", ["status"])

    # 5. asset_depreciation_lines table
    op.create_table(
        "asset_depreciation_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("depreciation_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("method", sa.String(10), nullable=False, server_default="SLM"),
        sa.Column("opening_gross_block", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("additions", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("disposals", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("closing_gross_block", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("opening_accumulated_depreciation", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("depreciation_for_year", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("disposal_accumulated_depreciation", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("closing_accumulated_depreciation", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("opening_carrying_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("closing_carrying_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("residual_value", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("remaining_useful_life_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effective_rate_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("is_part_year", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_disposed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("gain_loss_on_disposal", sa.Numeric(15, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # 6. it_block_depreciation_lines table
    op.create_table(
        "it_block_depreciation_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("depreciation_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("it_block_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("it_asset_blocks.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("block_name", sa.String(255), nullable=False),
        sa.Column("prescribed_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("opening_wdv", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("additions_more_than_180", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("additions_less_than_180", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("realized_from_sales", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("balance_before_depreciation", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("depreciation_full_rate", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("depreciation_half_rate", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("total_depreciation", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("closing_wdv", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("capital_gain_or_loss", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("has_stcg", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_stcl", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("it_block_depreciation_lines")
    op.drop_table("asset_depreciation_lines")
    op.drop_table("depreciation_runs")
    op.drop_column("assets", "disposal_it_proceeds")
    op.drop_column("assets", "disposal_gain_loss")
    op.drop_column("assets", "disposal_remarks")
    op.drop_column("assets", "disposal_invoice_no")
    op.drop_column("assets", "buyer_name")
    op.drop_column("assets", "sale_proceeds")
    op.drop_column("assets", "disposal_type")
    op.drop_column("assets", "disposal_date")
    op.drop_index("ix_audit_engagements_financial_year_id", table_name="audit_engagements")
    op.drop_constraint("fk_audit_engagements_financial_year_id", "audit_engagements", type_="foreignkey")
    op.drop_column("audit_engagements", "financial_year_id")
    op.drop_index("ix_financial_years_company_status", table_name="financial_years")
    op.drop_table("financial_years")
