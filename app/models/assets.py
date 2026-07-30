"""Fixed asset register: acquisitions, asset units, documents, tag sequences.

Two levels, because one invoice line for 50 chairs is one commercial event but
fifty things that get tagged, moved, verified and disposed of individually:

  AssetAcquisition — the invoice line. Supplier, invoice, PO, prices, GST, ITC
      treatment, freight/installation, and the derived cost totals. Entered once.
  Asset            — one physical unit. Tag, serial, location, custodian,
      depreciation inputs, its own allocated cost, its own lifecycle.

Almost every column is nullable on purpose. "Mandatory" is enforced per lifecycle
transition (see app/services/asset_validation.py), not per INSERT, so a user can
save a six-field draft and enrich it later without fighting the database.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Enum as SAEnum,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.asset_masters import (
    DEPRECIATION_METHOD_ENUM,
    ITC_TREATMENT_ENUM,
    DepreciationMethod,
    DiscountType,
    ItcTreatment,
)
from app.models.base import Base, TenantScopedMixin, TimestampMixin

# Money wide enough for plant and machinery. The previous register capped
# purchase_cost at Numeric(10,2) — about ten crore — which is too small.
Money = Numeric(15, 2)


class AssetLifecycleStatus(str, enum.Enum):
    """Drives required-field validation and the depreciation engine.

    draft       — freely editable, minimal validation, does not depreciate
    ready       — complete and submitted for approval
    capitalized — approved and on the books; cost is locked, depreciation runs
    disposed    — sold / scrapped / written off (P2)
    """

    draft = "draft"
    ready = "ready"
    capitalized = "capitalized"
    disposed = "disposed"


class AssetOperationalStatus(str, enum.Enum):
    """Where the asset is in its working life — orthogonal to lifecycle_status."""

    in_use = "in_use"
    idle = "idle"
    under_maintenance = "under_maintenance"
    in_storage = "in_storage"


class AssetCondition(str, enum.Enum):
    new = "new"
    good = "good"
    fair = "fair"
    poor = "poor"
    unusable = "unusable"


class AssetDocRole(str, enum.Enum):
    """What an attached file is. Invoice/PO/GRN/e-way/approval attach at the
    acquisition level and are shared by every unit; the rest are per unit."""

    invoice = "invoice"
    purchase_order = "purchase_order"
    grn = "grn"
    eway_bill = "eway_bill"
    approval = "approval"
    asset_photo = "asset_photo"
    serial_photo = "serial_photo"
    warranty = "warranty"
    insurance = "insurance"
    amc = "amc"
    test_certificate = "test_certificate"
    manual = "manual"
    customs = "customs"
    lease = "lease"
    other = "other"


ACQUISITION_DOC_ROLES = frozenset(
    {
        AssetDocRole.invoice,
        AssetDocRole.purchase_order,
        AssetDocRole.grn,
        AssetDocRole.eway_bill,
        AssetDocRole.approval,
        AssetDocRole.customs,
        AssetDocRole.lease,
    }
)

PHOTO_DOC_ROLES = frozenset({AssetDocRole.asset_photo, AssetDocRole.serial_photo})


class AssetAcquisition(Base, TimestampMixin, TenantScopedMixin):
    """One purchase line. Parents N asset units."""

    __tablename__ = "asset_acquisitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # --- Supplier ---
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    # Snapshot at capitalization: the register must not silently change when
    # someone edits the supplier master years later.
    supplier_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_gstin_snapshot: Mapped[str | None] = mapped_column(String(15), nullable=True)

    # --- Invoice / order ---
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    po_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Quantity and price ---
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    unit_basic_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    discount_type: Mapped[DiscountType] = mapped_column(
        SAEnum(DiscountType, name="discount_type"),
        nullable=False,
        default=DiscountType.amount,
        server_default="amount",
    )
    discount_value: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    # --- GST ---
    hsn_sac_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    gst_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Receiving branch decides the place of supply; falls back to the company state.
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_lookups.id", ondelete="SET NULL"), nullable=True
    )
    place_of_supply_state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cgst_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    sgst_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    igst_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # True when the user typed the GST amounts to tie to the invoice, so a later
    # recompute must not overwrite them.
    gst_amounts_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    gst_split_basis: Mapped[str | None] = mapped_column(String(24), nullable=True)
    itc_treatment: Mapped[ItcTreatment | None] = mapped_column(ITC_TREATMENT_ENUM, nullable=True)
    itc_eligible_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # --- Incidental capitalizable costs ---
    freight_cost: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    installation_cost: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    other_capitalizable_cost: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    # --- Derived. Recomputed on every write by asset_costing; stored so list and
    # report queries do not have to reproduce the arithmetic in SQL. ---
    gross_basic_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    net_basic_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    total_gst: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    recoverable_gst: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    capitalizable_gst: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    landed_cost: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    total_acquisition_outlay: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    per_unit_cost: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    # --- Conditional groups, revealed by these toggles ---
    is_imported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_leased: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    grn_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grn_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_challan_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    eway_bill_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    irn: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Import / customs
    bill_of_entry_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bill_of_entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    customs_duty: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    foreign_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    foreign_currency_value: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    # Lease / finance
    lease_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lessor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lease_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lease_rental: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    project_budget_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True
    )

    supplier = relationship("Supplier", lazy="joined")
    units = relationship(
        "Asset", back_populates="acquisition", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_asset_acquisitions_quantity_positive"),
    )


class Asset(Base, TimestampMixin, TenantScopedMixin):
    """One physical asset unit."""

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    acquisition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_acquisitions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # 1..N within the acquisition, so exploded siblings have a stable order.
    unit_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    # --- Identity ---
    asset_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # SET NULL rather than RESTRICT: a company purge cascades both this row and
    # its categories, and RESTRICT would deadlock that teardown.
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manufacturer_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manufacturer_serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Status ---
    lifecycle_status: Mapped[AssetLifecycleStatus] = mapped_column(
        SAEnum(AssetLifecycleStatus, name="asset_lifecycle_status"),
        nullable=False,
        default=AssetLifecycleStatus.draft,
        server_default="draft",
        index=True,
    )
    operational_status: Mapped[AssetOperationalStatus | None] = mapped_column(
        SAEnum(AssetOperationalStatus, name="asset_operational_status"), nullable=True
    )
    condition: Mapped[AssetCondition | None] = mapped_column(
        SAEnum(AssetCondition, name="asset_condition"), nullable=True
    )

    # --- Assignment ---
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_lookups.id", ondelete="SET NULL"), nullable=True
    )
    cost_centre_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_lookups.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_lookups.id", ondelete="SET NULL"), nullable=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_lookups.id", ondelete="SET NULL"), nullable=True
    )
    custodian_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True
    )
    # Real custodians — drivers, machine operators, security staff — often have no
    # login, so a name/code is accepted instead of a user reference.
    custodian_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    custodian_employee_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Dates ---
    available_for_use_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    capitalization_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Derived from start + months; stored so "warranties expiring this quarter" is
    # an index scan rather than a full recompute.
    warranty_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Companies Act depreciation inputs ---
    useful_life_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dep_method: Mapped[DepreciationMethod | None] = mapped_column(DEPRECIATION_METHOD_ENUM, nullable=True)
    residual_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    residual_value: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # Schedule II requires disclosure when a different useful life is used.
    useful_life_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Income Tax Act depreciation inputs ---
    it_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("it_asset_blocks.id", ondelete="SET NULL"), nullable=True
    )
    it_dep_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    it_put_to_use_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Cost ---
    # Allocated share of the acquisition's landed cost (plus P2 adjustments).
    original_cost: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # Cutover: for assets already owned when the company started using the
    # register, depreciation starts from these rather than from capitalization.
    is_pre_cutover: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    opening_accumulated_depreciation: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    opening_wdv: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    opening_it_wdv: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    # --- Conditional groups ---
    registration_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    engine_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    chassis_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    imei: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(32), nullable=True)
    technical_specs: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Informational link only. Full Schedule II component accounting (independent
    # useful lives with NBV rolling up to the parent) is deliberately out of scope.
    parent_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )

    custom_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)

    # --- Attribution ---
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    acquisition = relationship("AssetAcquisition", back_populates="units")
    category = relationship("AssetCategory", lazy="joined")
    it_block = relationship("ItAssetBlock", lazy="joined")


# Asset codes are unique per company, case-insensitively. Partial (WHERE NOT NULL)
# because a draft may not have been tagged yet.
Index(
    "uq_assets_company_code",
    Asset.company_id,
    func.lower(Asset.asset_code),
    unique=True,
    postgresql_where=Asset.asset_code.isnot(None),
)


class AssetDocument(Base, TimestampMixin, TenantScopedMixin):
    """Roled link between an asset (or its acquisition) and a DocVault document.

    Many-to-many with a role, replacing the single documents.id FK the old asset
    table carried. Exactly one of asset_id / acquisition_id is set.
    """

    __tablename__ = "asset_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    acquisition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_acquisitions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    doc_role: Mapped[AssetDocRole] = mapped_column(
        SAEnum(AssetDocRole, name="asset_doc_role"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "(asset_id IS NOT NULL) <> (acquisition_id IS NOT NULL)",
            name="ck_asset_documents_exactly_one_parent",
        ),
    )


class AssetCodeSequence(Base, TimestampMixin, TenantScopedMixin):
    """Per-prefix running counter for generated asset tags.

    An explicit counter rather than MAX(asset_code)+1: exploding a 50-unit
    acquisition allocates fifty codes at once, and two concurrent explodes reading
    the same MAX would collide. Allocation locks this row.
    """

    __tablename__ = "asset_code_sequences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


Index(
    "uq_asset_code_sequences_company_prefix",
    AssetCodeSequence.company_id,
    func.upper(AssetCodeSequence.prefix),
    unique=True,
)
