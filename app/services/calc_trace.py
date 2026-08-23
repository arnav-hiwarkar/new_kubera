"""Presentation-layer calculation traces.

A trace explains a computed figure: an ordered list of steps, each carrying the
symbolic formula, the same formula with this entity's values substituted in, and the
result.

Two rules make the trace trustworthy:

  * Formatting happens here, once, using the same quantization the engines use. A
    trace therefore cannot display a number that differs from the figure it explains.
  * Nothing reads a trace back to compute anything. It is output, never input, so it
    never becomes a second source of truth.

Labels, formulae and statutory wording live in `calc_trace_builders`, not here.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from app.services.asset_costing import money

__all__ = [
    "CalcStep",
    "CalcTrace",
    "TraceBuilder",
    "fmt_dec",
    "fmt_int",
    "fmt_money",
    "fmt_pct",
]


def fmt_money(value: Any) -> str:
    """Money for display: two places, en-US grouping, no currency symbol.

    The symbol is added by the renderer from the step's unit. Baking it in here would
    duplicate it inside substitution strings, which read as arithmetic.
    """
    return f"{money(value):,.2f}"


def fmt_dec(value: Any) -> str:
    """A plain decimal number: two places, grouped, no symbol or sign word."""
    if value is None:
        return "0.00"
    return f"{Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def fmt_pct(value: Any) -> str:
    """A percentage's digits, without the sign. Same shape as fmt_dec — the separate
    name is so a call site reads as a rate rather than an arbitrary number."""
    return fmt_dec(value)


def fmt_int(value: Any) -> str:
    if value is None:
        return "0"
    return f"{int(value):,}"


@dataclass(frozen=True)
class CalcStep:
    """One line of a calculation.

    `formula` and `substitution` are empty for a step that is a plain input rather
    than a derivation; the renderer omits those lines instead of showing blanks.
    """

    key: str
    group: str
    label: str
    formula: str
    substitution: str
    result: str
    unit: str = "none"  # money | percent | days | months | count | none
    emphasis: bool = False  # the figure shown on the page
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "group": self.group,
            "label": self.label,
            "formula": self.formula,
            "substitution": self.substitution,
            "result": self.result,
            "unit": self.unit,
            "emphasis": self.emphasis,
            "note": self.note,
        }


@dataclass(frozen=True)
class CalcTrace:
    title: str
    basis: str
    steps: tuple = ()
    is_projection: bool = False
    computed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "basis": self.basis,
            "steps": [s.to_dict() for s in self.steps],
            "is_projection": self.is_projection,
            "computed_at": self.computed_at,
        }


class TraceBuilder:
    """Accumulates steps in computation order, then freezes them into a CalcTrace."""

    def __init__(
        self,
        title: str,
        basis: str,
        is_projection: bool = False,
        computed_at: Optional[str] = None,
    ) -> None:
        self._title = title
        self._basis = basis
        self._is_projection = is_projection
        self._computed_at = computed_at
        self._steps: list = []

    def add(
        self,
        key: str,
        group: str,
        label: str,
        formula: str,
        substitution: str,
        result: str,
        unit: str = "none",
        emphasis: bool = False,
        note: Optional[str] = None,
    ) -> "TraceBuilder":
        self._steps.append(
            CalcStep(
                key=key,
                group=group,
                label=label,
                formula=formula,
                substitution=substitution,
                result=result,
                unit=unit,
                emphasis=emphasis,
                note=note,
            )
        )
        return self

    def add_input(
        self,
        key: str,
        group: str,
        label: str,
        result: str,
        unit: str = "none",
        emphasis: bool = False,
        note: Optional[str] = None,
    ) -> "TraceBuilder":
        """A given value rather than a derivation — no formula, no substitution."""
        return self.add(key, group, label, "", "", result, unit=unit, emphasis=emphasis, note=note)

    def add_money(
        self,
        key: str,
        group: str,
        label: str,
        formula: str,
        substitution: str,
        value: Any,
        emphasis: bool = False,
        note: Optional[str] = None,
    ) -> "TraceBuilder":
        """Formats `value` as money. A None value adds nothing: an absent figure is
        omitted rather than rendered as a blank or a misleading zero."""
        if value is None:
            return self
        return self.add(
            key,
            group,
            label,
            formula,
            substitution,
            fmt_money(value),
            unit="money",
            emphasis=emphasis,
            note=note,
        )

    def build(self) -> CalcTrace:
        return CalcTrace(
            title=self._title,
            basis=self._basis,
            steps=tuple(self._steps),
            is_projection=self._is_projection,
            computed_at=self._computed_at,
        )
