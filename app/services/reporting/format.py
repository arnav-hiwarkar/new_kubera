"""Unified monetary, numerical, and date formatting for backend reporting.

Single source of truth for Indian digit grouping (12,34,567.00), scale rounding
for Schedule III financial statements (thousands, lakhs, crores), and standard
report string representations.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

TWO_PLACES = Decimal("0.01")

UNIT_SCALES: dict[str, Decimal] = {
    "absolute": Decimal("1"),
    "thousands": Decimal("1000"),
    "lakhs": Decimal("100000"),
    "crores": Decimal("10000000"),
}


def to_decimal(v: Any) -> Decimal:
    """Coerce input to Decimal safely."""
    if v is None:
        return Decimal("0.00")
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).strip().replace(",", "")
    if not s:
        return Decimal("0.00")
    return Decimal(s)


def scale_for_units(value: Any, units: str = "absolute") -> Decimal:
    """Scale a monetary amount according to the chosen reporting units.
    
    Schedule III statements often require rounding off to thousands, lakhs, or crores.
    Quantized to 2 decimal places using ROUND_HALF_UP.
    """
    if value is None:
        return Decimal("0.00")
    dec = to_decimal(value)
    scale = UNIT_SCALES.get(units.lower(), Decimal("1"))
    return (dec / scale).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def format_indian_number(value: Any, decimals: int = 2) -> str:
    """Format a number with Indian digit grouping (e.g. 12,34,567.50).
    
    The last three digits form the first group, followed by repeating groups of two.
    """
    if value is None:
        return "—"
    dec = to_decimal(value)
    is_neg = dec < 0
    abs_dec = abs(dec)

    q_pattern = Decimal("1") if decimals == 0 else Decimal("0." + "0" * decimals)
    quantized = abs_dec.quantize(q_pattern, rounding=ROUND_HALF_UP)

    parts = str(quantized).split(".")
    int_part = parts[0]
    dec_part = parts[1] if len(parts) > 1 else ""

    if len(int_part) <= 3:
        grouped_int = int_part
    else:
        last3 = int_part[-3:]
        prefix = int_part[:-3]
        groups = []
        while len(prefix) > 2:
            groups.insert(0, prefix[-2:])
            prefix = prefix[:-2]
        if prefix:
            groups.insert(0, prefix)
        grouped_int = ",".join(groups) + "," + last3

    res = grouped_int
    if decimals > 0:
        res = f"{grouped_int}.{dec_part}"
    if is_neg:
        res = f"-{res}"
    return res


def format_money(
    value: Any,
    units: str = "absolute",
    indian: bool = True,
    symbol: bool = False,
) -> str:
    """Format monetary amount with units scaling and optional Indian digit grouping."""
    if value is None:
        return "—"
    scaled = scale_for_units(value, units)
    if indian:
        formatted = format_indian_number(scaled, decimals=2)
    else:
        formatted = f"{scaled:,.2f}"

    if symbol:
        if formatted.startswith("-"):
            return f"-₹ {formatted[1:]}"
        return f"₹ {formatted}"
    return formatted


def format_number(value: Any, decimals: int = 2, indian: bool = True) -> str:
    """Format a numeric quantity."""
    if value is None:
        return "—"
    if indian:
        return format_indian_number(value, decimals=decimals)
    dec = to_decimal(value)
    return f"{dec:,.{decimals}f}"


def format_percent(value: Any, decimals: int = 2) -> str:
    """Format a percentage value."""
    if value is None:
        return "—"
    dec = to_decimal(value)
    return f"{dec:.{decimals}f}%"


def format_date(d: Any) -> str:
    """Format date as DD/MM/YYYY."""
    if d is None:
        return "—"
    if isinstance(d, datetime):
        return d.strftime("%d/%m/%Y")
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return str(d)
