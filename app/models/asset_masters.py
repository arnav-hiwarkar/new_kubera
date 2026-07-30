"""Master data for the fixed-asset register.

Three "rich" tables where the attributes matter — asset_categories (which carries
the depreciation defaults that keep the create form short), suppliers, and
it_asset_blocks — plus one generic asset_lookups table with a `kind` discriminator
standing in for branch / cost centre / department / location / condition.

asset_categories and it_asset_blocks follow the DocumentType / LedgerGroup
precedent: a NULL company_id means "seeded global row, shared by every tenant".
Those rows are read-only to companies; a company extends the set by creating its
own rows instead of editing the shared ones.
"""
import enum
import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Enum as SAEnum,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin, TimestampMixin


class DepreciationMethod(str, enum.Enum):
    slm = "slm"  # Straight Line Method
    wdv = "wdv"  # Written Down Value


class ItcTreatment(str, enum.Enum):
    """Input Tax Credit treatment. Drives whether GST is capitalized into the
    depreciation base: eligible GST is recoverable and excluded from cost;
    blocked GST (Sec 17(5)) is capitalized; partial splits by eligible %."""

    eligible = "eligible"
    blocked = "blocked"
    partial = "partial"


class DiscountType(str, enum.Enum):
    amount = "amount"
    percent = "percent"


class ItBlockClass(str, enum.Enum):
    """Appendix I groupings, used to order the block-wise tax summary."""

    building = "building"
    furniture = "furniture"
    plant_machinery = "plant_machinery"
    intangible = "intangible"


class AssetLookupKind(str, enum.Enum):
    """Company-defined dimension values. Deliberately excludes condition: that is
    a small closed ordinal scale (AssetCondition) that reports and physical
    verification need to sort on, so it is an enum rather than free-form data."""

    branch = "branch"
    cost_centre = "cost_centre"
    department = "department"
    location = "location"


# Shared SAEnum instances. Both asset_categories and assets carry a depreciation
# method / ITC treatment; reusing one instance per Postgres type name means
# create_all emits a single CREATE TYPE instead of colliding on the second table.
DEPRECIATION_METHOD_ENUM = SAEnum(DepreciationMethod, name="depreciation_method")
ITC_TREATMENT_ENUM = SAEnum(ItcTreatment, name="itc_treatment")


# Unit-level optional field groups a category can declare as applicable. Kept as
# JSONB strings rather than an enum so adding a group needs no migration.
FIELD_GROUPS = (
    "registration",       # registration / engine / chassis number
    "network_ids",        # IMEI / MAC address
    "insurance",
    "amc",
    "warranty",
    "test_certificate",   # installation & testing certificates
    "manual",             # technical specifications and manuals
)


class ItAssetBlock(Base, TimestampMixin):
    """Income Tax Act Appendix I block. Seeded globally (company_id IS NULL)."""

    __tablename__ = "it_asset_blocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dep_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    block_class: Mapped[ItBlockClass] = mapped_column(
        SAEnum(ItBlockClass, name="it_block_class"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


# NULLS NOT DISTINCT so the seeded global rows (company_id IS NULL) collide with
# each other on re-seed instead of silently duplicating. Mirrored in the migration
# so create_all (tests) matches prod.
Index(
    "uq_it_asset_blocks_company_code",
    ItAssetBlock.company_id,
    func.lower(ItAssetBlock.code),
    unique=True,
    postgresql_nulls_not_distinct=True,
)


class AssetCategory(Base, TimestampMixin):
    """Two-level asset category tree. A leaf carries the statutory defaults that
    auto-fill the asset form, so the user sees six fields instead of thirty-seven.
    Seeded globally from Schedule II Part C (company_id IS NULL)."""

    __tablename__ = "asset_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_categories.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Defaults inherited by assets in this category (all overridable) ---
    default_useful_life_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_dep_method: Mapped[DepreciationMethod | None] = mapped_column(
        DEPRECIATION_METHOD_ENUM, nullable=True
    )
    default_residual_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    default_it_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("it_asset_blocks.id", ondelete="SET NULL"), nullable=True
    )
    default_itc_treatment: Mapped[ItcTreatment | None] = mapped_column(
        ITC_TREATMENT_ENUM, nullable=True
    )
    tag_prefix: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # Which optional unit-level field groups this category makes relevant.
    applicable_field_groups: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    # Schedule II Part C class this was derived from, for the disclosure note.
    schedule_ii_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    parent = relationship("AssetCategory", remote_side=[id], backref="children")
    it_block = relationship("ItAssetBlock", lazy="joined")


Index(
    "uq_asset_categories_company_parent_name",
    AssetCategory.company_id,
    AssetCategory.parent_id,
    func.lower(AssetCategory.name),
    unique=True,
    postgresql_nulls_not_distinct=True,
)


class Supplier(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    # First two characters of the GSTIN. Denormalized because it is what the
    # CGST/SGST-vs-IGST decision actually compares.
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)

    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(6), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


Index(
    "uq_suppliers_company_code",
    Supplier.company_id,
    func.lower(Supplier.code),
    unique=True,
)


class AssetLookup(Base, TimestampMixin, TenantScopedMixin):
    """Generic per-company dimension value, discriminated by `kind`.

    `state`/`state_code`/`gstin` are only meaningful for kind='branch', where a
    branch registered in another state changes the place of supply and therefore
    whether an invoice is CGST+SGST or IGST. `parent_id` is only used by
    kind='location' to model site -> building -> floor -> room.
    """

    __tablename__ = "asset_lookups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[AssetLookupKind] = mapped_column(
        SAEnum(AssetLookupKind, name="asset_lookup_kind"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_lookups.id", ondelete="SET NULL"), nullable=True
    )
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    parent = relationship("AssetLookup", remote_side=[id])


Index(
    "uq_asset_lookups_company_kind_name",
    AssetLookup.company_id,
    AssetLookup.kind,
    func.lower(AssetLookup.name),
    unique=True,
)
