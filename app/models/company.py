import uuid
import enum
from sqlalchemy import String, ForeignKey, LargeBinary, Enum as SAEnum
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

    company = relationship("Company", back_populates="users")
