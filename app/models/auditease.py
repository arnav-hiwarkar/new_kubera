import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, Boolean, Enum as SAEnum, Integer, Numeric, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, TenantScopedMixin


class EngagementStatus(str, enum.Enum):
    draft = "draft"
    invited = "invited"
    active = "active"
    closed = "closed"

class GrantStatus(str, enum.Enum):
    invited = "invited"
    accepted = "accepted"
    revoked = "revoked"

class AuditEntryStatus(str, enum.Enum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"

class EntryLineSide(str, enum.Enum):
    debit = "debit"
    credit = "credit"

class RequestStatus(str, enum.Enum):
    open = "open"
    fulfilled = "fulfilled"

class QueryStatus(str, enum.Enum):
    open = "open"
    closed = "closed"

class SenderType(str, enum.Enum):
    company_user = "company_user"
    auditor = "auditor"


# --- Trial Balance & Ledger ---

class LedgerGroup(Base):
    __tablename__ = "ledger_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True) # Null for seeded defaults
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ledger_groups.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    has_children: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # level 0: Top (Asset/Liab/Inc/Exp, seeded, read-only)
    # level 1: sub-group (company-owned)
    # level 2: sub-sub-group (company-owned)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")


class TrialBalanceAccount(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "trial_balance_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    ledger_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ledger_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mapped_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ledger_groups.id"), nullable=True)
    
    opening_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    debit: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    credit: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    closing_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0)


# --- Engagements ---

class AuditEngagement(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "audit_engagements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_label: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[EngagementStatus] = mapped_column(SAEnum(EngagementStatus, name="engagement_status"), default=EngagementStatus.invited, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=False)


class AuditorEngagementGrant(Base):
    __tablename__ = "auditor_engagement_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auditor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auditors.id", ondelete="CASCADE"), nullable=False, index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[GrantStatus] = mapped_column(SAEnum(GrantStatus, name="grant_status"), default=GrantStatus.invited, nullable=False)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PendingAuditorInvite(Base):
    """An invite to an email that has no auditor account yet. Converted to an
    AuditorEngagementGrant automatically when an auditor registers with this email."""
    __tablename__ = "pending_auditor_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


# --- Audit Entries ---

class AuditEntry(Base, TimestampMixin):
    __tablename__ = "audit_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id"), nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auditors.id"), nullable=False)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AuditEntryStatus] = mapped_column(SAEnum(AuditEntryStatus, name="audit_entry_status"), default=AuditEntryStatus.proposed, nullable=False)
    rejection_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    lines = relationship("AuditEntryLine", back_populates="entry", cascade="all, delete-orphan")


class AuditEntryLine(Base):
    __tablename__ = "audit_entry_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_entries.id", ondelete="CASCADE"), nullable=False)
    ledger_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trial_balance_accounts.id"), nullable=False)
    side: Mapped[EntryLineSide] = mapped_column(SAEnum(EntryLineSide, name="entry_line_side"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)

    entry = relationship("AuditEntry", back_populates="lines")
    # The trial-balance ledger this line adjusts. Read paths eager-load it so the
    # API can surface the ledger name/code (raise if accessed unloaded in async).
    ledger = relationship("TrialBalanceAccount", lazy="raise")


# --- Requests & Queries ---

class RequirementRequest(Base, TimestampMixin):
    __tablename__ = "requirement_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id"), nullable=False, index=True)
    raised_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auditors.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, server_default="Requirement")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(SAEnum(RequestStatus, name="request_status"), default=RequestStatus.open, nullable=False)
    fulfilled_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)


class Query(Base, TimestampMixin):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id"), nullable=False, index=True)
    opened_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auditors.id"), nullable=False)
    status: Mapped[QueryStatus] = mapped_column(SAEnum(QueryStatus, name="query_status"), default=QueryStatus.open, nullable=False)

    messages = relationship("QueryMessage", back_populates="query", cascade="all, delete-orphan", order_by="QueryMessage.created_at")


class QueryMessage(Base):
    __tablename__ = "query_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False)
    sender_type: Mapped[SenderType] = mapped_column(SAEnum(SenderType, name="sender_type"), nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False) # ID of CompanyUser or Auditor
    text: Mapped[str] = mapped_column(Text, nullable=False)
    attached_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    query = relationship("Query", back_populates="messages")


# --- Reports ---

class ReportTemplate(Base, TimestampMixin):
    __tablename__ = "report_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
