"""P1b — acquisition costing arithmetic.

Pure functions, no DB. These are the figures that become the depreciation base, so
they are asserted to the paisa.
"""
from decimal import Decimal

import pytest

from app.models.asset_masters import ItcTreatment
from app.services.asset_costing import (
    AcquisitionCostInput,
    DiscountType,
    allocate_per_unit,
    compute_acquisition_cost,
    compute_residual_value,
    compute_warranty_expiry,
)

D = Decimal


def _inp(**kw) -> AcquisitionCostInput:
    base = dict(quantity=1, unit_basic_price=D("1000.00"), gst_rate=D("18"))
    base.update(kw)
    return AcquisitionCostInput(**base)


def test_intra_state_splits_into_cgst_and_sgst():
    r = compute_acquisition_cost(
        _inp(quantity=50, supplier_state_code="27", place_of_supply_state_code="27")
    )
    assert r.gross_basic_price == D("50000.00")
    assert r.net_basic_price == D("50000.00")
    assert r.gst_split_basis == "intra_state"
    assert r.cgst_amount == D("4500.00")
    assert r.sgst_amount == D("4500.00")
    assert r.igst_amount == D("0.00")
    assert r.total_gst == D("9000.00")
    # Eligible ITC is the default: recoverable, so it stays out of cost.
    assert r.recoverable_gst == D("9000.00")
    assert r.capitalizable_gst == D("0.00")
    assert r.landed_cost == D("50000.00")
    assert r.total_acquisition_outlay == D("59000.00")
    assert r.per_unit_cost == D("1000.00")


def test_inter_state_uses_igst():
    r = compute_acquisition_cost(
        _inp(quantity=50, supplier_state_code="27", place_of_supply_state_code="29")
    )
    assert r.gst_split_basis == "inter_state"
    assert r.igst_amount == D("9000.00")
    assert r.cgst_amount == D("0.00")
    assert r.sgst_amount == D("0.00")
    assert r.total_gst == D("9000.00")


def test_unknown_states_are_flagged_not_guessed_silently():
    r = compute_acquisition_cost(_inp(supplier_state_code=None, place_of_supply_state_code="27"))
    # Falls back to the common case but says so, so the UI can prompt.
    assert r.gst_split_basis == "assumed_intra_state"
    assert r.cgst_amount == r.sgst_amount == D("90.00")


def test_blocked_itc_is_capitalized_into_the_depreciation_base():
    """A motor car: Sec 17(5) blocks the credit, so GST becomes cost."""
    r = compute_acquisition_cost(
        _inp(
            unit_basic_price=D("1000000.00"),
            gst_rate=D("28"),
            itc_treatment=ItcTreatment.blocked,
            supplier_state_code="27",
            place_of_supply_state_code="27",
        )
    )
    assert r.total_gst == D("280000.00")
    assert r.recoverable_gst == D("0.00")
    assert r.capitalizable_gst == D("280000.00")
    assert r.landed_cost == D("1280000.00")
    # Cash out is the same either way — only the split changes.
    assert r.total_acquisition_outlay == D("1280000.00")


def test_partial_itc_splits_recoverable_and_capitalizable():
    r = compute_acquisition_cost(
        _inp(
            quantity=50,
            itc_treatment=ItcTreatment.partial,
            itc_eligible_pct=D("60"),
            supplier_state_code="27",
            place_of_supply_state_code="27",
        )
    )
    assert r.total_gst == D("9000.00")
    assert r.recoverable_gst == D("5400.00")
    assert r.capitalizable_gst == D("3600.00")
    assert r.landed_cost == D("53600.00")
    # Recoverable + capitalizable must always exhaust the GST — no lost paisa.
    assert r.recoverable_gst + r.capitalizable_gst == r.total_gst


def test_partial_itc_requires_a_percentage():
    with pytest.raises(ValueError, match="itc_eligible_pct"):
        compute_acquisition_cost(_inp(itc_treatment=ItcTreatment.partial))


def test_percentage_discount_reduces_the_taxable_value():
    r = compute_acquisition_cost(
        _inp(
            quantity=10,
            discount_type=DiscountType.percent,
            discount_value=D("10"),
            supplier_state_code="27",
            place_of_supply_state_code="27",
        )
    )
    assert r.gross_basic_price == D("10000.00")
    assert r.discount_amount == D("1000.00")
    assert r.net_basic_price == D("9000.00")
    # GST is charged on the discounted value, not the list price.
    assert r.total_gst == D("1620.00")


def test_absolute_discount_cannot_exceed_gross():
    with pytest.raises(ValueError, match="discount"):
        compute_acquisition_cost(_inp(discount_value=D("5000.00")))


def test_incidental_costs_are_capitalized_and_paid():
    r = compute_acquisition_cost(
        _inp(
            freight_cost=D("2000.00"),
            installation_cost=D("3000.00"),
            other_capitalizable_cost=D("500.00"),
            supplier_state_code="27",
            place_of_supply_state_code="27",
        )
    )
    # Eligible ITC, so GST is out of cost but incidentals are in.
    assert r.landed_cost == D("6500.00")
    assert r.total_acquisition_outlay == D("6680.00")  # 1000 + 180 GST + 5500


def test_manual_overrides_tie_the_entry_to_the_invoice():
    """Computed GST must be overridable to the paisa or entries won't reconcile."""
    r = compute_acquisition_cost(
        _inp(
            supplier_state_code="27",
            place_of_supply_state_code="27",
            cgst_amount_override=D("89.99"),
            sgst_amount_override=D("90.01"),
        )
    )
    assert r.cgst_amount == D("89.99")
    assert r.sgst_amount == D("90.01")
    assert r.total_gst == D("180.00")
    assert r.gst_split_basis == "manual"


def test_override_of_one_component_does_not_silently_keep_the_others():
    """Overriding to IGST on an intra-state entry zeroes CGST/SGST."""
    r = compute_acquisition_cost(
        _inp(
            supplier_state_code="27",
            place_of_supply_state_code="27",
            igst_amount_override=D("180.00"),
        )
    )
    assert r.igst_amount == D("180.00")
    assert r.cgst_amount == D("0.00")
    assert r.sgst_amount == D("0.00")
    assert r.total_gst == D("180.00")


def test_total_gst_always_equals_the_sum_of_components():
    for rate in ("0", "5", "12", "18", "28"):
        for net in ("100.01", "999.99", "1000.05", "33333.33"):
            r = compute_acquisition_cost(
                _inp(
                    unit_basic_price=D(net),
                    gst_rate=D(rate),
                    supplier_state_code="27",
                    place_of_supply_state_code="27",
                )
            )
            assert r.total_gst == r.cgst_amount + r.sgst_amount + r.igst_amount


# === Per-unit allocation ===

def test_allocation_sums_exactly_with_no_rounding_leak():
    """1000.00 over 3 units cannot be 333.33 x 3 — a paisa would vanish."""
    parts = allocate_per_unit(D("1000.00"), 3)
    assert parts == (D("333.34"), D("333.33"), D("333.33"))
    assert sum(parts) == D("1000.00")


@pytest.mark.parametrize(
    "total,qty",
    [
        ("1000.00", 3),
        ("50000.00", 50),
        ("1.00", 7),
        ("0.01", 2),
        ("123456.78", 13),
        ("999999.99", 999),
    ],
)
def test_allocation_always_ties_back(total, qty):
    parts = allocate_per_unit(Decimal(total), qty)
    assert len(parts) == qty
    assert sum(parts) == Decimal(total)


def test_allocation_is_exposed_on_the_breakdown():
    r = compute_acquisition_cost(_inp(quantity=3, unit_basic_price=D("333.3333")))
    assert len(r.unit_cost_allocation) == 3
    assert sum(r.unit_cost_allocation) == r.landed_cost


def test_quantity_must_be_positive():
    with pytest.raises(ValueError, match="quantity"):
        compute_acquisition_cost(_inp(quantity=0))


# === Small derived helpers ===

def test_residual_value_is_a_percentage_of_cost():
    assert compute_residual_value(D("100000.00"), D("5")) == D("5000.00")
    assert compute_residual_value(D("100000.00"), None) is None
    assert compute_residual_value(None, D("5")) is None


def test_warranty_expiry_is_derived_not_typed():
    from datetime import date

    assert compute_warranty_expiry(date(2026, 1, 15), 24) == date(2028, 1, 14)
    # Month-end arithmetic must not overflow into the next month.
    assert compute_warranty_expiry(date(2026, 1, 31), 1) == date(2026, 2, 27)
    assert compute_warranty_expiry(None, 12) is None
    assert compute_warranty_expiry(date(2026, 1, 1), None) is None
