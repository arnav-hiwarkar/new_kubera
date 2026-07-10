import uuid
import enum
from sqlalchemy import String, ForeignKey, Boolean, Integer, Date, Numeric, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, TenantScopedMixin

class SalesStatus(str, enum.Enum):
    lead = "lead"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"

class SalesRecord(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "sales_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_service: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[SalesStatus] = mapped_column(SAEnum(SalesStatus, name="sales_status"), default=SalesStatus.lead, nullable=False)
    closing_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=False)
    
    custom_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
