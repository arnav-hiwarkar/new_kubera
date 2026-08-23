"""Pydantic schemas for depreciation runs and calculation lines."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DepreciationRunCreate(BaseModel):
    # No `book` field: one run computes both the Companies Act and the Income Tax
    # book in a single pass, and finalized runs are now unique per (company,
    # financial year) regardless of book. Accepting a `book` here invited callers
    # into a distinction the engine does not make — an unvalidated string that
    # changed nothing but could slip a second "finalized" run past the old index.
    financial_year_id: uuid.UUID
    notes: Optional[str] = None


class DepreciationRunReopenRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class CalcStepSchema(BaseModel):
    """One line of a calculation, already formatted for display.

    `formula` and `substitution` are empty for a plain input rather than a derivation.
    """

    key: str
    group: str
    label: str
    formula: str
    substitution: str
    result: str
    unit: str = "none"
    emphasis: bool = False
    note: Optional[str] = None


class CalcTraceSchema(BaseModel):
    title: str
    basis: str
    steps: List[CalcStepSchema] = []
    is_projection: bool = False
    computed_at: Optional[str] = None


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
    calc_trace: Optional[CalcTraceSchema] = None

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
    calc_trace: Optional[CalcTraceSchema] = None

    model_config = ConfigDict(from_attributes=True)


class DepreciationExplainRequest(BaseModel):
    asset_id: uuid.UUID
    financial_year_id: uuid.UUID


class DepreciationExplainResponse(BaseModel):
    """Traces computed on demand and never stored.

    `income_tax` is absent when the asset has not been assigned to a block.
    """

    companies_act: CalcTraceSchema
    income_tax: Optional[CalcTraceSchema] = None


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
