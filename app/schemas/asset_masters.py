"""Schemas for fixed-asset master data."""
import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.asset_masters import (
    AssetLookupKind,
    DepreciationMethod,
    ItBlockClass,
    ItcTreatment,
)
# Reuse the statutory identifier regexes rather than restating them.
from app.schemas.company import GSTIN_RE, PAN_RE


def _clean_gstin(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip().upper()
    if not v:
        return None
    if not GSTIN_RE.match(v):
        raise ValueError("Invalid GSTIN format (15 characters)")
    return v


# === IT asset blocks ===

class ItAssetBlockResponse(BaseModel):
    id: uuid.UUID
    company_id: Optional[uuid.UUID]
    code: str
    name: str
    dep_rate: float
    block_class: ItBlockClass
    is_active: bool
    display_order: int

    model_config = ConfigDict(from_attributes=True)


class ItAssetBlockCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=255)
    dep_rate: float = Field(ge=0, le=100)
    block_class: ItBlockClass
    display_order: int = 0


class ItAssetBlockUpdate(BaseModel):
    """Partial edit of a company-owned Appendix I block."""
    code: Optional[str] = Field(default=None, min_length=1, max_length=30)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    dep_rate: Optional[float] = Field(default=None, ge=0, le=100)
    block_class: Optional[ItBlockClass] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


# === Categories ===

class AssetCategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: Optional[str] = Field(default=None, max_length=50)
    parent_id: Optional[uuid.UUID] = None
    default_useful_life_months: Optional[int] = Field(default=None, ge=1, le=1200)
    default_dep_method: Optional[DepreciationMethod] = None
    default_residual_pct: Optional[float] = Field(default=None, ge=0, le=100)
    default_it_block_id: Optional[uuid.UUID] = None
    default_itc_treatment: Optional[ItcTreatment] = None
    tag_prefix: Optional[str] = Field(default=None, max_length=12)
    applicable_field_groups: list[str] = Field(default_factory=list)
    schedule_ii_reference: Optional[str] = Field(default=None, max_length=255)
    display_order: int = 0

    @field_validator("tag_prefix")
    @classmethod
    def _upper_prefix(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() or None if v else None


class AssetCategoryCreate(AssetCategoryBase):
    pass


class AssetCategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    code: Optional[str] = Field(default=None, max_length=50)
    default_useful_life_months: Optional[int] = Field(default=None, ge=1, le=1200)
    default_dep_method: Optional[DepreciationMethod] = None
    default_residual_pct: Optional[float] = Field(default=None, ge=0, le=100)
    default_it_block_id: Optional[uuid.UUID] = None
    default_itc_treatment: Optional[ItcTreatment] = None
    tag_prefix: Optional[str] = Field(default=None, max_length=12)
    applicable_field_groups: Optional[list[str]] = None
    schedule_ii_reference: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class AssetCategoryResponse(BaseModel):
    id: uuid.UUID
    company_id: Optional[uuid.UUID]
    parent_id: Optional[uuid.UUID]
    name: str
    code: Optional[str]
    default_useful_life_months: Optional[int]
    default_dep_method: Optional[DepreciationMethod]
    default_residual_pct: Optional[float]
    default_it_block_id: Optional[uuid.UUID]
    # Flattened for the client so picking a category needs no second lookup.
    default_it_block_code: Optional[str] = None
    default_it_block_rate: Optional[float] = None
    default_itc_treatment: Optional[ItcTreatment]
    tag_prefix: Optional[str]
    applicable_field_groups: list[str] = Field(default_factory=list)
    schedule_ii_reference: Optional[str]
    is_active: bool
    display_order: int

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _flatten_block(cls, data: Any):
        block = getattr(data, "it_block", None)
        if block is None:
            return data
        # Build a dict view so we can inject the flattened block fields.
        out = {c: getattr(data, c) for c in (
            "id", "company_id", "parent_id", "name", "code",
            "default_useful_life_months", "default_dep_method", "default_residual_pct",
            "default_it_block_id", "default_itc_treatment", "tag_prefix",
            "applicable_field_groups", "schedule_ii_reference", "is_active", "display_order",
        )}
        out["default_it_block_code"] = block.code
        out["default_it_block_rate"] = float(block.dep_rate)
        return out

    @field_validator("applicable_field_groups", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return v or []


# === Suppliers ===

class SupplierBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    gstin: Optional[str] = None
    state: Optional[str] = Field(default=None, max_length=100)
    pan: Optional[str] = None
    contact_person: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    address_line1: Optional[str] = Field(default=None, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=6)

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v):
        return _clean_gstin(v)

    @field_validator("pan")
    @classmethod
    def _pan(cls, v):
        if v is None:
            return None
        s = v.strip().upper()
        if not s:
            return None
        if not PAN_RE.match(s):
            raise ValueError("Invalid PAN format (10 characters)")
        return s


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    gstin: Optional[str] = None
    state: Optional[str] = Field(default=None, max_length=100)
    pan: Optional[str] = None
    contact_person: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    address_line1: Optional[str] = Field(default=None, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=6)
    is_active: Optional[bool] = None

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v):
        return _clean_gstin(v)


class SupplierResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    code: str
    name: str
    gstin: Optional[str]
    state_code: Optional[str]
    state: Optional[str]
    pan: Optional[str]
    contact_person: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address_line1: Optional[str]
    address_line2: Optional[str]
    city: Optional[str]
    pincode: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# === Lookups ===

class AssetLookupCreate(BaseModel):
    kind: AssetLookupKind
    name: str = Field(min_length=1, max_length=255)
    code: Optional[str] = Field(default=None, max_length=50)
    parent_id: Optional[uuid.UUID] = None
    gstin: Optional[str] = None
    state: Optional[str] = Field(default=None, max_length=100)
    display_order: int = 0

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v):
        return _clean_gstin(v)


class AssetLookupUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    code: Optional[str] = Field(default=None, max_length=50)
    parent_id: Optional[uuid.UUID] = None
    gstin: Optional[str] = None
    state: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None
    display_order: Optional[int] = None

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v):
        return _clean_gstin(v)


class AssetLookupResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    kind: AssetLookupKind
    name: str
    code: Optional[str]
    parent_id: Optional[uuid.UUID]
    gstin: Optional[str]
    state_code: Optional[str]
    state: Optional[str]
    is_active: bool
    display_order: int

    model_config = ConfigDict(from_attributes=True)


# === Impact preview ===

class ImpactPreviewResponse(BaseModel):
    kind: str
    id: uuid.UUID
    assets_referencing: int
    draft_run_fy_labels: List[str]
    finalized_run_fy_labels: List[str]
    classification: str  # "none" | "future_only"
    message: str
