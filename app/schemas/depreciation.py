"""Pydantic schemas for depreciation runs and calculation lines."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class DepreciationRunCreate(BaseModel):
    financial_year_id: uuid.UUID
    book: str = "companies_act"
    notes: Optional[str] = None


class AssetDepreciationLineResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    asset_id: uuid.UUID
    method: str
    opening_gross_block: Decimal
    additions: Decimal
    disposals: Decimal
    closing_gross_block: Decimal
    opening_accumulated_depreciation: Decimal
    depreciation_for_year: Decimal
    disposal_accumulated_depreciation: Decimal
    closing_accumulated_depreciation: Decimal
    opening_carrying_amount: Decimal
    closing_carrying_amount: Decimal
    residual_value: Decimal
    remaining_useful_life_days: int
    effective_rate_pct: Decimal
    is_part_year: bool
    is_disposed: bool
    gain_loss_on_disposal: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class ItBlockDepreciationLineResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    it_block_id: Optional[uuid.UUID]
    block_name: str
    prescribed_rate: Decimal
    opening_wdv: Decimal
    additions_more_than_180: Decimal
    additions_less_than_180: Decimal
    realized_from_sales: Decimal
    balance_before_depreciation: Decimal
    depreciation_full_rate: Decimal
    depreciation_half_rate: Decimal
    total_depreciation: Decimal
    closing_wdv: Decimal
    capital_gain_or_loss: Decimal
    has_stcg: bool
    has_stcl: bool

    model_config = ConfigDict(from_attributes=True)


class DepreciationRunResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    financial_year_id: uuid.UUID
    financial_year_label: Optional[str] = None
    book: str = "companies_act"
    run_date: datetime
    status: str
    finalized_at: Optional[datetime] = None
    finalized_by: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    total_gross_block: Decimal = Decimal("0.00")
    total_depreciation: Decimal = Decimal("0.00")
    total_carrying_amount: Decimal = Decimal("0.00")
    total_it_depreciation: Decimal = Decimal("0.00")
    total_it_closing_wdv: Decimal = Decimal("0.00")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
