"""Unit tests for Income Tax Section 32 Block Depreciation engine."""
from decimal import Decimal
import pytest

from app.services.it_depreciation import (
    ItBlockDepreciationInput,
    calculate_it_block_depreciation,
)


def test_standard_block_full_rate():
    """Standard block with opening WDV and additions >= 180 days."""
    block = ItBlockDepreciationInput(
        block_id="b1",
        block_name="Plant & Machinery (General)",
        prescribed_rate=Decimal("15.00"),
        opening_wdv=Decimal("500000.00"),
        additions_more_than_180=Decimal("100000.00"),
        additions_less_than_180=Decimal("0.00"),
        realized_from_sales=Decimal("0.00"),
        all_assets_disposed=False,
    )

    res = calculate_it_block_depreciation(block)

    assert res.balance_before_depreciation == Decimal("600000.00")
    assert res.depreciation_full_rate == Decimal("90000.00")
    assert res.depreciation_half_rate == Decimal("0.00")
    assert res.total_depreciation == Decimal("90000.00")
    assert res.closing_wdv == Decimal("510000.00")
    assert not res.has_stcg
    assert not res.has_stcl


def test_180_day_rule_split():
    """Additions split between >= 180 days (full rate) and < 180 days (half rate)."""
    block = ItBlockDepreciationInput(
        block_id="b2",
        block_name="Computers & Software",
        prescribed_rate=Decimal("40.00"),
        opening_wdv=Decimal("100000.00"),
        additions_more_than_180=Decimal("50000.00"),
        additions_less_than_180=Decimal("50000.00"),
        realized_from_sales=Decimal("0.00"),
        all_assets_disposed=False,
    )

    res = calculate_it_block_depreciation(block)

    assert res.balance_before_depreciation == Decimal("200000.00")
    # Full pool = 100,000 + 50,000 = 150,000 @ 40% = 60,000
    assert res.depreciation_full_rate == Decimal("60000.00")
    # Half pool = 50,000 @ 20% = 10,000
    assert res.depreciation_half_rate == Decimal("10000.00")
    assert res.total_depreciation == Decimal("70000.00")
    assert res.closing_wdv == Decimal("130000.00")


def test_sales_deducted_from_full_pool_first():
    """Sales proceeds first reduce the full-rate pool, leaving remainder in half-rate pool."""
    block = ItBlockDepreciationInput(
        block_id="b3",
        block_name="Furniture & Fittings",
        prescribed_rate=Decimal("10.00"),
        opening_wdv=Decimal("100000.00"),
        additions_more_than_180=Decimal("50000.00"),
        additions_less_than_180=Decimal("50000.00"),
        realized_from_sales=Decimal("180000.00"),
        all_assets_disposed=False,
    )

    res = calculate_it_block_depreciation(block)

    assert res.balance_before_depreciation == Decimal("20000.00")
    # Full pool (150,000) exhausted by sales.
    assert res.depreciation_full_rate == Decimal("0.00")
    # Half pool: 50,000 - 30,000 = 20,000 @ 5% (half of 10%) = 1,000
    assert res.depreciation_half_rate == Decimal("1000.00")
    assert res.total_depreciation == Decimal("1000.00")
    assert res.closing_wdv == Decimal("19000.00")


def test_short_term_capital_gain_stcg():
    """When sales exceed opening WDV + additions, STCG arises u/s 50 and dep is zero."""
    block = ItBlockDepreciationInput(
        block_id="b4",
        block_name="Vehicles",
        prescribed_rate=Decimal("15.00"),
        opening_wdv=Decimal("100000.00"),
        additions_more_than_180=Decimal("50000.00"),
        additions_less_than_180=Decimal("0.00"),
        realized_from_sales=Decimal("200000.00"),
        all_assets_disposed=False,
    )

    res = calculate_it_block_depreciation(block)

    assert res.balance_before_depreciation == Decimal("-50000.00")
    assert res.total_depreciation == Decimal("0.00")
    assert res.closing_wdv == Decimal("0.00")
    assert res.has_stcg
    assert res.capital_gain_or_loss == Decimal("50000.00")


def test_short_term_capital_loss_stcl():
    """When all assets in block are disposed, STCL arises and closing WDV is zero."""
    block = ItBlockDepreciationInput(
        block_id="b5",
        block_name="Special Machinery",
        prescribed_rate=Decimal("30.00"),
        opening_wdv=Decimal("200000.00"),
        additions_more_than_180=Decimal("0.00"),
        additions_less_than_180=Decimal("0.00"),
        realized_from_sales=Decimal("80000.00"),
        all_assets_disposed=True,  # Block is empty at year-end
    )

    res = calculate_it_block_depreciation(block)

    assert res.balance_before_depreciation == Decimal("120000.00")
    assert res.total_depreciation == Decimal("0.00")
    assert res.closing_wdv == Decimal("0.00")
    assert res.has_stcl
    assert res.capital_gain_or_loss == Decimal("120000.00")
