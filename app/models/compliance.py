import uuid
import enum
from datetime import date, datetime
from sqlalchemy import String, ForeignKey, Boolean, Date, DateTime, Enum as SAEnum
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
    # SET NULL so purging the company that owns the template document does not
    # block on a global (company_id IS NULL) document type pointing at it.
    template_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    metadata_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    due_date_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MeetingRecord(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "meeting_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Records imported from docVault arrive unclassified; the type is filled in later.
    doc_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_types.id", ondelete="CASCADE"), nullable=True)
    # Denormalised from the type: an untyped record still has to belong to exactly
    # one of the two compliance apps, so the domain cannot be derived by joining.
    domain: Mapped[ComplianceDomain] = mapped_column(SAEnum(ComplianceDomain, name="compliance_domain"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    structured_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # The date the document pertains to (meeting/filing period); drives month views.
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Set = archived. The record and its file are both retained; the linked docVault
    # document is archived alongside it.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The document's status and lock state immediately before we archived it, so
    # unarchiving puts both back exactly. Status is plain text rather than the enum:
    # it is a snapshot of a past value, not a live state.
    archived_document_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    archived_document_editable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    doc_type = relationship("DocumentType")
