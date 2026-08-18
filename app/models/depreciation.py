"""Depreciation runs and calculation result tables for Companies Act and Income Tax."""
import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin, TimestampMixin

Money = Numeric(15, 2)


class DepreciationRunStatus(str, enum.Enum):
    draft = "draft"
    finalized = "finalized"


class DepreciationBook(str, enum.Enum):
    companies_act = "companies_act"
    income_tax = "income_tax"


class DepreciationRun(Base, TimestampMixin, TenantScopedMixin):
    """Execution run of depreciation calculation for a financial year."""

    __tablename__ = "depreciation_runs"
    __table_args__ = (
        Index(
            "uq_depreciation_runs_company_fy_book_finalized",
            "company_id",
            "financial_year_id",
            "book",
            unique=True,
            postgresql_where=text("status = 'finalized'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    financial_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_years.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DepreciationBook.companies_act.value, server_default="companies_act"
    )
    run_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DepreciationRunStatus.draft.value, server_default="draft", index=True
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    financial_year = relationship("FinancialYear", lazy="joined")
    lines = relationship("AssetDepreciationLine", back_populates="run", cascade="all, delete-orphan")
    it_lines = relationship("ItBlockDepreciationLine", back_populates="run", cascade="all, delete-orphan")


class AssetDepreciationLine(Base, TimestampMixin):
    """Companies Act Schedule II asset-wise computed depreciation line."""

    __tablename__ = "asset_depreciation_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("depreciation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    method: Mapped[str] = mapped_column(String(10), nullable=False, default="SLM")
    opening_gross_block: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    additions: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    disposals: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    closing_gross_block: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))

    opening_accumulated_depreciation: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    depreciation_for_year: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    disposal_accumulated_depreciation: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    closing_accumulated_depreciation: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))

    opening_carrying_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    closing_carrying_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    residual_value: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    remaining_useful_life_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_rate_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))

    is_part_year: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_disposed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gain_loss_on_disposal: Mapped[Decimal | None] = mapped_column(Money, nullable=True)

    run = relationship("DepreciationRun", back_populates="lines")
    asset = relationship("Asset", lazy="joined")


class ItBlockDepreciationLine(Base, TimestampMixin):
    """Income Tax Act Section 32 block-wise computed depreciation line."""

    __tablename__ = "it_block_depreciation_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("depreciation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    it_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("it_asset_blocks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    block_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prescribed_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))

    opening_wdv: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    additions_more_than_180: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    additions_less_than_180: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    realized_from_sales: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    balance_before_depreciation: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))

    depreciation_full_rate: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    depreciation_half_rate: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    total_depreciation: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    closing_wdv: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    capital_gain_or_loss: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    has_stcg: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_stcl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    run = relationship("DepreciationRun", back_populates="it_lines")
    it_block = relationship("ItAssetBlock", lazy="joined")
