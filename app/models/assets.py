import uuid
import enum
from sqlalchemy import String, ForeignKey, Boolean, Integer, Date, Numeric, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, TenantScopedMixin

class AssetCategory(str, enum.Enum):
    hardware = "hardware"
    software = "software"
    furniture = "furniture"
    vehicle = "vehicle"
    other = "other"

class AssetStatus(str, enum.Enum):
    active = "active"
    maintenance = "maintenance"
    retired = "retired"

class Asset(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[AssetCategory] = mapped_column(SAEnum(AssetCategory, name="asset_category"), nullable=False)
    status: Mapped[AssetStatus] = mapped_column(SAEnum(AssetStatus, name="asset_status"), default=AssetStatus.active, nullable=False)
    purchase_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    purchase_cost: Mapped[Numeric | None] = mapped_column(Numeric(10, 2), nullable=True)
    depreciation_rate: Mapped[Numeric | None] = mapped_column(Numeric(5, 2), nullable=True) # Percentage
    
    custodian_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    
    custom_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
