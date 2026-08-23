"""Unit tests for Companies Act Schedule II depreciation engine."""
from datetime import date
from decimal import Decimal
import pytest

from app.services.depreciation import (
    AssetDepreciationInput,
    calculate_asset_depreciation,
)


def test_full_year_slm():
    """Test full year SLM depreciation on standard asset."""
    inp = AssetDepreciationInput(
        asset_id="a1",
        asset_name="Office Equipment",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2023, 4, 1),
        useful_life_months=60,  # 5 years
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
        is_pre_cutover=False,
        opening_accumulated_dep=Decimal("0.00"),
    )
    fy_start = date(2024, 4, 1)
    fy_end = date(2025, 3, 31)

    result = calculate_asset_depreciation(inp, fy_start, fy_end)

    assert result.opening_gross_block == Decimal("100000.00")
    assert result.closing_gross_block == Decimal("100000.00")
    assert result.residual_value == Decimal("5000.00")
    assert result.depreciation_for_year == Decimal("19000.00")
    assert result.closing_accumulated_dep == Decimal("19000.00")
    assert result.closing_carrying_amount == Decimal("81000.00")
    assert not result.is_part_year
    assert not result.is_disposed


def test_part_year_addition_slm():
    """Test pro-rata part-year addition put to use mid-year."""
    inp = AssetDepreciationInput(
        asset_id="a2",
        asset_name="New Laptop",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2024, 10, 1),
        useful_life_months=36,  # 3 years
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
        is_pre_cutover=False,
        opening_accumulated_dep=Decimal("0.00"),
    )
    fy_start = date(2024, 4, 1)
    fy_end = date(2025, 3, 31)  # 365 days, Oct 1 to Mar 31 is 182 days

    result = calculate_asset_depreciation(inp, fy_start, fy_end)

    assert result.opening_gross_block == Decimal("0.00")
    assert result.additions == Decimal("100000.00")
    assert result.closing_gross_block == Decimal("100000.00")
    assert result.is_part_year
    # Annual dep = 95,000 / 3 = 31,666.67
    # 182 days / 365 days * 31,666.666... = 15,789.95
    assert result.depreciation_for_year == Decimal("15789.95")
    assert result.closing_carrying_amount == Decimal("84210.05")


def test_pre_cutover_asset_with_opening_dep():
    """Test cutover asset depreciating over remaining useful life."""
    inp = AssetDepreciationInput(
        asset_id="a3",
        asset_name="Heavy Machinery",
        original_cost=Decimal("500000.00"),
        capitalization_date=date(2021, 4, 1),
        useful_life_months=120,  # 10 years total
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
        is_pre_cutover=True,
        opening_accumulated_dep=Decimal("190000.00"),  # 4 years elapsed
    )
    fy_start = date(2025, 4, 1)
    fy_end = date(2026, 3, 31)

    result = calculate_asset_depreciation(inp, fy_start, fy_end)

    assert result.opening_gross_block == Decimal("500000.00")
    assert result.opening_accumulated_dep == Decimal("190000.00")
    assert result.opening_carrying_amount == Decimal("310000.00")
    # Annual dep = (500,000 - 25,000) / 10 = 47,500
    assert result.depreciation_for_year == Decimal("47500.00")
    assert result.closing_accumulated_dep == Decimal("237500.00")
    assert result.closing_carrying_amount == Decimal("262500.00")


def test_pre_cutover_wdv_depreciates_from_opening_wdv_not_cost():
    """A pre-owned WDV asset must depreciate from the WDV carried in, not from cost.

    `opening_wdv` was collected on the form, required by validation, and then never
    passed to the engine — which derived the carrying amount from cost instead and,
    when that came to zero, fell back to full original cost.
    """
    inp = AssetDepreciationInput(
        asset_id="pc-wdv",
        asset_name="Pre-owned Press",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2021, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="WDV",
        is_pre_cutover=True,
        opening_accumulated_dep=Decimal("45070.00"),
        opening_wdv=Decimal("54930.00"),
    )
    result = calculate_asset_depreciation(inp, date(2025, 4, 1), date(2026, 3, 31))

    # Rate 0.4507 on the carried-in WDV of 54,930 = 24,756.95.
    # Depreciating from cost would have charged 45,070.
    assert result.opening_carrying_amount == Decimal("54930.00")
    assert result.depreciation_for_year == Decimal("24756.95")


def test_opening_wdv_wins_when_it_diverges_from_cost_less_accumulated():
    """An impaired asset's stated WDV is authoritative over the derived figure.

    cost - accumulated = 100000 - 40000 = 60000, but the asset was impaired to
    50000. The engine must depreciate the 50000 the user stated.
    """
    inp = AssetDepreciationInput(
        asset_id="pc-impaired",
        asset_name="Impaired Plant",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2021, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="WDV",
        is_pre_cutover=True,
        opening_accumulated_dep=Decimal("40000.00"),
        opening_wdv=Decimal("50000.00"),
    )
    result = calculate_asset_depreciation(inp, date(2025, 4, 1), date(2026, 3, 31))

    assert result.opening_carrying_amount == Decimal("50000.00")
    # 50,000 * 0.4507 = 22,535.00 (not 60,000 * 0.4507 = 27,042.00)
    assert result.depreciation_for_year == Decimal("22535.00")


def test_fully_depreciated_asset_does_not_restart_from_cost():
    """A carrying amount of zero means written down, not 'start again'.

    `carrying_for_calc = opening_carrying if opening_carrying > 0 else cost` sent any
    fully-depreciated WDV asset back to full original cost every year, held in check
    only by the residual cap.
    """
    inp = AssetDepreciationInput(
        asset_id="pc-spent",
        asset_name="Spent Machine",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2015, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="WDV",
        is_pre_cutover=True,
        opening_accumulated_dep=Decimal("95000.00"),
        opening_wdv=Decimal("5000.00"),
    )
    result = calculate_asset_depreciation(inp, date(2025, 4, 1), date(2026, 3, 31))

    # Already at residual: nothing further may be charged.
    assert result.depreciation_for_year == Decimal("0.00")
    assert result.closing_accumulated_dep == Decimal("95000.00")


def test_disposed_asset_mid_year():
    """Test asset disposed mid-year with depreciation up to disposal date and gain/loss."""
    inp = AssetDepreciationInput(
        asset_id="a4",
        asset_name="Delivery Van",
        original_cost=Decimal("200000.00"),
        capitalization_date=date(2022, 4, 1),
        useful_life_months=96,  # 8 years
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
        is_pre_cutover=False,
        opening_accumulated_dep=Decimal("47500.00"),  # 2 years prior
        disposal_date=date(2024, 9, 30),  # 183 days into FY 24-25
        disposal_type="sale",
        sale_proceeds=Decimal("160000.00"),
    )
    fy_start = date(2024, 4, 1)
    fy_end = date(2025, 3, 31)

    result = calculate_asset_depreciation(inp, fy_start, fy_end)

    assert result.is_disposed
    assert result.disposals == Decimal("200000.00")
    assert result.closing_gross_block == Decimal("0.00")
    # Annual dep = (200,000 - 10,000) / 8 = 23,750
    # Mid-year dep for 183 days = 23,750 * 183 / 365 = 11,907.53
    assert result.depreciation_for_year == Decimal("11907.53")
    # Total accumulated dep at disposal = 47,500 + 11,907.53 = 59,407.53
    assert result.disposal_accumulated_dep == Decimal("59407.53")
    assert result.closing_accumulated_dep == Decimal("0.00")
    assert result.closing_carrying_amount == Decimal("0.00")
    # Net book value at disposal = 200,000 - 59,407.53 = 140,592.47
    # Gain on sale = 160,000 - 140,592.47 = 19,407.53
    assert result.gain_loss_on_disposal == Decimal("19407.53")


def test_residual_value_cap():
    """Test asset reaching end of useful life stops depreciating at residual value."""
    inp = AssetDepreciationInput(
        asset_id="a5",
        asset_name="Old Printer",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2020, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
        is_pre_cutover=False,
        opening_accumulated_dep=Decimal("93000.00"),  # Only 2,000 left before reaching 5,000 residual
    )
    fy_start = date(2025, 4, 1)
    fy_end = date(2026, 3, 31)

    result = calculate_asset_depreciation(inp, fy_start, fy_end)

    # Full year dep would be 19,000, but capped at 2,000
    assert result.depreciation_for_year == Decimal("2000.00")
    assert result.closing_accumulated_dep == Decimal("95000.00")
    assert result.closing_carrying_amount == Decimal("5000.00")


def test_wdv_rate_derivation():
    """Test WDV rate derivation for 100k cost, 5k residual, 60 months life."""
    inp = AssetDepreciationInput(
        asset_id="w1",
        asset_name="WDV Machine",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2024, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="WDV",
    )
    fy_start = date(2024, 4, 1)
    fy_end = date(2025, 3, 31)

    result = calculate_asset_depreciation(inp, fy_start, fy_end)
    # Effective rate 45.07% corresponding to wdv_rate 0.4507
    assert result.effective_rate_pct == Decimal("45.07")
    assert result.depreciation_for_year == Decimal("45070.00")


def test_wdv_first_year_full():
    """Test full first year WDV charge."""
    inp = AssetDepreciationInput(
        asset_id="w2",
        asset_name="WDV Machine 2",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2024, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="WDV",
        opening_accumulated_dep=Decimal("0.00"),
    )
    fy_start = date(2024, 4, 1)
    fy_end = date(2025, 3, 31)

    result = calculate_asset_depreciation(inp, fy_start, fy_end)

    assert result.depreciation_for_year == Decimal("45070.00")
    assert result.closing_accumulated_dep == Decimal("45070.00")
    assert result.closing_carrying_amount == Decimal("54930.00")


def test_wdv_multi_year():
    """Test second year WDV charge opening at 54930.00."""
    inp = AssetDepreciationInput(
        asset_id="w3",
        asset_name="WDV Machine 3",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2023, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="WDV",
        opening_accumulated_dep=Decimal("45070.00"),
    )
    fy_start = date(2024, 4, 1)
    fy_end = date(2025, 3, 31)

    result = calculate_asset_depreciation(inp, fy_start, fy_end)

    assert result.opening_carrying_amount == Decimal("54930.00")
    # 54930 * 0.4507 = 24756.951 -> 24756.95
    assert result.depreciation_for_year == Decimal("24756.95")
    assert result.closing_accumulated_dep == Decimal("69826.95")
    assert result.closing_carrying_amount == Decimal("30173.05")


def test_wdv_zero_residual_raises():
    """WDV with zero residual value must raise ValueError."""
    inp = AssetDepreciationInput(
        asset_id="w_zero",
        asset_name="Zero Residual Machine",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2024, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("0.00"),
        dep_method="WDV",
    )
    fy_start = date(2024, 4, 1)
    fy_end = date(2025, 3, 31)

    with pytest.raises(ValueError, match="residual"):
        calculate_asset_depreciation(inp, fy_start, fy_end)


def test_wdv_residual_not_less_than_cost_raises():
    """WDV with residual >= cost must raise ValueError."""
    inp = AssetDepreciationInput(
        asset_id="w_high_res",
        asset_name="High Residual Machine",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2024, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("100.00"),
        dep_method="WDV",
    )
    fy_start = date(2024, 4, 1)
    fy_end = date(2025, 3, 31)

    with pytest.raises(ValueError, match="residual"):
        calculate_asset_depreciation(inp, fy_start, fy_end)


def test_slm_zero_residual_depreciates_to_zero():
    """SLM with 0% residual depreciates to zero (100% depreciable)."""
    inp = AssetDepreciationInput(
        asset_id="slm_zero",
        asset_name="Zero Residual SLM",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2024, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("0.00"),
        dep_method="SLM",
    )
    fy_start = date(2024, 4, 1)
    fy_end = date(2025, 3, 31)

    result = calculate_asset_depreciation(inp, fy_start, fy_end)

    assert result.residual_value == Decimal("0.00")
    assert result.depreciation_for_year == Decimal("20000.00")
    assert result.closing_carrying_amount == Decimal("80000.00")



def test_intermediates_slm_full_year():
    """The engine exposes its workings so a trace can be built without recomputing."""
    inp = AssetDepreciationInput(
        asset_id="i1",
        asset_name="Office Equipment",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2023, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
    )
    result = calculate_asset_depreciation(inp, date(2024, 4, 1), date(2025, 3, 31))
    i = result.intermediates

    assert i["depreciable_base"] == Decimal("95000.00")
    assert i["useful_years"] == Decimal("5")
    assert i["total_fy_days"] == 365
    assert i["active_days"] == 365
    assert i["start_active"] == "2024-04-01"
    assert i["end_active"] == "2025-03-31"
    assert i["is_addition"] is False
    assert i["annual_dep"] == Decimal("19000.00")
    assert i["dep_before_cap"] == Decimal("19000.00")
    # Nothing WDV-specific leaks into an SLM computation.
    assert "wdv_rate" not in i
    assert "nbv_at_disposal" not in i


def test_intermediates_are_internally_consistent_part_year():
    inp = AssetDepreciationInput(
        asset_id="i2",
        asset_name="New Laptop",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2024, 10, 1),
        useful_life_months=36,
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
    )
    result = calculate_asset_depreciation(inp, date(2024, 4, 1), date(2025, 3, 31))
    i = result.intermediates

    assert i["is_addition"] is True
    assert i["active_days"] <= i["total_fy_days"]
    assert i["start_active"] == "2024-10-01"
    assert i["depreciable_base"] == inp.original_cost - result.residual_value
    # The reported charge is the pro-rata figure, capped.
    assert result.depreciation_for_year == min(i["dep_before_cap"], i["max_dep_allowed"])


def test_intermediates_wdv_exposes_rate_and_base():
    inp = AssetDepreciationInput(
        asset_id="i3",
        asset_name="Machine",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2023, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="WDV",
        opening_accumulated_dep=Decimal("45072.00"),
    )
    result = calculate_asset_depreciation(inp, date(2024, 4, 1), date(2025, 3, 31))
    i = result.intermediates

    # Schedule II WDV rate: 1 - (5,000/100,000)^(1/5) = 0.4507
    assert i["wdv_rate"] == Decimal("0.4507")
    assert i["carrying_for_calc"] == result.opening_carrying_amount
    assert i["annual_dep"] == result.depreciation_for_year


def test_intermediates_disposal_exposes_nbv():
    inp = AssetDepreciationInput(
        asset_id="i4",
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
    result = calculate_asset_depreciation(inp, date(2024, 4, 1), date(2025, 3, 31))
    i = result.intermediates

    assert result.is_disposed is True
    assert i["nbv_at_disposal"] == (
        result.opening_carrying_amount + result.additions - result.depreciation_for_year
    )
    assert result.gain_loss_on_disposal == Decimal("70000.00") - i["nbv_at_disposal"]


def test_intermediates_expose_remaining_life_workings():
    inp = AssetDepreciationInput(
        asset_id="i5",
        asset_name="Old Press",
        original_cost=Decimal("100000.00"),
        capitalization_date=date(2020, 4, 1),
        useful_life_months=60,
        residual_pct=Decimal("5.00"),
        dep_method="SLM",
        is_pre_cutover=True,
        opening_accumulated_dep=Decimal("57000.00"),
    )
    result = calculate_asset_depreciation(inp, date(2024, 4, 1), date(2025, 3, 31))
    i = result.intermediates

    assert i["total_life_days"] == 60 * 30
    assert i["consumed"] == result.closing_accumulated_dep
