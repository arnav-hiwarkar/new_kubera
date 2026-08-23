"""Unit tests for calculation-trace builders."""
from datetime import date
from decimal import Decimal

import pytest

from app.services.calc_trace import fmt_money
from app.services.calc_trace_builders import (
    ADD,
    DIV,
    MUL,
    SCHEDULE_II_LINE_FIELDS,
    SUB,
    build_schedule_ii_trace,
)
from app.services.depreciation import (
    AssetDepreciationInput,
    calculate_asset_depreciation,
)

FY_START = date(2024, 4, 1)
FY_END = date(2025, 3, 31)


def _trace(inp: AssetDepreciationInput):
    result = calculate_asset_depreciation(inp, FY_START, FY_END)
    return result, build_schedule_ii_trace(inp, result, fy_label="2024-25")


def _step(trace, key):
    matches = [s for s in trace.steps if s.key == key]
    assert matches, f"no step {key!r} in {[s.key for s in trace.steps]}"
    return matches[0]


SLM_FULL_YEAR = AssetDepreciationInput(
    asset_id="a1",
    asset_name="Office Equipment",
    original_cost=Decimal("100000.00"),
    capitalization_date=date(2023, 4, 1),
    useful_life_months=60,
    residual_pct=Decimal("5.00"),
    dep_method="SLM",
)


def test_slm_full_year_shows_formula_substitution_and_result():
    _, trace = _trace(SLM_FULL_YEAR)

    base = _step(trace, "depreciable_base")
    assert base.formula == f"Original cost{SUB}Residual value"
    assert base.substitution == f"100,000.00{SUB}5,000.00"
    assert base.result == "95,000.00"
    assert base.unit == "money"

    annual = _step(trace, "annual_depreciation")
    assert annual.formula == f"Depreciable base{DIV}Useful life in years"
    assert annual.substitution == f"95,000.00{DIV}5.00"
    assert annual.result == "19,000.00"

    charge = _step(trace, "depreciation_for_year")
    assert charge.result == "19,000.00"
    assert charge.emphasis is True


def test_effective_rate_pct_formula_is_coherent_with_its_result():
    """The formula shown, worked by hand, must produce the result shown.

    The engine's `effective_rate_pct` is already a percentage (dep_for_year * 100 /
    cost), so the displayed formula and substitution must include the ×100 term —
    otherwise a reader working `19,000.00 ÷ 100,000.00` by hand gets 0.19, not the
    19.00 actually displayed.
    """
    _, trace = _trace(SLM_FULL_YEAR)
    step = _step(trace, "effective_rate_pct")
    assert step.formula == f"Depreciation for the year{DIV}Original cost{MUL}100"
    assert step.substitution == f"19,000.00{DIV}100,000.00{MUL}100"
    assert step.result == "19.00"
    assert step.unit == "percent"


def test_full_year_omits_the_prorata_step():
    """A full year has no pro-rata working, so showing one would be noise."""
    _, trace = _trace(SLM_FULL_YEAR)
    assert [s.key for s in trace.steps if s.key == "prorata_depreciation"] == []


def test_title_and_basis_state_the_inputs_used():
    _, trace = _trace(SLM_FULL_YEAR)
    assert trace.title == "Depreciation — Companies Act Schedule II — FY 2024-25"
    assert "SLM" in trace.basis
    assert "60 months" in trace.basis
    assert "5.00%" in trace.basis
    assert "100,000.00" in trace.basis
    assert trace.is_projection is False


def test_part_year_addition_shows_prorata_with_the_dates():
    inp = AssetDepreciationInput(
        asset_id="a2",
        asset_name="New Laptop",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2024, 10, 1),
        useful_life_months=36,
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
    )
    result, trace = _trace(inp)

    days = _step(trace, "active_days")
    assert days.substitution == "2024-10-01 → 2025-03-31"
    assert days.unit == "days"

    prorata = _step(trace, "prorata_depreciation")
    assert prorata.formula == f"Full-year depreciation{MUL}Days held{DIV}Days in year"
    assert prorata.substitution == f"31,666.67{MUL}182{DIV}365"
    assert prorata.note is not None

    assert _step(trace, "depreciation_for_year").result == fmt_money(result.depreciation_for_year)


def test_wdv_shows_the_schedule_ii_rate_formula():
    inp = AssetDepreciationInput(
        asset_id="a3",
        asset_name="Machine",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2023, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="WDV",
        opening_accumulated_dep=Decimal("45072.00"),
    )
    _, trace = _trace(inp)

    # Coherence check: the Schedule II formula yields a fraction (0.4507), but the
    # step displays a percentage (45.07). The formula and substitution shown must
    # carry the ×100 term, or working them by hand gives an answer 100x too small.
    rate = _step(trace, "wdv_rate")
    assert rate.formula == f"(1{SUB}(Residual value{DIV}Original cost)^(1{DIV}n)){MUL}100"
    assert rate.substitution == f"(1{SUB}(5,000.00{DIV}100,000.00)^(1{DIV}5.00)){MUL}100"
    assert rate.result == "45.07"
    assert rate.unit == "percent"

    annual = _step(trace, "annual_depreciation")
    assert annual.formula == f"Carrying amount{MUL}WDV rate"


def test_stated_cutover_wdv_is_labelled_as_stated():
    inp = AssetDepreciationInput(
        asset_id="a4",
        asset_name="Impaired Press",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2020, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
        is_pre_cutover=True,
        opening_accumulated_dep=Decimal("40000.00"),
        opening_wdv=Decimal("52000.00"),
    )
    _, trace = _trace(inp)

    opening = _step(trace, "opening_carrying_amount")
    assert opening.result == "52,000.00"
    assert opening.formula == "Stated carrying amount"
    assert "not re-derived" in (opening.note or "") or "stated" in (opening.note or "").lower()


def test_residual_cap_step_appears_only_when_the_cap_bites():
    """A nearly spent asset shows the cap as its own step, with the reason."""
    inp = AssetDepreciationInput(
        asset_id="a5",
        asset_name="Nearly Spent Rack",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2019, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
        opening_accumulated_dep=Decimal("90000.00"),
    )
    result, trace = _trace(inp)

    cap = _step(trace, "residual_cap")
    assert cap.formula == f"Depreciable base{SUB}Opening accumulated depreciation"
    assert cap.substitution == f"95,000.00{SUB}90,000.00"
    assert cap.result == "5,000.00"
    assert "residual" in (cap.note or "").lower()
    assert result.depreciation_for_year == Decimal("5000.00")

    # And it is absent when the ordinary charge fits.
    _, plain = _trace(SLM_FULL_YEAR)
    assert [s.key for s in plain.steps if s.key == "residual_cap"] == []


def test_disposal_year_adds_the_gain_loss_group():
    inp = AssetDepreciationInput(
        asset_id="a6",
        asset_name="Sold Van",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2022, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
        opening_accumulated_dep=Decimal("38000.00"),
        disposal_date=date(2024, 9, 30),
        disposal_type="sale",
        sale_proceeds=Decimal("70000.00"),
    )
    result, trace = _trace(inp)

    assert _step(trace, "nbv_at_disposal").result == fmt_money(
        result.intermediates["nbv_at_disposal"]
    )
    gain = _step(trace, "gain_loss")
    assert gain.formula == f"Sale proceeds{SUB}Carrying amount at disposal"
    assert gain.result == fmt_money(result.gain_loss_on_disposal)
    assert gain.emphasis is True

    closing = _step(trace, "closing_carrying_amount")
    assert closing.result == "0.00"
    assert "disposed" in (closing.note or "").lower()

    # A mid-year disposal shortens the active period too, but the reason is not that
    # the asset became available for use partway through the year.
    prorata = _step(trace, "prorata_depreciation")
    assert prorata.note == (
        "Depreciation is charged only for the days the asset was on the "
        "register during the year."
    )
    assert "became available for use" not in prorata.note


def test_no_disposal_group_when_the_asset_is_held():
    _, trace = _trace(SLM_FULL_YEAR)
    assert [s.key for s in trace.steps if s.key == "gain_loss"] == []


def test_steps_are_grouped_in_contiguous_runs():
    """The renderer emits a heading when `group` changes, so a group must not recur."""
    _, trace = _trace(SLM_FULL_YEAR)
    groups = [s.group for s in trace.steps]
    seen = []
    for g in groups:
        if not seen or seen[-1] != g:
            assert g not in seen, f"group {g!r} appears in two separate runs"
            seen.append(g)


@pytest.mark.parametrize(
    "inp",
    [
        SLM_FULL_YEAR,
        AssetDepreciationInput(
            asset_id="p1",
            asset_name="Part Year",
            original_cost=Decimal("100000.00"),
            capitalization_date=date(2024, 10, 1),
            useful_life_months=36,
            residual_pct=Decimal("5.00"),
            dep_method="SLM",
        ),
        AssetDepreciationInput(
            asset_id="p2",
            asset_name="WDV Machine",
            original_cost=Decimal("100000.00"),
            capitalization_date=date(2023, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="WDV",
            opening_accumulated_dep=Decimal("45072.00"),
        ),
        AssetDepreciationInput(
            asset_id="p3",
            asset_name="Disposed",
            original_cost=Decimal("100000.00"),
            capitalization_date=date(2022, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="SLM",
            opening_accumulated_dep=Decimal("38000.00"),
            disposal_date=date(2024, 9, 30),
            disposal_type="sale",
            sale_proceeds=Decimal("70000.00"),
        ),
    ],
    ids=["slm_full", "slm_part", "wdv", "disposed"],
)
def test_every_emphasis_step_matches_the_persisted_line_field(inp):
    """The invariant that makes the drawer trustworthy.

    Each emphasised step is a figure the page shows from the stored line. If a step's
    formatted result could differ from the stored field, the drawer would explain one
    number while the row displayed another.
    """
    result, trace = _trace(inp)
    emphasised = [s for s in trace.steps if s.emphasis]
    assert emphasised, "a trace must emphasise at least one figure"

    for step in emphasised:
        attr = SCHEDULE_II_LINE_FIELDS[step.key]
        assert step.result == fmt_money(getattr(result, attr)), (
            f"step {step.key!r} shows {step.result} but the line's {attr} is "
            f"{getattr(result, attr)}"
        )


from app.services.calc_trace_builders import (  # noqa: E402
    IT_BLOCK_LINE_FIELDS,
    build_it_block_trace,
)
from app.services.it_depreciation import (  # noqa: E402
    ItBlockDepreciationInput,
    calculate_it_block_depreciation,
)


def _it_trace(inp: ItBlockDepreciationInput, **kwargs):
    result = calculate_it_block_depreciation(inp)
    return result, build_it_block_trace(inp, result, fy_label="2024-25", **kwargs)


IT_STANDARD = ItBlockDepreciationInput(
    block_id="b1",
    block_name="Plant & Machinery (General)",
    prescribed_rate=Decimal("15.00"),
    opening_wdv=Decimal("500000.00"),
    additions_more_than_180=Decimal("100000.00"),
    additions_less_than_180=Decimal("40000.00"),
    realized_from_sales=Decimal("0.00"),
)


def test_it_standard_shows_both_rate_pools():
    _, trace = _it_trace(IT_STANDARD)

    assert trace.title == "Depreciation — Income Tax Act, block — FY 2024-25"
    assert "Plant & Machinery (General)" in trace.basis
    assert "15.00%" in trace.basis

    balance = _step(trace, "balance_before_depreciation")
    assert balance.formula == (
        f"Opening WDV{ADD}Additions held 180 days or more{ADD}Additions held under 180 days"
        f"{SUB}Sale proceeds"
    )
    assert balance.result == "640,000.00"

    full = _step(trace, "depreciation_full_rate")
    assert full.formula == f"Remaining full-rate pool{MUL}Prescribed rate"
    assert full.substitution == f"600,000.00{MUL}15.00%"
    assert full.result == "90,000.00"

    half = _step(trace, "depreciation_half_rate")
    assert half.formula == f"Remaining half-rate pool{MUL}Prescribed rate{DIV}2"
    assert half.substitution == f"40,000.00{MUL}15.00%{DIV}2"
    assert half.result == "3,000.00"

    total = _step(trace, "total_depreciation")
    assert total.result == "93,000.00"
    assert total.emphasis is True


def test_it_half_rate_addition_carries_the_statutory_note():
    _, trace = _it_trace(IT_STANDARD)
    note = _step(trace, "additions_less_than_180").note or ""
    assert "180" in note
    assert "32" in note  # s.32(1) proviso


def test_it_sales_spilling_into_the_half_rate_pool_is_visible():
    inp = ItBlockDepreciationInput(
        block_id="b2",
        block_name="Furniture",
        prescribed_rate=Decimal("10.00"),
        opening_wdv=Decimal("100000.00"),
        additions_more_than_180=Decimal("0.00"),
        additions_less_than_180=Decimal("50000.00"),
        realized_from_sales=Decimal("120000.00"),
    )
    _, trace = _it_trace(inp)

    assert _step(trace, "remaining_full_pool").result == "0.00"
    remaining_half = _step(trace, "remaining_half_pool")
    assert remaining_half.result == "30,000.00"
    assert "full-rate pool first" in (remaining_half.note or "")


def test_it_remaining_full_pool_substitution_reflects_the_clamp():
    inp = ItBlockDepreciationInput(
        block_id="b2b",
        block_name="Furniture",
        prescribed_rate=Decimal("10.00"),
        opening_wdv=Decimal("100000.00"),
        additions_more_than_180=Decimal("0.00"),
        additions_less_than_180=Decimal("50000.00"),
        realized_from_sales=Decimal("120000.00"),
    )
    _, trace = _it_trace(inp)

    step = _step(trace, "remaining_full_pool")
    assert step.formula == f"Full-rate pool{SUB}Sale proceeds, floored at 0"
    assert step.substitution == f"100,000.00{SUB}120,000.00 → floored to 0.00"
    assert step.result == "0.00"


def test_it_remaining_half_pool_is_a_plain_input_when_there_is_no_excess():
    _, trace = _it_trace(IT_STANDARD)

    step = _step(trace, "remaining_half_pool")
    assert step.formula == ""
    assert step.substitution == ""
    assert step.result == fmt_money(IT_STANDARD.additions_less_than_180)


def test_it_remaining_half_pool_substitution_shows_the_real_excess():
    inp = ItBlockDepreciationInput(
        block_id="b2",
        block_name="Furniture",
        prescribed_rate=Decimal("10.00"),
        opening_wdv=Decimal("100000.00"),
        additions_more_than_180=Decimal("0.00"),
        additions_less_than_180=Decimal("50000.00"),
        realized_from_sales=Decimal("120000.00"),
    )
    _, trace = _it_trace(inp)

    step = _step(trace, "remaining_half_pool")
    assert step.formula == f"Additions held under 180 days{SUB}Excess sale proceeds"
    assert step.substitution == f"50,000.00{SUB}20,000.00"
    assert step.result == "30,000.00"


def test_it_stcg_explains_why_no_depreciation_is_allowed():
    inp = ItBlockDepreciationInput(
        block_id="b3",
        block_name="Vehicles",
        prescribed_rate=Decimal("15.00"),
        opening_wdv=Decimal("50000.00"),
        additions_more_than_180=Decimal("0.00"),
        additions_less_than_180=Decimal("0.00"),
        realized_from_sales=Decimal("80000.00"),
    )
    result, trace = _it_trace(inp)

    assert result.has_stcg is True
    gain = _step(trace, "capital_gain_or_loss")
    assert gain.result == "30,000.00"
    assert "short-term capital gain" in (gain.note or "").lower()
    assert "50" in (gain.note or "")
    # The rate-application steps never ran, so they are not shown.
    assert [s.key for s in trace.steps if s.key == "depreciation_full_rate"] == []
    assert _step(trace, "total_depreciation").result == "0.00"


def test_it_stcl_explains_the_extinguished_block():
    inp = ItBlockDepreciationInput(
        block_id="b4",
        block_name="Computers",
        prescribed_rate=Decimal("40.00"),
        opening_wdv=Decimal("60000.00"),
        additions_more_than_180=Decimal("0.00"),
        additions_less_than_180=Decimal("0.00"),
        realized_from_sales=Decimal("10000.00"),
        all_assets_disposed=True,
    )
    result, trace = _it_trace(inp)

    assert result.has_stcl is True
    loss = _step(trace, "capital_gain_or_loss")
    assert "short-term capital loss" in (loss.note or "").lower()
    assert [s.key for s in trace.steps if s.key == "depreciation_full_rate"] == []


def test_it_asset_context_names_the_asset_share():
    _, trace = _it_trace(
        IT_STANDARD, asset_name="Server Rack", asset_contribution=Decimal("100000.00")
    )
    step = _step(trace, "asset_contribution")
    assert step.result == "100,000.00"
    assert "Server Rack" in step.label
    assert "block" in (step.note or "").lower()


def test_it_asset_context_is_omitted_when_not_supplied():
    _, trace = _it_trace(IT_STANDARD)
    assert [s.key for s in trace.steps if s.key == "asset_contribution"] == []


@pytest.mark.parametrize(
    "inp",
    [
        IT_STANDARD,
        ItBlockDepreciationInput(
            block_id="q1",
            block_name="STCG block",
            prescribed_rate=Decimal("15.00"),
            opening_wdv=Decimal("50000.00"),
            additions_more_than_180=Decimal("0.00"),
            additions_less_than_180=Decimal("0.00"),
            realized_from_sales=Decimal("80000.00"),
        ),
        ItBlockDepreciationInput(
            block_id="q2",
            block_name="STCL block",
            prescribed_rate=Decimal("40.00"),
            opening_wdv=Decimal("60000.00"),
            additions_more_than_180=Decimal("0.00"),
            additions_less_than_180=Decimal("0.00"),
            realized_from_sales=Decimal("10000.00"),
            all_assets_disposed=True,
        ),
    ],
    ids=["standard", "stcg", "stcl"],
)
def test_every_it_emphasis_step_matches_the_persisted_line_field(inp):
    result, trace = _it_trace(inp)
    emphasised = [s for s in trace.steps if s.emphasis]
    assert emphasised

    for step in emphasised:
        attr = IT_BLOCK_LINE_FIELDS[step.key]
        assert step.result == fmt_money(getattr(result, attr))
