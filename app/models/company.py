import uuid
import enum
from sqlalchemy import String, ForeignKey, LargeBinary, Enum as SAEnum, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    users = relationship("CompanyUser", back_populates="company", lazy="selectin")
    keys = relationship("CompanyKey", back_populates="company", lazy="selectin")


class CompanyKey(Base, TimestampMixin):
    __tablename__ = "company_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
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
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
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

    company = relationship("Company", back_populates="users")
