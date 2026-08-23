"""Unit tests for calculation-trace primitives."""
from decimal import Decimal

from app.services.calc_trace import (
    CalcStep,
    CalcTrace,
    TraceBuilder,
    fmt_dec,
    fmt_int,
    fmt_money,
    fmt_pct,
)


def test_fmt_money_groups_en_us_with_two_places():
    # en-US grouping and no currency symbol: the renderer adds the symbol from the
    # step's unit, and the frontend's formatMoney groups the same way.
    assert fmt_money(Decimal("100000")) == "100,000.00"
    assert fmt_money(Decimal("1234567.891")) == "1,234,567.89"
    assert fmt_money(Decimal("-5000")) == "-5,000.00"
    assert fmt_money(None) == "0.00"


def test_fmt_dec_pct_and_int():
    assert fmt_dec(Decimal("5")) == "5.00"
    assert fmt_dec(Decimal("2.5")) == "2.50"
    assert fmt_dec(Decimal("1234.5678")) == "1,234.57"
    assert fmt_dec(None) == "0.00"
    # fmt_pct is fmt_dec under a name that reads correctly at the call site.
    assert fmt_pct(Decimal("15")) == "15.00"
    assert fmt_pct(Decimal("45.0712")) == "45.07"
    assert fmt_int(365) == "365"
    assert fmt_int(1825) == "1,825"


def test_trace_builder_collects_steps_in_order():
    b = TraceBuilder(title="T", basis="B")
    b.add_input("original_cost", "Inputs", "Original cost", fmt_money(Decimal("100000")), unit="money")
    b.add(
        "residual_value",
        "Inputs",
        "Residual value",
        formula="Cost x Residual %",
        substitution="100,000.00 x 5.00%",
        result=fmt_money(Decimal("5000")),
        unit="money",
    )
    b.add_money("depreciable_base", "Rate", "Depreciable base", "Cost - Residual value",
                "100,000.00 - 5,000.00", Decimal("95000"), emphasis=True)
    trace = b.build()

    assert isinstance(trace, CalcTrace)
    assert [s.key for s in trace.steps] == ["original_cost", "residual_value", "depreciable_base"]
    # An input step carries no formula, so the renderer can omit those lines.
    assert trace.steps[0].formula == ""
    assert trace.steps[0].substitution == ""
    assert trace.steps[2].emphasis is True
    assert trace.steps[2].result == "95,000.00"
    assert trace.is_projection is False
    assert trace.computed_at is None


def test_trace_builder_skips_none_results():
    """A step whose value is absent must not render as a blank row."""
    b = TraceBuilder(title="T", basis="B")
    b.add_money("gain_loss", "Disposal", "Gain on disposal", "Proceeds - NBV", "-", None)
    assert b.build().steps == ()


def test_to_dict_is_json_serializable():
    import json

    b = TraceBuilder(title="T", basis="B", is_projection=True, computed_at="2026-08-23T00:00:00Z")
    b.add_input("x", "G", "L", "1.00", unit="money", note="a note")
    payload = b.build().to_dict()

    assert json.loads(json.dumps(payload)) == payload
    assert payload["is_projection"] is True
    assert payload["steps"][0] == {
        "key": "x",
        "group": "G",
        "label": "L",
        "formula": "",
        "substitution": "",
        "result": "1.00",
        "unit": "money",
        "emphasis": False,
        "note": "a note",
    }


def test_calc_step_is_frozen():
    step = CalcStep(key="k", group="g", label="l", formula="", substitution="", result="1.00")
    try:
        step.result = "2.00"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("CalcStep must be immutable")


def test_fmt_dec_and_fmt_pct_use_round_half_up():
    """Verify ROUND_HALF_UP rounding mode for halfway cases, consistent with project constraints."""
    # Halfway cases that round up with ROUND_HALF_UP (not ROUND_HALF_EVEN)
    assert fmt_dec(Decimal("45.005")) == "45.01"
    assert fmt_pct(Decimal("2.345")) == "2.35"
