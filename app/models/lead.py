import uuid
import enum
from sqlalchemy import String, Integer, Text, Enum as SAEnum, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LeadStatus(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    converted = "converted"
    archived = "archived"


class Lead(Base, TimestampMixin):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entities_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        SAEnum(LeadStatus, name="lead_status"),
        nullable=False,
        default=LeadStatus.new,
        server_default=LeadStatus.new.value,
        index=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_leads_email_lower", func.lower(email)),
        Index("ix_leads_created_at_desc", "created_at"),
    )
