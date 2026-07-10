import uuid
import enum
from sqlalchemy import String, ForeignKey, Boolean, Integer, Numeric, Text, Date, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, TenantScopedMixin

class KRAStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    in_progress = "in_progress"
    review_submitted = "review_submitted"
    completed = "completed"
    rejected = "rejected"

class KRAItem(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "kra_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    weightage: Mapped[Numeric] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    target_metric: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    cycle: Mapped[str] = mapped_column(String(255), nullable=False)
    
    status: Mapped[KRAStatus] = mapped_column(SAEnum(KRAStatus, name="kra_status"), default=KRAStatus.draft, nullable=False)
    
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=False)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)

    employee_self_rating: Mapped[Numeric | None] = mapped_column(Numeric(5, 2), nullable=True)
    employee_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    manager_rating: Mapped[Numeric | None] = mapped_column(Numeric(5, 2), nullable=True)
    manager_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
