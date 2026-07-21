import uuid
import enum
from datetime import date, datetime
from sqlalchemy import String, ForeignKey, LargeBinary, Enum as SAEnum, Boolean, Date, DateTime, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # --- Profile (Indian Pvt Ltd). Populated during onboarding. ---
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cin: Mapped[str | None] = mapped_column(String(21), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    tan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(6), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_incorporation: Mapped[date | None] = mapped_column(Date, nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # --- Admin activation (one-shot key, 48h TTL). ---
    activation_key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activation_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activation_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Archival (soft delete). When set, the company is archived: every login is
    # disabled and its name/admin email are freed for reuse, but the encrypted
    # tenant data is retained (it is unrecoverable once archived anyway). ---
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    users = relationship("CompanyUser", back_populates="company", lazy="selectin")
    keys = relationship("CompanyKey", back_populates="company", lazy="selectin")


class CompanyKey(Base, TimestampMixin):
    __tablename__ = "company_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    encrypted_kek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kek_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    company = relationship("Company", back_populates="keys")


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    employee = "employee"


class CompanyUser(Base, TimestampMixin):
    __tablename__ = "company_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Uniqueness is enforced only over LIVE accounts by a partial unique index
    # (see below), so a soft-deleted user's email can be reused by a new account.
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        default=UserRole.admin,
        nullable=False,
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="Unknown")
    designation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    # When set, the user has been soft-deleted: login is disabled and the email is
    # freed for reuse, but the row (and full_name) is retained so historical work
    # still shows who created it. Distinct from a merely deactivated (is_active=False)
    # user, which keeps its email.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accessible_modules: Mapped[list[str]] = mapped_column(JSONB, server_default='[]', nullable=False)

    company = relationship("Company", back_populates="users")


# Case-insensitive email uniqueness, restricted to live (non-deleted) accounts.
# Kept in sync with migration e1f2a3b4c5d6 so create_all (tests) matches prod.
Index(
    "uq_company_users_email_active",
    func.lower(CompanyUser.email),
    unique=True,
    postgresql_where=CompanyUser.deleted_at.is_(None),
)
