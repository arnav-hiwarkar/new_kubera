"""Financial Year entity for accounting and statutory depreciation periods."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin, TimestampMixin


class FinancialYearStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class FinancialYear(Base, TimestampMixin, TenantScopedMixin):
    """Financial Year definition for statutory accounting and depreciation runs."""

    __tablename__ = "financial_years"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FinancialYearStatus.open.value, server_default="open"
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("company_id", "label", name="uq_company_fy_label"),
        Index("ix_financial_years_company_status", "company_id", "status"),
    )
