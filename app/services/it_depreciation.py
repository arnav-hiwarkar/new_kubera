"""Income Tax Act 1961 Section 32 Block Depreciation Engine.

Computes block-level depreciation with:
- 180-day rule: Put to use >= 180 days -> full rate; < 180 days -> half rate.
- Deductions for sales proceeds deducted from full-rate additions / opening first.
- Section 50 Short-Term Capital Gain (STCG) when sales exceed block value.
- Section 50 Short-Term Capital Loss (STCL) when block ceases to exist (all assets disposed).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from app.services.asset_costing import money


@dataclass(frozen=True)
class ItBlockDepreciationInput:
    block_id: Optional[str]
    block_name: str
    prescribed_rate: Decimal
    opening_wdv: Decimal
    additions_more_than_180: Decimal
    additions_less_than_180: Decimal
    realized_from_sales: Decimal
    all_assets_disposed: bool = False


@dataclass(frozen=True)
class ItBlockDepreciationResult:
    block_id: Optional[str]
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


def calculate_it_block_depreciation(
    inp: ItBlockDepreciationInput,
) -> ItBlockDepreciationResult:
    rate = inp.prescribed_rate
    rate_fraction = rate / Decimal("100")
    half_rate_fraction = rate_fraction / Decimal("2")

    opening = money(inp.opening_wdv)
    add_full = money(inp.additions_more_than_180)
    add_half = money(inp.additions_less_than_180)
    sales = money(inp.realized_from_sales)

    total_pool = opening + add_full + add_half
    balance_before_dep = total_pool - sales

    # Case 1: Sale proceeds exceed the entire pool -> Section 50 STCG
    if balance_before_dep < 0:
        stcg = abs(balance_before_dep)
        return ItBlockDepreciationResult(
            block_id=inp.block_id,
            block_name=inp.block_name,
            prescribed_rate=rate,
            opening_wdv=opening,
            additions_more_than_180=add_full,
            additions_less_than_180=add_half,
            realized_from_sales=sales,
            balance_before_depreciation=balance_before_dep,
            depreciation_full_rate=Decimal("0.00"),
            depreciation_half_rate=Decimal("0.00"),
            total_depreciation=Decimal("0.00"),
            closing_wdv=Decimal("0.00"),
            capital_gain_or_loss=stcg,
            has_stcg=True,
            has_stcl=False,
        )

    # Case 2: Block is completely empty (all assets disposed) -> Section 50 STCL
    if inp.all_assets_disposed and balance_before_dep > 0:
        stcl = balance_before_dep
        return ItBlockDepreciationResult(
            block_id=inp.block_id,
            block_name=inp.block_name,
            prescribed_rate=rate,
            opening_wdv=opening,
            additions_more_than_180=add_full,
            additions_less_than_180=add_half,
            realized_from_sales=sales,
            balance_before_depreciation=balance_before_dep,
            depreciation_full_rate=Decimal("0.00"),
            depreciation_half_rate=Decimal("0.00"),
            total_depreciation=Decimal("0.00"),
            closing_wdv=Decimal("0.00"),
            capital_gain_or_loss=stcl,
            has_stcg=False,
            has_stcl=True,
        )

    # Case 3: Standard depreciation calculation
    # Sales proceeds reduce the full-rate pool (opening + additions >= 180) first
    full_pool = opening + add_full
    if sales <= full_pool:
        remaining_full_pool = full_pool - sales
        remaining_half_pool = add_half
    else:
        remaining_full_pool = Decimal("0.00")
        excess_sales = sales - full_pool
        remaining_half_pool = max(Decimal("0.00"), add_half - excess_sales)

    dep_full = money(remaining_full_pool * rate_fraction)
    dep_half = money(remaining_half_pool * half_rate_fraction)
    total_dep = dep_full + dep_half

    # Closing WDV cannot be negative
    closing_wdv = max(Decimal("0.00"), balance_before_dep - total_dep)

    return ItBlockDepreciationResult(
        block_id=inp.block_id,
        block_name=inp.block_name,
        prescribed_rate=rate,
        opening_wdv=opening,
        additions_more_than_180=add_full,
        additions_less_than_180=add_half,
        realized_from_sales=sales,
        balance_before_depreciation=balance_before_dep,
        depreciation_full_rate=dep_full,
        depreciation_half_rate=dep_half,
        total_depreciation=total_dep,
        closing_wdv=closing_wdv,
        capital_gain_or_loss=Decimal("0.00"),
        has_stcg=False,
        has_stcl=False,
    )
