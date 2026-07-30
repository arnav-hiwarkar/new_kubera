"""Acquisition costing for the fixed-asset register.

Pure functions over Decimal — no DB, no ORM. Everything here feeds the
depreciation base, so all money is quantized to two places with ROUND_HALF_UP and
the per-unit allocation is guaranteed to tie back to the total exactly.

The one rule worth restating, because getting it backwards misstates both the
balance sheet and the tax computation:

  * GST for which input tax credit IS available is recoverable — it is NOT part of
    the asset's cost.
  * GST for which credit is blocked (CGST Act s.17(5) — motor cars, etc.) or not
    taken is capitalized INTO the asset's cost and therefore depreciates.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Optional

from app.models.asset_masters import DiscountType, ItcTreatment

__all__ = [
    "AcquisitionCostInput",
    "AcquisitionCostBreakdown",
    "DiscountType",
    "allocate_per_unit",
    "compute_acquisition_cost",
    "compute_residual_value",
    "compute_warranty_expiry",
]

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value) -> Decimal:
    """Quantize to paise, half-up. The single rounding rule for the module."""
    if value is None:
        return ZERO
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class AcquisitionCostInput:
    quantity: int
    unit_basic_price: Decimal = ZERO
    discount_type: DiscountType = DiscountType.amount
    discount_value: Decimal = ZERO
    gst_rate: Decimal = ZERO
    # Place of supply is decided by comparing the supplier's state with the
    # receiving branch's state (falling back to the company's own state).
    supplier_state_code: Optional[str] = None
    place_of_supply_state_code: Optional[str] = None
    itc_treatment: ItcTreatment = ItcTreatment.eligible
    itc_eligible_pct: Optional[Decimal] = None
    freight_cost: Decimal = ZERO
    installation_cost: Decimal = ZERO
    other_capitalizable_cost: Decimal = ZERO
    # Any override switches the entry to manual mode so it reconciles with the
    # invoice to the paisa.
    cgst_amount_override: Optional[Decimal] = None
    sgst_amount_override: Optional[Decimal] = None
    igst_amount_override: Optional[Decimal] = None


@dataclass(frozen=True)
class AcquisitionCostBreakdown:
    gross_basic_price: Decimal
    discount_amount: Decimal
    net_basic_price: Decimal
    gst_split_basis: str  # intra_state | inter_state | assumed_intra_state | manual
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_gst: Decimal
    recoverable_gst: Decimal
    capitalizable_gst: Decimal
    freight_cost: Decimal
    installation_cost: Decimal
    other_capitalizable_cost: Decimal
    # The capitalized total: what goes on the balance sheet and depreciates.
    landed_cost: Decimal
    # Total cash out, including recoverable GST. Never the depreciation base.
    total_acquisition_outlay: Decimal
    per_unit_cost: Decimal
    unit_cost_allocation: tuple = field(default_factory=tuple)


def allocate_per_unit(total: Decimal, quantity: int) -> tuple:
    """Split `total` into `quantity` parts that sum to exactly `total`.

    Rounding down and multiplying back loses paise (1000.00 / 3 -> 333.33 x 3 =
    999.99), which would make the register disagree with the invoice. The
    remainder is handed out a paisa at a time to the leading units.
    """
    if quantity < 1:
        raise ValueError("quantity must be at least 1")
    total = money(total)
    base = (total / quantity).quantize(TWO_PLACES, rounding=ROUND_DOWN)
    parts = [base] * quantity
    remainder_paise = int(((total - base * quantity) / TWO_PLACES).to_integral_value())
    for i in range(remainder_paise):
        parts[i] += TWO_PLACES
    return tuple(parts)


def _split_gst(net_basic: Decimal, inp: AcquisitionCostInput) -> tuple:
    """Return (basis, cgst, sgst, igst)."""
    has_override = any(
        v is not None
        for v in (inp.cgst_amount_override, inp.sgst_amount_override, inp.igst_amount_override)
    )
    if has_override:
        return (
            "manual",
            money(inp.cgst_amount_override),
            money(inp.sgst_amount_override),
            money(inp.igst_amount_override),
        )

    rate = Decimal(inp.gst_rate or 0)
    supplier = (inp.supplier_state_code or "").strip() or None
    pos = (inp.place_of_supply_state_code or "").strip() or None

    if supplier is None or pos is None:
        # Most Indian purchases are intra-state; say so explicitly rather than
        # pretending we knew, so the UI can ask for the missing state.
        basis = "assumed_intra_state"
        inter_state = False
    else:
        inter_state = supplier != pos
        basis = "inter_state" if inter_state else "intra_state"

    if inter_state:
        return basis, ZERO, ZERO, money(net_basic * rate / 100)
    half = money(net_basic * rate / 200)
    return basis, half, half, ZERO


def compute_acquisition_cost(inp: AcquisitionCostInput) -> AcquisitionCostBreakdown:
    if inp.quantity is None or inp.quantity < 1:
        raise ValueError("quantity must be at least 1")

    gross = money(Decimal(inp.unit_basic_price or 0) * inp.quantity)

    discount_value = Decimal(inp.discount_value or 0)
    if discount_value < 0:
        raise ValueError("discount cannot be negative")
    if inp.discount_type == DiscountType.percent:
        if discount_value > 100:
            raise ValueError("discount percentage cannot exceed 100")
        discount = money(gross * discount_value / 100)
    else:
        discount = money(discount_value)
    if discount > gross:
        raise ValueError("discount cannot exceed the gross basic price")

    net_basic = money(gross - discount)

    basis, cgst, sgst, igst = _split_gst(net_basic, inp)
    total_gst = money(cgst + sgst + igst)

    if inp.itc_treatment == ItcTreatment.eligible:
        recoverable = total_gst
    elif inp.itc_treatment == ItcTreatment.blocked:
        recoverable = ZERO
    elif inp.itc_treatment == ItcTreatment.partial:
        if inp.itc_eligible_pct is None:
            raise ValueError("itc_eligible_pct is required when ITC treatment is partial")
        pct = Decimal(inp.itc_eligible_pct)
        if pct < 0 or pct > 100:
            raise ValueError("itc_eligible_pct must be between 0 and 100")
        recoverable = money(total_gst * pct / 100)
    else:  # pragma: no cover - enum is exhaustive
        raise ValueError(f"unknown ITC treatment: {inp.itc_treatment}")
    # Subtract rather than recompute so the two halves always exhaust the GST.
    capitalizable = money(total_gst - recoverable)

    freight = money(inp.freight_cost)
    installation = money(inp.installation_cost)
    other = money(inp.other_capitalizable_cost)
    incidentals = money(freight + installation + other)

    landed = money(net_basic + capitalizable + incidentals)
    outlay = money(net_basic + total_gst + incidentals)

    allocation = allocate_per_unit(landed, inp.quantity)

    return AcquisitionCostBreakdown(
        gross_basic_price=gross,
        discount_amount=discount,
        net_basic_price=net_basic,
        gst_split_basis=basis,
        cgst_amount=cgst,
        sgst_amount=sgst,
        igst_amount=igst,
        total_gst=total_gst,
        recoverable_gst=recoverable,
        capitalizable_gst=capitalizable,
        freight_cost=freight,
        installation_cost=installation,
        other_capitalizable_cost=other,
        landed_cost=landed,
        total_acquisition_outlay=outlay,
        per_unit_cost=money(landed / inp.quantity),
        unit_cost_allocation=allocation,
    )


def compute_residual_value(cost: Optional[Decimal], residual_pct: Optional[Decimal]) -> Optional[Decimal]:
    """Schedule II expresses residual value as a percentage of original cost
    (normally capped at 5%). Stored as a percentage; the amount is derived."""
    if cost is None or residual_pct is None:
        return None
    return money(Decimal(cost) * Decimal(residual_pct) / 100)


def _add_months(start: date, months: int) -> date:
    """Calendar-month addition, clamping to the last valid day of the target
    month so 31 Jan + 1 month is 28/29 Feb rather than an invalid date."""
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    # Days in the target month.
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)
    last_day = (next_month_start - date.resolution).day
    return date(year, month, min(start.day, last_day))


def compute_warranty_expiry(start: Optional[date], months: Optional[int]) -> Optional[date]:
    """Warranty is captured as a start date plus a period; expiry is derived as
    the day before the anniversary."""
    if start is None or months is None:
        return None
    return _add_months(start, months) - date.resolution
