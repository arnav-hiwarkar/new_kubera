"""Turns engine results into labelled calculation traces.

Everything a user reads lives here: step labels, formula wording, and the statutory
notes. The engines stay math-only and hand over raw `intermediates`, so this module
never recomputes anything — it only names and formats what the engine already did.

Statutory notes are deliberately sparse. They appear on the rules that surprise people
(the pro-rata charge, the residual cap, and — in the Income Tax builder — the 180-day
half rate), on the nil-value cases where a bare "0.00" would otherwise look like an
error (an addition's opening balances, a disposed asset's closing balances), and on a
stated cutover carrying amount that is deliberately not re-derived — so the numbers
stay readable and nothing is asserted without a reason.
"""
from decimal import Decimal
from typing import Optional

from app.services.calc_trace import (
    CalcTrace,
    TraceBuilder,
    fmt_dec,
    fmt_int,
    fmt_money,
    fmt_pct,
)
from app.services.depreciation import AssetDepreciationInput, AssetDepreciationResult
from app.services.it_depreciation import (
    ItBlockDepreciationInput,
    ItBlockDepreciationResult,
)

__all__ = [
    "ADD",
    "DIV",
    "MUL",
    "SUB",
    "GROUP_CHARGE",
    "GROUP_CLOSING",
    "GROUP_DISPOSAL",
    "GROUP_INPUTS",
    "GROUP_POOL",
    "GROUP_RATE",
    "GROUP_RATE_APPLIED",
    "GROUP_ROLL",
    "IT_BLOCK_LINE_FIELDS",
    "SCHEDULE_II_LINE_FIELDS",
    "build_it_block_trace",
    "build_schedule_ii_trace",
]

# Operators as constants rather than inline literals: a caller or a test that needs to
# reproduce a formula string cannot then mistype a Unicode multiplication sign.
MUL = " × "
DIV = " ÷ "
SUB = " − "
ADD = " + "

GROUP_INPUTS = "Inputs"
GROUP_RATE = "Rate"
GROUP_CHARGE = "Charge for the year"
GROUP_ROLL = "Roll-forward"
GROUP_DISPOSAL = "Disposal"

# Emphasised steps are the figures the page displays from the stored line. This map is
# what lets a test prove the trace and the row can never disagree.
SCHEDULE_II_LINE_FIELDS = {
    "opening_gross_block": "opening_gross_block",
    "depreciation_for_year": "depreciation_for_year",
    "closing_carrying_amount": "closing_carrying_amount",
    "gain_loss": "gain_loss_on_disposal",
}

GROUP_POOL = "Block pool"
GROUP_RATE_APPLIED = "Rate application"
GROUP_CLOSING = "Closing"

IT_BLOCK_LINE_FIELDS = {
    "total_depreciation": "total_depreciation",
    "closing_wdv": "closing_wdv",
    "capital_gain_or_loss": "capital_gain_or_loss",
}

_PROVISO_180 = (
    "Held for 180 days or more in the year, so the full prescribed rate applies "
    "(s.32(1) proviso)."
)
_PROVISO_UNDER_180 = (
    "Held for less than 180 days in the year, so only half the prescribed rate "
    "applies (s.32(1) proviso)."
)


def build_schedule_ii_trace(
    inp: AssetDepreciationInput,
    result: AssetDepreciationResult,
    *,
    fy_label: str,
    is_projection: bool = False,
    computed_at: Optional[str] = None,
) -> CalcTrace:
    i = result.intermediates
    res_pct = inp.residual_pct if inp.residual_pct is not None else Decimal("5.00")
    method_label = "WDV — written down value" if result.method == "WDV" else "SLM — straight line"
    cost = fmt_money(inp.original_cost)

    b = TraceBuilder(
        title=f"Depreciation — Companies Act Schedule II — FY {fy_label}",
        basis=(
            f"{method_label}; useful life {inp.useful_life_months} months; "
            f"residual {fmt_pct(res_pct)}%; original cost {cost}"
        ),
        is_projection=is_projection,
        computed_at=computed_at,
    )

    # --- Inputs ----------------------------------------------------------------
    b.add_input("original_cost", GROUP_INPUTS, "Original cost", cost, unit="money")
    b.add_input("residual_pct", GROUP_INPUTS, "Residual value %", fmt_pct(res_pct), unit="percent")
    b.add_money(
        "residual_value",
        GROUP_INPUTS,
        "Residual value",
        f"Original cost{MUL}Residual value %",
        f"{cost}{MUL}{fmt_pct(res_pct)}%",
        result.residual_value,
    )
    b.add_input(
        "useful_life_months",
        GROUP_INPUTS,
        "Useful life",
        fmt_int(inp.useful_life_months),
        unit="months",
    )
    b.add_money(
        "opening_gross_block",
        GROUP_INPUTS,
        "Opening gross block",
        "",
        "",
        result.opening_gross_block,
        emphasis=True,
        note=(
            "Nil — the asset was capitalized during this year, so it enters as an addition."
            if i.get("is_addition")
            else None
        ),
    )
    b.add_money(
        "opening_accumulated_depreciation",
        GROUP_INPUTS,
        "Opening accumulated depreciation",
        "",
        "",
        result.opening_accumulated_dep,
    )
    if i.get("is_addition"):
        b.add_money(
            "opening_carrying_amount",
            GROUP_INPUTS,
            "Opening carrying amount",
            "",
            "",
            result.opening_carrying_amount,
            note="Nil: the asset had not been capitalized at the start of the year.",
        )
    elif inp.opening_wdv is not None:
        b.add_money(
            "opening_carrying_amount",
            GROUP_INPUTS,
            "Opening carrying amount",
            "Stated carrying amount",
            "",
            result.opening_carrying_amount,
            note=(
                "Taken as stated and not re-derived. An impaired or revalued asset's "
                "written-down value is not cost less accumulated depreciation."
            ),
        )
    else:
        b.add_money(
            "opening_carrying_amount",
            GROUP_INPUTS,
            "Opening carrying amount",
            f"Opening gross block{SUB}Opening accumulated depreciation",
            f"{fmt_money(result.opening_gross_block)}{SUB}{fmt_money(result.opening_accumulated_dep)}",
            result.opening_carrying_amount,
        )

    # --- Rate ------------------------------------------------------------------
    b.add_money(
        "depreciable_base",
        GROUP_RATE,
        "Depreciable base",
        f"Original cost{SUB}Residual value",
        f"{cost}{SUB}{fmt_money(result.residual_value)}",
        i["depreciable_base"],
    )
    b.add(
        "useful_years",
        GROUP_RATE,
        "Useful life in years",
        f"Useful life in months{DIV}12",
        f"{fmt_int(inp.useful_life_months)}{DIV}12",
        fmt_dec(i["useful_years"]),
        unit="count",
    )
    if result.method == "WDV":
        rate_pct = fmt_dec(i["wdv_rate"] * Decimal("100"))
        b.add(
            "wdv_rate",
            GROUP_RATE,
            "Schedule II WDV rate",
            f"(1{SUB}(Residual value{DIV}Original cost)^(1{DIV}n)){MUL}100",
            f"(1{SUB}({fmt_money(result.residual_value)}{DIV}{cost})^(1{DIV}{fmt_dec(i['useful_years'])})){MUL}100",
            rate_pct,
            unit="percent",
        )
        b.add_money(
            "annual_depreciation",
            GROUP_RATE,
            "Depreciation at the full-year rate",
            f"Carrying amount{MUL}WDV rate",
            f"{fmt_money(i['carrying_for_calc'])}{MUL}{rate_pct}%",
            i["annual_dep"],
        )
    else:
        b.add_money(
            "annual_depreciation",
            GROUP_RATE,
            "Depreciation at the full-year rate",
            f"Depreciable base{DIV}Useful life in years",
            f"{fmt_money(i['depreciable_base'])}{DIV}{fmt_dec(i['useful_years'])}",
            i["annual_dep"],
        )

    # --- Charge for the year ---------------------------------------------------
    b.add(
        "active_days",
        GROUP_CHARGE,
        "Days held in this year",
        "Period the asset was on the register during the year",
        f"{i['start_active']} → {i['end_active']}",
        fmt_int(i["active_days"]),
        unit="days",
    )
    b.add_input(
        "total_fy_days",
        GROUP_CHARGE,
        "Days in the financial year",
        fmt_int(i["total_fy_days"]),
        unit="days",
    )
    if i["active_days"] != i["total_fy_days"]:
        b.add_money(
            "prorata_depreciation",
            GROUP_CHARGE,
            "Pro-rata charge",
            f"Full-year depreciation{MUL}Days held{DIV}Days in year",
            f"{fmt_money(i['annual_dep'])}{MUL}{fmt_int(i['active_days'])}{DIV}{fmt_int(i['total_fy_days'])}",
            i["dep_before_cap"],
            note=(
                "Depreciation is charged only for the days the asset was on the "
                "register during the year."
            ),
        )
    if i["dep_before_cap"] > i["max_dep_allowed"]:
        b.add_money(
            "residual_cap",
            GROUP_CHARGE,
            "Cap on the charge",
            f"Depreciable base{SUB}Opening accumulated depreciation",
            f"{fmt_money(i['depreciable_base'])}{SUB}{fmt_money(result.opening_accumulated_dep)}",
            i["max_dep_allowed"],
            note=(
                "The charge is capped so accumulated depreciation never exceeds the "
                "depreciable base — the asset cannot be written below its residual value."
            ),
        )
    b.add_money(
        "depreciation_for_year",
        GROUP_CHARGE,
        "Depreciation for the year",
        "Lower of the charge and the remaining depreciable base",
        f"lower of {fmt_money(i['dep_before_cap'])} and {fmt_money(i['max_dep_allowed'])}",
        result.depreciation_for_year,
        emphasis=True,
    )

    # --- Roll-forward ----------------------------------------------------------
    b.add_money("additions", GROUP_ROLL, "Additions", "", "", result.additions)
    b.add_money("disposals", GROUP_ROLL, "Disposals", "", "", result.disposals)
    b.add_money(
        "closing_gross_block",
        GROUP_ROLL,
        "Closing gross block",
        f"Opening gross block{ADD}Additions{SUB}Disposals",
        f"{fmt_money(result.opening_gross_block)}{ADD}{fmt_money(result.additions)}"
        f"{SUB}{fmt_money(result.disposals)}",
        result.closing_gross_block,
    )
    if result.is_disposed:
        b.add_money(
            "closing_accumulated_depreciation",
            GROUP_ROLL,
            "Closing accumulated depreciation",
            "",
            "",
            result.closing_accumulated_dep,
            note=(
                "Nil: the asset left the register during the year, so its accumulated "
                "depreciation is removed with it."
            ),
        )
        b.add_money(
            "closing_carrying_amount",
            GROUP_ROLL,
            "Closing carrying amount",
            "",
            "",
            result.closing_carrying_amount,
            emphasis=True,
            note="Nil: the asset was disposed of during the year.",
        )
    else:
        b.add_money(
            "closing_accumulated_depreciation",
            GROUP_ROLL,
            "Closing accumulated depreciation",
            f"Opening accumulated depreciation{ADD}Depreciation for the year",
            f"{fmt_money(result.opening_accumulated_dep)}{ADD}{fmt_money(result.depreciation_for_year)}",
            result.closing_accumulated_dep,
        )
        b.add_money(
            "closing_carrying_amount",
            GROUP_ROLL,
            "Closing carrying amount",
            f"Opening carrying amount{ADD}Additions{SUB}Depreciation for the year",
            f"{fmt_money(result.opening_carrying_amount)}{ADD}{fmt_money(result.additions)}"
            f"{SUB}{fmt_money(result.depreciation_for_year)}",
            result.closing_carrying_amount,
            emphasis=True,
        )
    b.add(
        "remaining_useful_life",
        GROUP_ROLL,
        "Remaining useful life",
        f"Total life in days{MUL}(Depreciable base{SUB}Consumed){DIV}Depreciable base",
        f"{fmt_int(i['total_life_days'])}{MUL}({fmt_money(i['depreciable_base'])}"
        f"{SUB}{fmt_money(i['consumed'])}){DIV}{fmt_money(i['depreciable_base'])}",
        fmt_int(result.remaining_useful_life_days),
        unit="days",
    )
    b.add(
        "effective_rate_pct",
        GROUP_ROLL,
        "Effective rate on cost",
        f"Depreciation for the year{DIV}Original cost{MUL}100",
        f"{fmt_money(result.depreciation_for_year)}{DIV}{cost}{MUL}100",
        fmt_dec(result.effective_rate_pct),
        unit="percent",
    )

    # --- Disposal --------------------------------------------------------------
    if result.is_disposed:
        proceeds = inp.sale_proceeds if inp.sale_proceeds is not None else Decimal("0.00")
        b.add_money(
            "nbv_at_disposal",
            GROUP_DISPOSAL,
            "Carrying amount at disposal",
            f"Opening carrying amount{ADD}Additions{SUB}Depreciation for the year",
            f"{fmt_money(result.opening_carrying_amount)}{ADD}{fmt_money(result.additions)}"
            f"{SUB}{fmt_money(result.depreciation_for_year)}",
            i["nbv_at_disposal"],
        )
        b.add_money("sale_proceeds", GROUP_DISPOSAL, "Sale proceeds", "", "", proceeds)
        b.add_money(
            "gain_loss",
            GROUP_DISPOSAL,
            "Gain / (loss) on disposal",
            f"Sale proceeds{SUB}Carrying amount at disposal",
            f"{fmt_money(proceeds)}{SUB}{fmt_money(i['nbv_at_disposal'])}",
            result.gain_loss_on_disposal,
            emphasis=True,
        )

    return b.build()


def build_it_block_trace(
    inp: ItBlockDepreciationInput,
    result: ItBlockDepreciationResult,
    *,
    fy_label: str,
    asset_name: Optional[str] = None,
    asset_contribution: Optional[Decimal] = None,
    is_projection: bool = False,
    computed_at: Optional[str] = None,
) -> CalcTrace:
    """A block-wise trace.

    Income Tax depreciation is computed on the block, not the asset. When an asset's
    context is supplied the trace names that asset's share, so nobody reads the block's
    figure as belonging to the one asset they were looking at.
    """
    i = result.intermediates
    rate = fmt_pct(result.prescribed_rate)
    branch = i.get("branch", "standard")

    b = TraceBuilder(
        title=f"Depreciation — Income Tax Act, block — FY {fy_label}",
        basis=f"Block {inp.block_name}; prescribed rate {rate}%",
        is_projection=is_projection,
        computed_at=computed_at,
    )

    # --- Block pool ------------------------------------------------------------
    b.add_input("prescribed_rate", GROUP_POOL, "Prescribed rate", rate, unit="percent")
    b.add_money("opening_wdv", GROUP_POOL, "Opening written-down value", "", "", result.opening_wdv)
    b.add_money(
        "additions_more_than_180",
        GROUP_POOL,
        "Additions held 180 days or more",
        "",
        "",
        result.additions_more_than_180,
        note=_PROVISO_180,
    )
    b.add_money(
        "additions_less_than_180",
        GROUP_POOL,
        "Additions held under 180 days",
        "",
        "",
        result.additions_less_than_180,
        note=_PROVISO_UNDER_180,
    )
    if asset_contribution is not None:
        b.add_money(
            "asset_contribution",
            GROUP_POOL,
            f"Of which {asset_name or 'this asset'}",
            "",
            "",
            asset_contribution,
            note=(
                "Income Tax depreciation is computed on the whole block, not per asset. "
                "This is this asset's share of the block, shown for context only."
            ),
        )
    b.add_money(
        "realized_from_sales",
        GROUP_POOL,
        "Sale proceeds realized",
        "",
        "",
        result.realized_from_sales,
    )
    b.add_money(
        "balance_before_depreciation",
        GROUP_POOL,
        "Balance before depreciation",
        f"Opening WDV{ADD}Additions held 180 days or more{ADD}Additions held under 180 days"
        f"{SUB}Sale proceeds",
        f"{fmt_money(result.opening_wdv)}{ADD}{fmt_money(result.additions_more_than_180)}"
        f"{ADD}{fmt_money(result.additions_less_than_180)}{SUB}{fmt_money(result.realized_from_sales)}",
        result.balance_before_depreciation,
    )

    # --- Rate application ------------------------------------------------------
    if branch == "standard":
        b.add_money(
            "full_pool",
            GROUP_RATE_APPLIED,
            "Full-rate pool",
            f"Opening WDV{ADD}Additions held 180 days or more",
            f"{fmt_money(result.opening_wdv)}{ADD}{fmt_money(result.additions_more_than_180)}",
            i["full_pool"],
        )
        sales_exceed_full_pool = result.realized_from_sales > i["full_pool"]
        if sales_exceed_full_pool:
            b.add_money(
                "remaining_full_pool",
                GROUP_RATE_APPLIED,
                "Full-rate pool after sales",
                f"Full-rate pool{SUB}Sale proceeds, floored at 0",
                f"{fmt_money(i['full_pool'])}{SUB}{fmt_money(result.realized_from_sales)}"
                " → floored to 0.00",
                i["remaining_full_pool"],
                note=(
                    "Sale proceeds exceeded the full-rate pool, so this pool cannot go "
                    "negative — it is floored at zero and the excess is absorbed by the "
                    "half-rate pool below."
                ),
            )
            excess_sales = i["excess_sales"]
            if excess_sales > result.additions_less_than_180:
                b.add_money(
                    "remaining_half_pool",
                    GROUP_RATE_APPLIED,
                    "Half-rate pool after sales",
                    f"Additions held under 180 days{SUB}Excess sale proceeds, floored at 0",
                    f"{fmt_money(result.additions_less_than_180)}{SUB}{fmt_money(excess_sales)}"
                    " → floored to 0.00",
                    i["remaining_half_pool"],
                    note=(
                        "Sale proceeds are set against the full-rate pool first, then the "
                        "half-rate pool; the excess absorbed here cannot take this pool "
                        "negative, so it is floored at zero."
                    ),
                )
            else:
                b.add_money(
                    "remaining_half_pool",
                    GROUP_RATE_APPLIED,
                    "Half-rate pool after sales",
                    f"Additions held under 180 days{SUB}Excess sale proceeds",
                    f"{fmt_money(result.additions_less_than_180)}{SUB}{fmt_money(excess_sales)}",
                    i["remaining_half_pool"],
                    note="Sale proceeds are set against the full-rate pool first, then the half-rate pool.",
                )
        else:
            b.add_money(
                "remaining_full_pool",
                GROUP_RATE_APPLIED,
                "Full-rate pool after sales",
                f"Full-rate pool{SUB}Sale proceeds",
                f"{fmt_money(i['full_pool'])}{SUB}{fmt_money(result.realized_from_sales)}",
                i["remaining_full_pool"],
            )
            b.add_money(
                "remaining_half_pool",
                GROUP_RATE_APPLIED,
                "Half-rate pool after sales",
                "",
                "",
                i["remaining_half_pool"],
                note="Sale proceeds are set against the full-rate pool first, then the half-rate pool.",
            )
        b.add_money(
            "depreciation_full_rate",
            GROUP_RATE_APPLIED,
            "Depreciation at the full rate",
            f"Remaining full-rate pool{MUL}Prescribed rate",
            f"{fmt_money(i['remaining_full_pool'])}{MUL}{rate}%",
            result.depreciation_full_rate,
        )
        b.add_money(
            "depreciation_half_rate",
            GROUP_RATE_APPLIED,
            "Depreciation at half the rate",
            f"Remaining half-rate pool{MUL}Prescribed rate{DIV}2",
            f"{fmt_money(i['remaining_half_pool'])}{MUL}{rate}%{DIV}2",
            result.depreciation_half_rate,
        )
        b.add_money(
            "total_depreciation",
            GROUP_RATE_APPLIED,
            "Total depreciation for the block",
            f"Full-rate depreciation{ADD}Half-rate depreciation",
            f"{fmt_money(result.depreciation_full_rate)}{ADD}{fmt_money(result.depreciation_half_rate)}",
            result.total_depreciation,
            emphasis=True,
        )
    else:
        b.add_money(
            "total_depreciation",
            GROUP_RATE_APPLIED,
            "Total depreciation for the block",
            "",
            "",
            result.total_depreciation,
            emphasis=True,
            note=(
                "No depreciation is allowed on a block whose sale proceeds exceeded the "
                "whole pool."
                if branch == "stcg"
                else "No depreciation is allowed on a block that ceased to exist during the year."
            ),
        )

    # --- Closing ---------------------------------------------------------------
    if branch == "standard":
        b.add_money(
            "closing_wdv",
            GROUP_CLOSING,
            "Closing written-down value",
            f"Balance before depreciation{SUB}Total depreciation",
            f"{fmt_money(result.balance_before_depreciation)}{SUB}{fmt_money(result.total_depreciation)}",
            result.closing_wdv,
            emphasis=True,
        )
    else:
        b.add_money(
            "closing_wdv",
            GROUP_CLOSING,
            "Closing written-down value",
            "",
            "",
            result.closing_wdv,
            emphasis=True,
            note="The block is extinguished, so nothing is carried forward.",
        )

    if branch == "stcg":
        b.add_money(
            "capital_gain_or_loss",
            GROUP_CLOSING,
            "Short-term capital gain",
            f"Sale proceeds{SUB}(Opening WDV{ADD}Additions)",
            f"{fmt_money(result.realized_from_sales)}{SUB}{fmt_money(i['total_pool'])}",
            result.capital_gain_or_loss,
            emphasis=True,
            note=(
                "Section 50: the proceeds exceeded the whole block, so no depreciation is "
                "allowed and the excess is taxable as a short-term capital gain."
            ),
        )
    elif branch == "stcl":
        b.add_money(
            "capital_gain_or_loss",
            GROUP_CLOSING,
            "Short-term capital loss",
            f"Opening WDV{ADD}Additions{SUB}Sale proceeds",
            f"{fmt_money(i['total_pool'])}{SUB}{fmt_money(result.realized_from_sales)}",
            result.capital_gain_or_loss,
            emphasis=True,
            note=(
                "Section 50: every asset in the block was disposed of, so the balance left "
                "is a short-term capital loss and no depreciation is allowed."
            ),
        )

    return b.build()
