"""Schemas for the fixed-asset register."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.asset_masters import DepreciationMethod, DiscountType, ItcTreatment
from app.models.assets import (
    AssetCondition,
    AssetDocRole,
    AssetLifecycleStatus,
    AssetOperationalStatus,
)


# === Quick add ===

class AssetQuickAddRequest(BaseModel):
    """The six-field create form. Everything else is enrichment.

    quantity > 1 explodes into that many individually tagged asset units sharing
    one acquisition.
    """

    asset_name: str = Field(min_length=1, max_length=255)
    category_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=2000)
    unit_basic_price: Optional[Decimal] = Field(default=None, ge=0)
    supplier_id: Optional[uuid.UUID] = None
    purchase_date: Optional[date] = None
    branch_id: Optional[uuid.UUID] = None


class AssetQuickAddResponse(BaseModel):
    acquisition_id: uuid.UUID
    asset_ids: List[uuid.UUID]
    first_asset_id: uuid.UUID
    quantity: int


# === Cost preview ===

class CostPreviewRequest(BaseModel):
    quantity: int = Field(default=1, ge=1)
    unit_basic_price: Decimal = Field(default=Decimal("0"), ge=0)
    discount_type: DiscountType = DiscountType.amount
    discount_value: Decimal = Field(default=Decimal("0"), ge=0)
    gst_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    supplier_id: Optional[uuid.UUID] = None
    branch_id: Optional[uuid.UUID] = None
    itc_treatment: ItcTreatment = ItcTreatment.eligible
    itc_eligible_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)
    freight_cost: Decimal = Field(default=Decimal("0"), ge=0)
    installation_cost: Decimal = Field(default=Decimal("0"), ge=0)
    other_capitalizable_cost: Decimal = Field(default=Decimal("0"), ge=0)
    cgst_amount_override: Optional[Decimal] = None
    sgst_amount_override: Optional[Decimal] = None
    igst_amount_override: Optional[Decimal] = None


class CostPreviewResponse(BaseModel):
    gross_basic_price: Decimal
    discount_amount: Decimal
    net_basic_price: Decimal
    gst_split_basis: str
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_gst: Decimal
    recoverable_gst: Decimal
    capitalizable_gst: Decimal
    landed_cost: Decimal
    total_acquisition_outlay: Decimal
    per_unit_cost: Decimal


# === Acquisition ===

class AcquisitionUpdate(BaseModel):
    supplier_id: Optional[uuid.UUID] = None
    invoice_number: Optional[str] = Field(default=None, max_length=100)
    invoice_date: Optional[date] = None
    po_number: Optional[str] = Field(default=None, max_length=100)
    purchase_date: Optional[date] = None
    quantity: Optional[int] = Field(default=None, ge=1, le=2000)
    unit_basic_price: Optional[Decimal] = Field(default=None, ge=0)
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = Field(default=None, ge=0)
    hsn_sac_code: Optional[str] = Field(default=None, max_length=10)
    gst_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    branch_id: Optional[uuid.UUID] = None
    place_of_supply_state_code: Optional[str] = Field(default=None, max_length=2)
    cgst_amount: Optional[Decimal] = Field(default=None, ge=0)
    sgst_amount: Optional[Decimal] = Field(default=None, ge=0)
    igst_amount: Optional[Decimal] = Field(default=None, ge=0)
    gst_amounts_overridden: Optional[bool] = None
    itc_treatment: Optional[ItcTreatment] = None
    itc_eligible_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)
    freight_cost: Optional[Decimal] = Field(default=None, ge=0)
    installation_cost: Optional[Decimal] = Field(default=None, ge=0)
    other_capitalizable_cost: Optional[Decimal] = Field(default=None, ge=0)
    is_imported: Optional[bool] = None
    is_leased: Optional[bool] = None
    grn_number: Optional[str] = Field(default=None, max_length=100)
    grn_date: Optional[date] = None
    delivery_challan_number: Optional[str] = Field(default=None, max_length=100)
    eway_bill_number: Optional[str] = Field(default=None, max_length=20)
    irn: Optional[str] = Field(default=None, max_length=64)
    bill_of_entry_number: Optional[str] = Field(default=None, max_length=50)
    bill_of_entry_date: Optional[date] = None
    customs_duty: Optional[Decimal] = Field(default=None, ge=0)
    foreign_currency: Optional[str] = Field(default=None, max_length=3)
    foreign_currency_value: Optional[Decimal] = Field(default=None, ge=0)
    exchange_rate: Optional[Decimal] = Field(default=None, ge=0)
    lease_type: Optional[str] = Field(default=None, max_length=50)
    lessor_name: Optional[str] = Field(default=None, max_length=255)
    lease_start_date: Optional[date] = None
    lease_end_date: Optional[date] = None
    lease_rental: Optional[Decimal] = Field(default=None, ge=0)
    project_budget_reference: Optional[str] = Field(default=None, max_length=255)
    remarks: Optional[str] = None


class AcquisitionResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    supplier_id: Optional[uuid.UUID]
    supplier_name_snapshot: Optional[str]
    supplier_gstin_snapshot: Optional[str]
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    po_number: Optional[str]
    purchase_date: Optional[date]
    quantity: int
    unit_basic_price: Optional[Decimal]
    discount_type: DiscountType
    discount_value: Optional[Decimal]
    hsn_sac_code: Optional[str]
    gst_rate: Optional[Decimal]
    branch_id: Optional[uuid.UUID]
    place_of_supply_state_code: Optional[str]
    cgst_amount: Optional[Decimal]
    sgst_amount: Optional[Decimal]
    igst_amount: Optional[Decimal]
    gst_amounts_overridden: bool
    gst_split_basis: Optional[str]
    itc_treatment: Optional[ItcTreatment]
    itc_eligible_pct: Optional[Decimal]
    freight_cost: Optional[Decimal]
    installation_cost: Optional[Decimal]
    other_capitalizable_cost: Optional[Decimal]
    # Derived
    gross_basic_price: Optional[Decimal]
    discount_amount: Optional[Decimal]
    net_basic_price: Optional[Decimal]
    total_gst: Optional[Decimal]
    recoverable_gst: Optional[Decimal]
    capitalizable_gst: Optional[Decimal]
    landed_cost: Optional[Decimal]
    total_acquisition_outlay: Optional[Decimal]
    per_unit_cost: Optional[Decimal]
    # Conditional groups
    is_imported: bool
    is_leased: bool
    grn_number: Optional[str]
    grn_date: Optional[date]
    delivery_challan_number: Optional[str]
    eway_bill_number: Optional[str]
    irn: Optional[str]
    bill_of_entry_number: Optional[str]
    bill_of_entry_date: Optional[date]
    customs_duty: Optional[Decimal]
    foreign_currency: Optional[str]
    foreign_currency_value: Optional[Decimal]
    exchange_rate: Optional[Decimal]
    lease_type: Optional[str]
    lessor_name: Optional[str]
    lease_start_date: Optional[date]
    lease_end_date: Optional[date]
    lease_rental: Optional[Decimal]
    project_budget_reference: Optional[str]
    remarks: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# === Asset unit ===

class AssetUpdate(BaseModel):
    asset_code: Optional[str] = Field(default=None, max_length=50)
    asset_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    category_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    manufacturer: Optional[str] = Field(default=None, max_length=255)
    manufacturer_contact: Optional[str] = Field(default=None, max_length=255)
    brand_model: Optional[str] = Field(default=None, max_length=255)
    manufacturer_serial_number: Optional[str] = Field(default=None, max_length=255)

    operational_status: Optional[AssetOperationalStatus] = None
    condition: Optional[AssetCondition] = None

    branch_id: Optional[uuid.UUID] = None
    cost_centre_id: Optional[uuid.UUID] = None
    department_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    custodian_id: Optional[uuid.UUID] = None
    custodian_name: Optional[str] = Field(default=None, max_length=255)
    custodian_employee_code: Optional[str] = Field(default=None, max_length=50)

    available_for_use_date: Optional[date] = None
    capitalization_date: Optional[date] = None
    warranty_start_date: Optional[date] = None
    warranty_months: Optional[int] = Field(default=None, ge=0, le=1200)

    useful_life_months: Optional[int] = Field(default=None, ge=1, le=1200)
    dep_method: Optional[DepreciationMethod] = None
    residual_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)
    useful_life_override_reason: Optional[str] = None

    it_block_id: Optional[uuid.UUID] = None
    it_dep_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    it_put_to_use_date: Optional[date] = None

    is_pre_cutover: Optional[bool] = None
    opening_accumulated_depreciation: Optional[Decimal] = Field(default=None, ge=0)
    opening_wdv: Optional[Decimal] = Field(default=None, ge=0)
    opening_it_wdv: Optional[Decimal] = Field(default=None, ge=0)

    registration_number: Optional[str] = Field(default=None, max_length=50)
    engine_number: Optional[str] = Field(default=None, max_length=50)
    chassis_number: Optional[str] = Field(default=None, max_length=50)
    imei: Optional[str] = Field(default=None, max_length=20)
    mac_address: Optional[str] = Field(default=None, max_length=32)
    technical_specs: Optional[str] = None
    remarks: Optional[str] = None
    parent_asset_id: Optional[uuid.UUID] = None
    custom_fields: Optional[Dict[str, Any]] = None


class ValidationIssueResponse(BaseModel):
    field: str
    label: str
    tab: str
    kind: str
    message: Optional[str] = None


class AssetResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    acquisition_id: Optional[uuid.UUID]
    unit_index: int
    asset_code: Optional[str]
    asset_name: str
    category_id: Optional[uuid.UUID]
    description: Optional[str]
    manufacturer: Optional[str]
    manufacturer_contact: Optional[str]
    brand_model: Optional[str]
    manufacturer_serial_number: Optional[str]

    lifecycle_status: AssetLifecycleStatus
    operational_status: Optional[AssetOperationalStatus]
    condition: Optional[AssetCondition]

    branch_id: Optional[uuid.UUID]
    cost_centre_id: Optional[uuid.UUID]
    department_id: Optional[uuid.UUID]
    location_id: Optional[uuid.UUID]
    custodian_id: Optional[uuid.UUID]
    custodian_name: Optional[str]
    custodian_employee_code: Optional[str]

    available_for_use_date: Optional[date]
    capitalization_date: Optional[date]
    warranty_start_date: Optional[date]
    warranty_months: Optional[int]
    warranty_expiry_date: Optional[date]

    useful_life_months: Optional[int]
    dep_method: Optional[DepreciationMethod]
    residual_pct: Optional[Decimal]
    residual_value: Optional[Decimal]
    useful_life_override_reason: Optional[str]

    it_block_id: Optional[uuid.UUID]
    it_dep_rate: Optional[Decimal]
    it_put_to_use_date: Optional[date]

    original_cost: Optional[Decimal]
    is_pre_cutover: bool
    opening_accumulated_depreciation: Optional[Decimal]
    opening_wdv: Optional[Decimal]
    opening_it_wdv: Optional[Decimal]

    registration_number: Optional[str]
    engine_number: Optional[str]
    chassis_number: Optional[str]
    imei: Optional[str]
    mac_address: Optional[str]
    technical_specs: Optional[str]
    remarks: Optional[str]
    parent_asset_id: Optional[uuid.UUID]
    custom_fields: Dict[str, Any] = Field(default_factory=dict)

    # Disposals
    disposal_date: Optional[date] = None
    disposal_type: Optional[str] = None
    sale_proceeds: Optional[Decimal] = None
    buyer_name: Optional[str] = None
    disposal_invoice_no: Optional[str] = None
    disposal_remarks: Optional[str] = None
    disposal_gain_loss: Optional[Decimal] = None
    disposal_it_proceeds: Optional[Decimal] = None

    created_by: Optional[uuid.UUID]
    submitted_by: Optional[uuid.UUID]
    submitted_at: Optional[datetime]
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssetDisposalRequest(BaseModel):
    disposal_date: date
    disposal_type: str = Field(..., description="sale, scrap, write_off, loss_destruction, insurance_claim")
    sale_proceeds: Decimal = Field(default=Decimal("0.00"), ge=0)
    buyer_name: Optional[str] = None
    disposal_invoice_no: Optional[str] = None
    disposal_remarks: Optional[str] = None
    disposal_it_proceeds: Optional[Decimal] = None



class AssetDetailResponse(BaseModel):
    """What the tabbed detail page loads in one request."""

    asset: AssetResponse
    acquisition: Optional[AcquisitionResponse]
    # Sibling units from the same acquisition (id + code + status only).
    siblings: List["AssetSibling"] = Field(default_factory=list)
    documents: List["AssetDocumentResponse"] = Field(default_factory=list)
    # Field groups the category says are relevant, so the UI hides the rest.
    applicable_field_groups: List[str] = Field(default_factory=list)
    # What is stopping the next transition, per tab.
    blocking_issues: List[ValidationIssueResponse] = Field(default_factory=list)
    completeness_by_tab: Dict[str, int] = Field(default_factory=dict)


class AssetSibling(BaseModel):
    id: uuid.UUID
    unit_index: int
    asset_code: Optional[str]
    lifecycle_status: AssetLifecycleStatus
    manufacturer_serial_number: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class AssetDocumentResponse(BaseModel):
    id: uuid.UUID
    asset_id: Optional[uuid.UUID]
    acquisition_id: Optional[uuid.UUID]
    document_id: uuid.UUID
    doc_role: AssetDocRole
    note: Optional[str]
    uploaded_by: Optional[uuid.UUID]
    created_at: datetime
    # Flattened from the DocVault document for display.
    title: Optional[str] = None
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class AssetDocumentAttach(BaseModel):
    document_id: uuid.UUID
    doc_role: AssetDocRole
    note: Optional[str] = Field(default=None, max_length=255)


# === Transitions ===

class TransitionRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)
    # Apply the transition to every sibling unit of the same acquisition. The
    # common case for an exploded batch: submit or approve all fifty at once.
    apply_to_siblings: bool = False


class TransitionResponse(BaseModel):
    updated: List[uuid.UUID]
    lifecycle_status: AssetLifecycleStatus


class SerialAssignment(BaseModel):
    asset_id: uuid.UUID
    manufacturer_serial_number: Optional[str] = Field(default=None, max_length=255)
    asset_code: Optional[str] = Field(default=None, max_length=50)


class BulkSerialRequest(BaseModel):
    """Per-unit serials for an exploded batch, filled from a grid."""

    assignments: List[SerialAssignment]


AssetDetailResponse.model_rebuild()
