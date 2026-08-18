"""Unit tests for reporting format and scaling utilities."""
from decimal import Decimal
import pytest

from app.services.reporting.format import (
    format_date,
    format_indian_number,
    format_money,
    format_number,
    format_percent,
    scale_for_units,
)


def test_indian_grouping():
    assert format_indian_number(1234567.5) == "12,34,567.50"
    assert format_indian_number(100000) == "1,00,000.00"
    assert format_indian_number(999.5) == "999.50"
    assert format_indian_number(0) == "0.00"
    assert format_indian_number(Decimal("0.00")) == "0.00"
    assert format_indian_number(-1234567.5) == "-12,34,567.50"
    assert format_indian_number(-100000) == "-1,00,000.00"
    assert format_indian_number(-50) == "-50.00"
    assert format_indian_number(12345678.9) == "1,23,45,678.90"
    assert format_indian_number(100) == "100.00"
    assert format_indian_number(1000) == "1,000.00"


def test_scale_for_units():
    val = Decimal("10000000.00")
    assert scale_for_units(val, "absolute") == Decimal("10000000.00")
    assert scale_for_units(val, "thousands") == Decimal("10000.00")
    assert scale_for_units(val, "lakhs") == Decimal("100.00")
    assert scale_for_units(val, "crores") == Decimal("1.00")


def test_format_money():
    assert format_money(Decimal("1234567.50"), units="absolute") == "12,34,567.50"
    assert format_money(Decimal("1234567.50"), units="lakhs") == "12.35"
    assert format_money(Decimal("-1234567.50"), units="absolute") == "-12,34,567.50"
    assert format_money(0) == "0.00"
    assert format_money(None) == "—"


def test_format_percent():
    assert format_percent(15) == "15.00%"
    assert format_percent(Decimal("7.5")) == "7.50%"
    assert format_percent(0) == "0.00%"
    assert format_percent(None) == "—"


def test_format_date():
    from datetime import date
    assert format_date(date(2025, 3, 31)) == "31/03/2025"
    assert format_date(None) == "—"
