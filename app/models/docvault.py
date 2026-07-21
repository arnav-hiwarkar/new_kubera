import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, Boolean, Enum as SAEnum, Integer, BigInteger, LargeBinary, ARRAY, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, TenantScopedMixin


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    pending_approval = "pending_approval"
    action_required = "action_required"
    verified = "verified"
    submitted = "submitted"
    overdue = "overdue"
    archived = "archived"


class BucketVisibility(str, enum.Enum):
    # Visible to every company user who has DocVault module access.
    everyone = "everyone"
    # Visible only to users explicitly granted access (see BucketAccessGrant),
    # plus the bucket's creator and company admins.
    restricted = "restricted"


class Bucket(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "buckets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable so system buckets (e.g. "Audit Attachments") can be created during
    # an auditor's action, when there is no company user to attribute.
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)
    visibility: Mapped[BucketVisibility] = mapped_column(
        SAEnum(BucketVisibility, name="bucket_visibility"),
        default=BucketVisibility.everyone,
        server_default="everyone",
        nullable=False,
    )

    access_grants = relationship(
        "BucketAccessGrant", back_populates="bucket", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def access_user_ids(self) -> list[uuid.UUID]:
        """Company-user ids explicitly granted access (populated from access_grants,
        which is eager-loaded). Empty for `everyone` buckets."""
        return [g.company_user_id for g in self.access_grants]


class BucketAccessGrant(Base):
    """A company user explicitly granted access to a `restricted` bucket."""
    __tablename__ = "bucket_access_grants"
    __table_args__ = (UniqueConstraint("bucket_id", "company_user_id", name="uq_bucket_access_grant"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bucket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("buckets.id", ondelete="CASCADE"), nullable=False, index=True)
    company_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="CASCADE"), nullable=False, index=True)

    bucket = relationship("Bucket", back_populates="access_grants")


class Document(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_versions.id", use_alter=True, name="fk_documents_current_version_id"), nullable=True)
    bucket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("buckets.id"), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(SAEnum(DocumentStatus, name="document_status"), default=DocumentStatus.uploaded, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True) # Will point to DocumentType in later phases
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Nullable for auditor-uploaded audit attachments (no company_users row for an auditor).
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)

    versions = relationship("DocumentVersion", back_populates="document", foreign_keys="[DocumentVersion.document_id]")


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dek_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    document = relationship("Document", back_populates="versions", foreign_keys=[document_id])


class PrincipalType(str, enum.Enum):
    company_user = "company_user"
    auditor = "auditor"


class DocumentAccessOverride(Base):
    __tablename__ = "document_access_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    principal_type: Mapped[PrincipalType] = mapped_column(SAEnum(PrincipalType, name="principal_type_override"), nullable=False)
    principal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    permission_level: Mapped[str] = mapped_column(String(50), default="read", nullable=False)
