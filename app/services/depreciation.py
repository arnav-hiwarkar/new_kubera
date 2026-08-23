"""Companies Act 2013 Schedule II depreciation engine.

Pure Decimal calculations with ROUND_HALF_UP precision.
Handles SLM, WDV, pro-rata additions, disposals, pre-cutover balances,
and residual value capping.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from app.services.asset_costing import money


class DepreciationDataError(ValueError):
    """Raised when asset or block input data violates statutory or computation rules (HTTP 422)."""
    pass


@dataclass(frozen=True)
class AssetDepreciationInput:
    asset_id: str
    asset_name: str
    original_cost: Decimal
    capitalization_date: Optional[date]
    useful_life_months: int
    residual_pct: Optional[Decimal] = Decimal("5.00")
    residual_value: Optional[Decimal] = None
    dep_method: str = "SLM"  # "SLM" or "WDV"
    is_pre_cutover: bool = False
    opening_accumulated_dep: Decimal = Decimal("0.00")
    # Carrying amount carried in at cutover. Authoritative when supplied: an impaired
    # or revalued asset's true written-down value is not cost less accumulated
    # depreciation, and deriving it would silently discard the figure the user stated.
    opening_wdv: Optional[Decimal] = None
    disposal_date: Optional[date] = None
    disposal_type: Optional[str] = None
    sale_proceeds: Optional[Decimal] = None


@dataclass(frozen=True)
class AssetDepreciationResult:
    asset_id: str
    method: str
    opening_gross_block: Decimal
    additions: Decimal
    disposals: Decimal
    closing_gross_block: Decimal
    opening_accumulated_dep: Decimal
    depreciation_for_year: Decimal
    disposal_accumulated_dep: Decimal
    closing_accumulated_dep: Decimal
    opening_carrying_amount: Decimal
    closing_carrying_amount: Decimal
    residual_value: Decimal
    remaining_useful_life_days: int
    effective_rate_pct: Decimal
    is_part_year: bool
    is_disposed: bool
    gain_loss_on_disposal: Optional[Decimal] = None
    # The engine's own workings, for `calc_trace_builders` to label. Raw values only —
    # no formatting, no prose. Kept out of the returned figures so nothing downstream
    # can mistake a working for a result.
    intermediates: dict = field(default_factory=dict)


def _remaining_life_days(
    useful_life_months: int, depreciable_base: Decimal, closing_acc_dep: Decimal
) -> tuple:
    """Remaining life implied by how much of the depreciable base is left.

    Returns (remaining_days, total_life_days, consumed) so a trace can show the
    working rather than asserting the answer.

    The previous form subtracted only the CURRENT year's active days from the total
    life, so it ignored every prior year and the whole of a pre-cutover asset's
    elapsed life — a four-year-old asset carried in at cutover reported its full
    original life minus one year. Reading it off accumulated depreciation instead is
    correct for pre-cutover assets and for assets with prior runs alike.
    """
    total_life_days = useful_life_months * 30
    if depreciable_base <= 0:
        return 0, total_life_days, Decimal("0.00")
    consumed = min(closing_acc_dep, depreciable_base)
    remaining = (depreciable_base - consumed) / depreciable_base
    return max(0, int(Decimal(total_life_days) * remaining)), total_life_days, consumed


def calculate_asset_depreciation(
    inp: AssetDepreciationInput,
    fy_start: date,
    fy_end: date,
) -> AssetDepreciationResult:
    cost = inp.original_cost
    res_pct = inp.residual_pct if inp.residual_pct is not None else Decimal("5.00")
    res_val = inp.residual_value if inp.residual_value is not None else money(cost * res_pct / Decimal("100"))
    depreciable_base = cost - res_val if cost > res_val else Decimal("0.00")
    inter: dict = {"depreciable_base": depreciable_base}

    cap_date = inp.capitalization_date or fy_start
    total_fy_days = (fy_end - fy_start).days + 1
    inter["total_fy_days"] = total_fy_days

    # Check if addition during this FY
    is_addition = cap_date > fy_start and cap_date <= fy_end
    inter["is_addition"] = is_addition
    opening_gross = Decimal("0.00") if is_addition else cost

    # A pre-owned asset exists to carry its history in. Arriving with neither a WDV
    # nor accumulated depreciation means that history was lost, and depreciating from
    # full cost would silently restate an already part-worn asset as new.
    if (
        inp.is_pre_cutover
        and not is_addition
        and inp.opening_wdv is None
        and money(inp.opening_accumulated_dep) == Decimal("0.00")
    ):
        raise DepreciationDataError(
            f"Asset {inp.asset_id} ({inp.asset_name}) is marked pre-cutover but carries "
            f"neither an opening WDV nor opening accumulated depreciation. Depreciating "
            f"it from full original cost would overstate the charge."
        )
    additions = cost if is_addition else Decimal("0.00")

    # Check if disposed during this FY
    is_disposed = inp.disposal_date is not None and (fy_start <= inp.disposal_date <= fy_end)
    disposals = cost if is_disposed else Decimal("0.00")
    closing_gross = Decimal("0.00") if is_disposed else (opening_gross + additions)

    opening_acc_dep = money(inp.opening_accumulated_dep) if not is_addition else Decimal("0.00")
    if is_addition:
        opening_carrying = Decimal("0.00")
    elif inp.opening_wdv is not None:
        # A stated carrying amount wins over the derived one. They differ whenever the
        # asset was impaired, revalued, or carried in from a different rate regime.
        opening_carrying = money(inp.opening_wdv)
    else:
        opening_carrying = opening_gross - opening_acc_dep if opening_gross > 0 else Decimal("0.00")

    # Determine active days in the current FY
    start_active = cap_date if is_addition else fy_start
    end_active = inp.disposal_date if is_disposed else fy_end
    
    if start_active > end_active or start_active > fy_end:
        active_days = 0
    else:
        active_days = (end_active - start_active).days + 1

    inter["active_days"] = active_days
    inter["start_active"] = start_active.isoformat()
    inter["end_active"] = end_active.isoformat()

    is_part_year = active_days < total_fy_days and not is_disposed

    # Annual depreciation computation
    useful_years = Decimal(inp.useful_life_months) / Decimal("12")
    inter["useful_years"] = useful_years
    if useful_years <= 0:
        annual_dep = Decimal("0.00")
        dep_for_year = Decimal("0.00")
    else:
        if inp.dep_method == "WDV":
            # Schedule II WDV rate formula: 1 - (residual / cost) ** (1 / n)
            if cost <= 0 or res_val <= 0:
                raise DepreciationDataError(
                    f"WDV depreciation for asset {inp.asset_id} requires a residual value "
                    f"greater than zero (cost={cost}, residual={res_val}). The Schedule II rate "
                    f"1-(s/c)^(1/n) is undefined at zero residual and would write the asset off "
                    f"entirely in year one."
                )
            if res_val >= cost:
                raise DepreciationDataError(
                    f"WDV depreciation for asset {inp.asset_id}: residual value {res_val} is not "
                    f"less than cost {cost}."
                )
            ratio = float(res_val / cost)
            wdv_rate = Decimal(str(round(1.0 - (ratio ** (1.0 / float(useful_years))), 4)))
            # An asset in its first year has no opening carrying amount yet, so it
            # depreciates from cost. Any other zero means the asset is written down —
            # falling back to cost there restarted a spent asset from scratch every
            # year, checked only by the residual cap.
            carrying_for_calc = cost if is_addition else opening_carrying
            inter["wdv_rate"] = wdv_rate
            inter["carrying_for_calc"] = carrying_for_calc
            raw_annual = carrying_for_calc * wdv_rate
        else:
            # SLM
            raw_annual = depreciable_base / useful_years

        annual_dep = money(raw_annual)

        if active_days == total_fy_days:
            dep_for_year = annual_dep
        elif active_days > 0:
            dep_for_year = money(raw_annual * Decimal(active_days) / Decimal(total_fy_days))
        else:
            dep_for_year = Decimal("0.00")

    inter["annual_dep"] = annual_dep
    # The charge before the residual cap is applied. The cap is a separate, visible
    # step in the trace, so the figure it acted on has to survive.
    inter["dep_before_cap"] = dep_for_year

    # Cap depreciation so accumulated depreciation does not exceed depreciable base
    max_dep_allowed = depreciable_base - opening_acc_dep if depreciable_base > opening_acc_dep else Decimal("0.00")
    inter["max_dep_allowed"] = max_dep_allowed
    if dep_for_year > max_dep_allowed:
        dep_for_year = max_dep_allowed

    # Carrying amounts roll forward from the OPENING carrying amount, not from gross
    # cost less accumulated depreciation. The two agree for an ordinary asset, but
    # diverge whenever a cutover WDV was stated for an impaired or revalued asset —
    # and deriving from cost there would contradict the opening figure on the same row.
    if is_disposed:
        disposal_acc_dep = opening_acc_dep + dep_for_year
        closing_acc_dep = Decimal("0.00")
        closing_carrying = Decimal("0.00")
        nbv_at_disposal = opening_carrying + additions - dep_for_year
        inter["nbv_at_disposal"] = nbv_at_disposal
        proceeds = inp.sale_proceeds if inp.sale_proceeds is not None else Decimal("0.00")
        gain_loss = money(proceeds - nbv_at_disposal)
    else:
        disposal_acc_dep = Decimal("0.00")
        closing_acc_dep = opening_acc_dep + dep_for_year
        closing_carrying = opening_carrying + additions - dep_for_year
        gain_loss = None

    effective_rate = (
        money(dep_for_year * Decimal("100") / cost)
        if cost > 0
        else Decimal("0.00")
    )

    remaining_days, total_life_days, consumed = _remaining_life_days(
        inp.useful_life_months, depreciable_base, closing_acc_dep
    )
    inter["total_life_days"] = total_life_days
    inter["consumed"] = consumed

    return AssetDepreciationResult(
        asset_id=inp.asset_id,
        method=inp.dep_method,
        opening_gross_block=opening_gross,
        additions=additions,
        disposals=disposals,
        closing_gross_block=closing_gross,
        opening_accumulated_dep=opening_acc_dep,
        depreciation_for_year=dep_for_year,
        disposal_accumulated_dep=disposal_acc_dep,
        closing_accumulated_dep=closing_acc_dep,
        opening_carrying_amount=opening_carrying,
        closing_carrying_amount=closing_carrying,
        residual_value=res_val,
        remaining_useful_life_days=remaining_days,
        effective_rate_pct=effective_rate,
        is_part_year=is_part_year,
        is_disposed=is_disposed,
        gain_loss_on_disposal=gain_loss,
        intermediates=inter,
    )
