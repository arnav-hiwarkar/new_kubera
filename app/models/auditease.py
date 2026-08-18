import uuid
import enum
from decimal import Decimal
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
    """Which side of a *journal entry* line an amount sits on."""
    debit = "debit"
    credit = "credit"


class BalanceNature(str, enum.Enum):
    """The natural side of a *ledger group*. Deliberately a separate enum from
    EntryLineSide despite the identical member names: one describes a movement on
    an adjusting entry, the other describes where a group's balance normally sits.
    Do not merge them."""
    debit = "debit"
    credit = "credit"


class TBSignConvention(str, enum.Enum):
    """How the source trial balance encoded the sign of a balance.

    signed    - credit-natured balances are stored NEGATIVE (the column sums to 0)
    magnitude - every balance is stored POSITIVE; the side comes from the mapping
    explicit  - the source carries a Dr/Cr marker (or a Dr+Cr column pair)
    derived   - no closing column at all; closing = opening + debit - credit
    """
    signed = "signed"
    magnitude = "magnitude"
    explicit = "explicit"
    derived = "derived"

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
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ledger_groups.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    has_children: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # level 0: Top (Asset/Liab/Inc/Exp, seeded, read-only)
    # level 1: sub-group (company-owned)
    # level 2: sub-sub-group (company-owned)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    # Natural side of this group's balance. Set only on the seeded level-0 rows;
    # descendants inherit it by walking to the root (see ledger_groups.build_nature_map).
    # Nullable so a group whose root somehow lacks a nature is loudly unresolved
    # rather than silently contributing zero to the statements.
    nature: Mapped["BalanceNature | None"] = mapped_column(
        SAEnum(BalanceNature, name="balance_nature"), nullable=True
    )


class TrialBalanceAccount(Base, TimestampMixin, TenantScopedMixin):
    """One ledger of an engagement's trial balance.

    Sign model: `closing_net_debit` / `opening_net_debit` are the CANONICAL figures --
    a signed net debit (debit positive, credit negative) normalized at the import
    boundary. All accounting downstream of import reads only those.

    `opening_balance` / `debit` / `credit` / `closing_balance` are the verbatim
    as-imported SOURCE figures, kept for the audit trail and for the
    opening + debit - credit == closing cross-check. `debit`/`credit` are
    non-negative movement magnitudes. Do NOT compute statements from these.
    """
    __tablename__ = "trial_balance_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    ledger_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ledger_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mapped_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ledger_groups.id", ondelete="SET NULL"), nullable=True)

    # --- as-imported source figures (display + cross-check only) ---
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    debit: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    credit: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)

    # --- canonical signed net debit (the only figures the statements use) ---
    opening_net_debit: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=0, nullable=False, server_default="0"
    )
    closing_net_debit: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=0, nullable=False, server_default="0"
    )
    # True when the canonical sign was taken as a bare magnitude because neither an
    # explicit Dr/Cr marker nor a mapped group nature was available. Surfaced in the
    # UI so the user can confirm the convention rather than being silently guessed at.
    sign_unresolved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    # Did the source satisfy opening + debit - credit == closing? None when the
    # source did not supply every input needed to check.
    source_row_consistent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


# --- Engagements ---

class AuditEngagement(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "audit_engagements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_label: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[EngagementStatus] = mapped_column(SAEnum(EngagementStatus, name="engagement_status"), default=EngagementStatus.invited, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="CASCADE"), nullable=False)
    financial_year_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_years.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # How this engagement's trial balance encoded balance signs. NULL = no TB imported
    # yet, or a legacy engagement whose convention could not be proven and is pending
    # user confirmation.
    tb_sign_convention: Mapped["TBSignConvention | None"] = mapped_column(
        SAEnum(TBSignConvention, name="tb_sign_convention"), nullable=True
    )


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
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
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
    ledger_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trial_balance_accounts.id", ondelete="CASCADE"), nullable=False)
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
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    raised_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auditors.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, server_default="Requirement")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(SAEnum(RequestStatus, name="request_status"), default=RequestStatus.open, nullable=False)
    fulfilled_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)


class Query(Base, TimestampMixin):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
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
    attached_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    query = relationship("Query", back_populates="messages")


# --- Reports ---

class ReportTemplate(Base, TimestampMixin):
    __tablename__ = "report_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
