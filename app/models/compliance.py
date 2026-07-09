import uuid
import enum
from sqlalchemy import String, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, TenantScopedMixin


class ComplianceDomain(str, enum.Enum):
    secretarial = "secretarial"
    roc = "roc"


class DocumentType(Base, TimestampMixin):
    __tablename__ = "document_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    domain: Mapped[ComplianceDomain] = mapped_column(SAEnum(ComplianceDomain, name="compliance_domain"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    metadata_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    due_date_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MeetingRecord(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "meeting_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_types.id"), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    structured_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    doc_type = relationship("DocumentType")
