import uuid
import enum
from sqlalchemy import String, Boolean, Integer, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, TenantScopedMixin

class CustomFieldModule(str, enum.Enum):
    asset_management = "asset_management"
    sales_tracking = "sales_tracking"

class CustomFieldType(str, enum.Enum):
    text = "text"
    number = "number"
    date = "date"
    dropdown = "dropdown"

class CustomFieldDefinition(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "custom_field_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module: Mapped[CustomFieldModule] = mapped_column(SAEnum(CustomFieldModule, name="custom_field_module"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[CustomFieldType] = mapped_column(SAEnum(CustomFieldType, name="custom_field_type"), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dropdown_options: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
