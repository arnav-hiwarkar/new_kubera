# Calculation Trace Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "See the calculation" affordance beside every major derived figure in the assets module, opening a drawer that shows each computation step as formula, substituted values, and result.

**Architecture:** The depreciation engines emit their raw intermediates alongside their results; separate builder functions turn `(input, result, intermediates)` into a `CalcTrace` of labelled steps, which is persisted as JSONB on each depreciation line and also served fresh by a dry-run `explain` endpoint. Acquisition costing needs no backend change — a frontend adapter maps the existing cost fields to the same trace format. One `CalculationDrawer` component renders any trace and knows nothing about assets.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, Python Decimal; React 18, TypeScript, TanStack Query, Tailwind, framer-motion, Vitest + React Testing Library, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-23-calculation-trace-drawer-design.md`. Read it before starting.
- All money formatting in traces uses **en-US grouping with no currency symbol** — `"100,000.00"`. This matches the frontend's `formatMoney` (which is `formatSigned`, en-US grouping). The `₹` prefix is added by the renderer from the step's `unit`, never baked into the string. (The spec's illustrative `1,20,000.00` used Indian grouping; en-US is correct because that is what `DerivedRow` already renders.)
- Traces are presentation-only. Nothing in the codebase may read a trace back to compute a value.
- Statutory prose and labels live **only** in `app/services/calc_trace_builders.py` and the frontend adapter. The engines stay math-only.
- Money is quantized with `app.services.asset_costing.money` (2 places, ROUND_HALF_UP). Never use floats for money.
- Backend tests: `pytest`. Unit tests (no DB) go in `unit_tests/`; API tests (DB, httpx client) go in `tests/`.
- Frontend tests: `cd frontend && npm run test`. Follow the `vi.mock('@/api/hooks/...')` pattern used in `frontend/src/pages/company/assets/tabs/reopen.test.tsx`.
- Alembic head at plan time is `c1f2e3d4a5b6`. Task 6's migration must revise it.
- Commit after every task. Conventional-commit prefixes (`feat:`, `refactor:`, `test:`, `chore:`).

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `app/services/calc_trace.py` | `CalcStep`, `CalcTrace`, `TraceBuilder`, formatters. No domain knowledge. |
| `app/services/calc_trace_builders.py` | Turns engine `(input, result, intermediates)` into a `CalcTrace`. All labels, formulae, statutory notes. |
| `unit_tests/test_calc_trace.py` | Primitives and formatters. |
| `unit_tests/test_calc_trace_builders.py` | One case per engine branch, plus the emphasis-matches-line invariant. |
| `alembic/versions/d7a1c9b2e4f3_add_calc_trace_to_depreciation_lines.py` | Adds nullable `calc_trace` JSONB to both line tables. |
| `frontend/src/components/calc/types.ts` | `CalcStep`, `CalcTrace`, `TraceTab` TypeScript interfaces. |
| `frontend/src/components/calc/CalcStepRow.tsx` | Renders one step. |
| `frontend/src/components/calc/CalculationDrawer.tsx` | Renders a set of traces in the existing `Drawer`. |
| `frontend/src/components/calc/ExplainLink.tsx` | The trigger button. |
| `frontend/src/components/calc/traceToText.ts` | Plain-text rendering for the clipboard. |
| `frontend/src/components/calc/traceFromCostPreview.ts` | Acquisition-costing adapter. |
| `frontend/src/components/calc/index.ts` | Barrel export. |
| `frontend/src/components/calc/calc.test.tsx` | Drawer, step row, `traceToText`. |
| `frontend/src/components/calc/traceFromCostPreview.test.ts` | Adapter cases. |
| `frontend/src/pages/company/assets/tabs/DepreciationRunCard.tsx` | The run/compute/finalize/reopen card extracted out of `DepreciationTab`. |
| `frontend/src/pages/company/assets/tabs/explain.test.tsx` | Integration: open the drawer from the asset tabs. |

**Modified:**

| File | Change |
|---|---|
| `app/services/depreciation.py` | `intermediates` field on the result; `_remaining_life_days` returns its workings. |
| `app/services/it_depreciation.py` | `intermediates` field on the result, per branch. |
| `app/services/depreciation_query.py` | Extract `build_asset_depreciation_input` and `build_it_block_input`; persist traces. |
| `app/models/depreciation.py` | `calc_trace` column on both line models. |
| `app/schemas/depreciation.py` | `CalcStepSchema`, `CalcTraceSchema`, explain request/response; `calc_trace` on line responses. |
| `app/routers/depreciation.py` | `POST /api/v1/depreciation/explain`. |
| `frontend/src/api/endpoints/depreciation.ts` | `explain` client method. |
| `frontend/src/api/hooks/depreciation.ts` | `useExplainDepreciation`. |
| `frontend/src/pages/company/assets/tabs/SectionShell.tsx` | `DerivedRow` gains `onExplain`. |
| `frontend/src/pages/company/assets/tabs/DepreciationTab.tsx` | Run card extracted out; Derived Parameters gains a trigger. |
| `frontend/src/pages/company/assets/tabs/AcquisitionTab.tsx` | Cost build-up gains a trigger. |
| `frontend/src/pages/company/assets/tabs/TaxTab.tsx` | GST card gains a trigger. |

---

### Task 1: Trace primitives

**Files:**
- Create: `app/services/calc_trace.py`
- Test: `unit_tests/test_calc_trace.py`

**Interfaces:**
- Consumes: `app.services.asset_costing.money`
- Produces: `CalcStep`, `CalcTrace`, `TraceBuilder`, `fmt_money(value) -> str`, `fmt_dec(value) -> str`, `fmt_pct(value) -> str`, `fmt_int(value) -> str`

- [ ] **Step 1: Write the failing test**

Create `unit_tests/test_calc_trace.py`:

```python
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
    # ROUND_HALF_UP, not the decimal module's half-to-even default.
    assert fmt_dec(Decimal("45.005")) == "45.01"
    assert fmt_pct(Decimal("2.345")) == "2.35"
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unit_tests/test_calc_trace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.calc_trace'`

- [ ] **Step 3: Write the implementation**

Create `app/services/calc_trace.py`:

```python
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
from decimal import ROUND_HALF_UP, Decimal
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
    """A plain decimal number: two places, grouped, no symbol or sign word.

    ROUND_HALF_UP is explicit: the default decimal context rounds half to even, which
    would disagree with `money()` — and so with every figure on the page — on exact
    half-cent boundaries.
    """
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest unit_tests/test_calc_trace.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/calc_trace.py unit_tests/test_calc_trace.py
git commit -m "feat(assets): calculation trace primitives"
```

---

### Task 2: Schedule II engine emits intermediates

**Files:**
- Modify: `app/services/depreciation.py` — `_remaining_life_days` (lines 63-79), `AssetDepreciationResult` (lines 41-63), `calculate_asset_depreciation` (lines 82-231)
- Test: `unit_tests/test_depreciation.py` (append)

**Interfaces:**
- Produces: `AssetDepreciationResult.intermediates: dict` carrying keys `depreciable_base`, `useful_years`, `total_fy_days`, `active_days`, `start_active`, `end_active`, `is_addition`, `annual_dep`, `dep_before_cap`, `max_dep_allowed`, `total_life_days`, `consumed`, and — WDV only — `wdv_rate`, `carrying_for_calc`, and — disposal only — `nbv_at_disposal`.
- `_remaining_life_days` now returns `(days, total_life_days, consumed)`.

Note on approach: intermediates are accumulated into a local dict as the function proceeds, rather than assembled in one literal at the return. `wdv_rate` and `nbv_at_disposal` only exist on some paths, so a single literal would reference undefined locals.

- [ ] **Step 1: Write the failing test**

Append to `unit_tests/test_depreciation.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unit_tests/test_depreciation.py -v -k intermediates`
Expected: FAIL — `AttributeError: 'AssetDepreciationResult' object has no attribute 'intermediates'`

- [ ] **Step 3: Write the implementation**

In `app/services/depreciation.py`:

3a. Add the import and the result field. At the top, change the dataclass import:

```python
from dataclasses import dataclass, field
```

Add to the end of `AssetDepreciationResult` (after `gain_loss_on_disposal`):

```python
    gain_loss_on_disposal: Optional[Decimal] = None
    # The engine's own workings, for `calc_trace_builders` to label. Raw values only —
    # no formatting, no prose. Kept out of the returned figures so nothing downstream
    # can mistake a working for a result.
    intermediates: dict = field(default_factory=dict)
```

3b. `_remaining_life_days` returns its workings:

```python
def _remaining_life_days(
    useful_life_months: int, depreciable_base: Decimal, closing_acc_dep: Decimal
) -> tuple:
    """Remaining life implied by how much of the depreciable base is left.

    Returns (remaining_days, total_life_days, consumed) so a trace can show the
    working rather than asserting the answer.

    The previous form subtracted only the CURRENT year's active days from the total
    life, so it ignored every prior year and the whole of a pre-cutover asset's
    elapsed life — a four-year-old asset carried in at cutover reported its full
    original life minus one year. Reading it off accumulated depreciation instead is
    correct for pre-cutover assets and for assets with prior runs alike.
    """
    total_life_days = useful_life_months * 30
    if depreciable_base <= 0:
        return 0, total_life_days, Decimal("0.00")
    consumed = min(closing_acc_dep, depreciable_base)
    remaining = (depreciable_base - consumed) / depreciable_base
    return max(0, int(Decimal(total_life_days) * remaining)), total_life_days, consumed
```

3c. In `calculate_asset_depreciation`, immediately after `depreciable_base` is computed, open the dict:

```python
    depreciable_base = cost - res_val if cost > res_val else Decimal("0.00")
    inter: dict = {"depreciable_base": depreciable_base}
```

3d. After `total_fy_days` is computed, and after `is_addition`:

```python
    total_fy_days = (fy_end - fy_start).days + 1
    inter["total_fy_days"] = total_fy_days

    # Check if addition during this FY
    is_addition = cap_date > fy_start and cap_date <= fy_end
    inter["is_addition"] = is_addition
```

3e. After `active_days` is computed (replacing nothing, adding after the if/else):

```python
    if start_active > end_active or start_active > fy_end:
        active_days = 0
    else:
        active_days = (end_active - start_active).days + 1

    inter["active_days"] = active_days
    inter["start_active"] = start_active.isoformat()
    inter["end_active"] = end_active.isoformat()
```

3f. In the annual-depreciation block, record `useful_years`, the WDV specifics, and the pre-cap charge. Replace the whole block from `useful_years = ...` through the cap with:

```python
    # Annual depreciation computation
    useful_years = Decimal(inp.useful_life_months) / Decimal("12")
    inter["useful_years"] = useful_years
    if useful_years <= 0:
        annual_dep = Decimal("0.00")
        dep_for_year = Decimal("0.00")
    else:
        if inp.dep_method == "WDV":
            # Schedule II WDV rate formula: 1 - (residual / cost) ** (1 / n)
            if cost <= 0 or res_val <= 0:
                raise DepreciationDataError(
                    f"WDV depreciation for asset {inp.asset_id} requires a residual value "
                    f"greater than zero (cost={cost}, residual={res_val}). The Schedule II rate "
                    f"1-(s/c)^(1/n) is undefined at zero residual and would write the asset off "
                    f"entirely in year one."
                )
            if res_val >= cost:
                raise DepreciationDataError(
                    f"WDV depreciation for asset {inp.asset_id}: residual value {res_val} is not "
                    f"less than cost {cost}."
                )
            ratio = float(res_val / cost)
            wdv_rate = Decimal(str(round(1.0 - (ratio ** (1.0 / float(useful_years))), 4)))
            # An asset in its first year has no opening carrying amount yet, so it
            # depreciates from cost. Any other zero means the asset is written down —
            # falling back to cost there restarted a spent asset from scratch every
            # year, checked only by the residual cap.
            carrying_for_calc = cost if is_addition else opening_carrying
            inter["wdv_rate"] = wdv_rate
            inter["carrying_for_calc"] = carrying_for_calc
            raw_annual = carrying_for_calc * wdv_rate
        else:
            # SLM
            raw_annual = depreciable_base / useful_years

        annual_dep = money(raw_annual)

        if active_days == total_fy_days:
            dep_for_year = annual_dep
        elif active_days > 0:
            dep_for_year = money(raw_annual * Decimal(active_days) / Decimal(total_fy_days))
        else:
            dep_for_year = Decimal("0.00")

    inter["annual_dep"] = annual_dep
    # The charge before the residual cap is applied. The cap is a separate, visible
    # step in the trace, so the figure it acted on has to survive.
    inter["dep_before_cap"] = dep_for_year

    # Cap depreciation so accumulated depreciation does not exceed depreciable base
    max_dep_allowed = depreciable_base - opening_acc_dep if depreciable_base > opening_acc_dep else Decimal("0.00")
    inter["max_dep_allowed"] = max_dep_allowed
    if dep_for_year > max_dep_allowed:
        dep_for_year = max_dep_allowed
```

3g. In the disposal branch, record the NBV:

```python
        nbv_at_disposal = opening_carrying + additions - dep_for_year
        inter["nbv_at_disposal"] = nbv_at_disposal
        proceeds = inp.sale_proceeds if inp.sale_proceeds is not None else Decimal("0.00")
        gain_loss = money(proceeds - nbv_at_disposal)
```

3h. Unpack the remaining-life tuple and pass `intermediates` in the return:

```python
    remaining_days, total_life_days, consumed = _remaining_life_days(
        inp.useful_life_months, depreciable_base, closing_acc_dep
    )
    inter["total_life_days"] = total_life_days
    inter["consumed"] = consumed

    return AssetDepreciationResult(
        ...
        remaining_useful_life_days=remaining_days,
        ...
        gain_loss_on_disposal=gain_loss,
        intermediates=inter,
    )
```

(Keep every other field of the return exactly as it is; only `remaining_useful_life_days` changes from the inline call, and `intermediates` is added.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest unit_tests/test_depreciation.py -v`
Expected: PASS — all pre-existing tests still pass, plus the 5 new ones

- [ ] **Step 5: Commit**

```bash
git add app/services/depreciation.py unit_tests/test_depreciation.py
git commit -m "feat(assets): Schedule II engine exposes its intermediates"
```

---

### Task 3: Income Tax engine emits intermediates

**Files:**
- Modify: `app/services/it_depreciation.py` — `ItBlockDepreciationResult` (lines 31-48), `calculate_it_block_depreciation` (lines 51-139)
- Test: `unit_tests/test_it_depreciation.py` (append)

**Interfaces:**
- Produces: `ItBlockDepreciationResult.intermediates: dict` with `rate_fraction`, `half_rate_fraction`, `total_pool`, `branch` (`"standard" | "stcg" | "stcl"`), and — standard branch only — `full_pool`, `remaining_full_pool`, `remaining_half_pool`.

- [ ] **Step 1: Write the failing test**

Append to `unit_tests/test_it_depreciation.py`:

```python
def test_intermediates_standard_branch():
    block = ItBlockDepreciationInput(
        block_id="b1",
        block_name="Plant & Machinery (General)",
        prescribed_rate=Decimal("15.00"),
        opening_wdv=Decimal("500000.00"),
        additions_more_than_180=Decimal("100000.00"),
        additions_less_than_180=Decimal("40000.00"),
        realized_from_sales=Decimal("0.00"),
    )
    res = calculate_it_block_depreciation(block)
    i = res.intermediates

    assert i["branch"] == "standard"
    assert i["rate_fraction"] == Decimal("0.15")
    assert i["half_rate_fraction"] == Decimal("0.075")
    assert i["total_pool"] == Decimal("640000.00")
    assert i["full_pool"] == Decimal("600000.00")
    assert i["remaining_full_pool"] == Decimal("600000.00")
    assert i["remaining_half_pool"] == Decimal("40000.00")
    # The split reconciles with the reported charge.
    assert res.depreciation_full_rate == Decimal("90000.00")
    assert res.depreciation_half_rate == Decimal("3000.00")
    assert res.total_depreciation == res.depreciation_full_rate + res.depreciation_half_rate


def test_intermediates_sales_eat_into_pools():
    block = ItBlockDepreciationInput(
        block_id="b2",
        block_name="Furniture",
        prescribed_rate=Decimal("10.00"),
        opening_wdv=Decimal("100000.00"),
        additions_more_than_180=Decimal("0.00"),
        additions_less_than_180=Decimal("50000.00"),
        realized_from_sales=Decimal("120000.00"),
    )
    res = calculate_it_block_depreciation(block)
    i = res.intermediates

    assert i["branch"] == "standard"
    assert i["full_pool"] == Decimal("100000.00")
    # Sales are applied to the full-rate pool first, then spill into the half-rate pool.
    assert i["remaining_full_pool"] == Decimal("0.00")
    assert i["remaining_half_pool"] == Decimal("30000.00")


def test_intermediates_stcg_branch():
    block = ItBlockDepreciationInput(
        block_id="b3",
        block_name="Vehicles",
        prescribed_rate=Decimal("15.00"),
        opening_wdv=Decimal("50000.00"),
        additions_more_than_180=Decimal("0.00"),
        additions_less_than_180=Decimal("0.00"),
        realized_from_sales=Decimal("80000.00"),
    )
    res = calculate_it_block_depreciation(block)
    i = res.intermediates

    assert i["branch"] == "stcg"
    assert res.has_stcg is True
    assert i["total_pool"] == Decimal("50000.00")
    # The rate-application pools never came into existence on this path.
    assert "remaining_full_pool" not in i


def test_intermediates_stcl_branch():
    block = ItBlockDepreciationInput(
        block_id="b4",
        block_name="Computers",
        prescribed_rate=Decimal("40.00"),
        opening_wdv=Decimal("60000.00"),
        additions_more_than_180=Decimal("0.00"),
        additions_less_than_180=Decimal("0.00"),
        realized_from_sales=Decimal("10000.00"),
        all_assets_disposed=True,
    )
    res = calculate_it_block_depreciation(block)
    i = res.intermediates

    assert i["branch"] == "stcl"
    assert res.has_stcl is True
    assert "remaining_full_pool" not in i
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unit_tests/test_it_depreciation.py -v -k intermediates`
Expected: FAIL — `AttributeError: 'ItBlockDepreciationResult' object has no attribute 'intermediates'`

- [ ] **Step 3: Write the implementation**

In `app/services/it_depreciation.py`:

3a. Change the import:

```python
from dataclasses import dataclass, field
```

3b. Add to the end of `ItBlockDepreciationResult`:

```python
    has_stcl: bool
    # The engine's own workings, for `calc_trace_builders` to label. `branch` tells a
    # builder which path ran, so it does not have to re-derive it from the flags.
    intermediates: dict = field(default_factory=dict)
```

3c. In `calculate_it_block_depreciation`, build the dict progressively. After `balance_before_dep` is computed:

```python
    total_pool = opening + add_full + add_half
    balance_before_dep = total_pool - sales

    inter: dict = {
        "rate_fraction": rate_fraction,
        "half_rate_fraction": half_rate_fraction,
        "total_pool": total_pool,
    }
```

3d. In the STCG early return, add `intermediates={**inter, "branch": "stcg"}` as the last argument.

3e. In the STCL early return, add `intermediates={**inter, "branch": "stcl"}`.

3f. In the standard branch, record the pools and pass them through:

```python
    # Case 3: Standard depreciation calculation
    # Sales proceeds reduce the full-rate pool (opening + additions >= 180) first
    full_pool = opening + add_full
    if sales <= full_pool:
        remaining_full_pool = full_pool - sales
        remaining_half_pool = add_half
    else:
        remaining_full_pool = Decimal("0.00")
        excess_sales = sales - full_pool
        remaining_half_pool = max(Decimal("0.00"), add_half - excess_sales)

    inter.update(
        {
            "branch": "standard",
            "full_pool": full_pool,
            "remaining_full_pool": remaining_full_pool,
            "remaining_half_pool": remaining_half_pool,
        }
    )
```

and add `intermediates=inter` as the last argument of the final return.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest unit_tests/test_it_depreciation.py -v`
Expected: PASS — pre-existing tests plus the 4 new ones

- [ ] **Step 5: Commit**

```bash
git add app/services/it_depreciation.py unit_tests/test_it_depreciation.py
git commit -m "feat(assets): IT block engine exposes its intermediates"
```

---

### Task 4: Schedule II trace builder

**Files:**
- Create: `app/services/calc_trace_builders.py`
- Test: `unit_tests/test_calc_trace_builders.py`

**Interfaces:**
- Consumes: `CalcTrace`, `TraceBuilder`, `fmt_money`, `fmt_dec`, `fmt_pct`, `fmt_int` from Task 1; `AssetDepreciationInput`/`AssetDepreciationResult` with `intermediates` from Task 2.
- Produces:
  - `GROUP_INPUTS`, `GROUP_RATE`, `GROUP_CHARGE`, `GROUP_ROLL`, `GROUP_DISPOSAL` string constants
  - `MUL`, `DIV`, `SUB`, `ADD` operator constants
  - `SCHEDULE_II_LINE_FIELDS: dict[str, str]` — emphasis step key to `AssetDepreciationLine` attribute
  - `build_schedule_ii_trace(inp, result, *, fy_label: str, is_projection: bool = False, computed_at: str | None = None) -> CalcTrace`

The operator constants exist so a test never has to retype a Unicode `×` and mismatch it.

- [ ] **Step 1: Write the failing test**

Create `unit_tests/test_calc_trace_builders.py`:

```python
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

    rate = _step(trace, "wdv_rate")
    assert rate.formula == f"1{SUB}(Residual value{DIV}Original cost)^(1{DIV}n)"
    assert rate.substitution == f"1{SUB}(5,000.00{DIV}100,000.00)^(1{DIV}5.00)"
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unit_tests/test_calc_trace_builders.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.calc_trace_builders'`

- [ ] **Step 3: Write the implementation**

Create `app/services/calc_trace_builders.py`:

```python
"""Turns engine results into labelled calculation traces.

Everything a user reads lives here: step labels, formula wording, and the statutory
notes. The engines stay math-only and hand over raw `intermediates`, so this module
never recomputes anything — it only names and formats what the engine already did.

Statutory notes are deliberately sparse. They appear on the three rules that surprise
people (the pro-rata start, the residual cap, and — in the Income Tax builder — the
180-day half rate) and nowhere else, so the numbers stay readable.
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

__all__ = [
    "ADD",
    "DIV",
    "MUL",
    "SUB",
    "GROUP_CHARGE",
    "GROUP_DISPOSAL",
    "GROUP_INPUTS",
    "GROUP_RATE",
    "GROUP_ROLL",
    "SCHEDULE_II_LINE_FIELDS",
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
                "Depreciation is charged only for the days the asset was on the register "
                "during the year."
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest unit_tests/test_calc_trace_builders.py -v`
Expected: PASS — 13 passed (the parametrized invariant counts as 4)

If `test_part_year_addition_shows_prorata_with_the_dates` fails on the substitution
string, print the actual step and correct the expected numbers in the test — the
engine's figures are authoritative, the hand-computed expectations in the test are not.

- [ ] **Step 5: Commit**

```bash
git add app/services/calc_trace_builders.py unit_tests/test_calc_trace_builders.py
git commit -m "feat(assets): Schedule II calculation trace builder"
```

---

### Task 5: Income Tax block trace builder

**Files:**
- Modify: `app/services/calc_trace_builders.py`
- Test: `unit_tests/test_calc_trace_builders.py` (append)

**Interfaces:**
- Produces:
  - `GROUP_POOL = "Block pool"`, `GROUP_RATE_APPLIED = "Rate application"`, `GROUP_CLOSING = "Closing"`
  - `IT_BLOCK_LINE_FIELDS: dict[str, str]` — emphasis step key to `ItBlockDepreciationLine` attribute
  - `build_it_block_trace(inp, result, *, fy_label: str, asset_name: str | None = None, asset_contribution: Decimal | None = None, is_projection: bool = False, computed_at: str | None = None) -> CalcTrace`

`asset_name` and `asset_contribution` are supplied only by the explain endpoint, where the trace is being shown in the context of one asset. They add the `asset_contribution` step that says how much of the block is this asset.

- [ ] **Step 1: Write the failing test**

Append to `unit_tests/test_calc_trace_builders.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unit_tests/test_calc_trace_builders.py -v -k it_`
Expected: FAIL — `ImportError: cannot import name 'build_it_block_trace'`

- [ ] **Step 3: Write the implementation**

In `app/services/calc_trace_builders.py`, extend the imports:

```python
from app.services.it_depreciation import (
    ItBlockDepreciationInput,
    ItBlockDepreciationResult,
)
```

Add to `__all__`: `"GROUP_CLOSING"`, `"GROUP_POOL"`, `"GROUP_RATE_APPLIED"`, `"IT_BLOCK_LINE_FIELDS"`, `"build_it_block_trace"`.

Add the constants beside the existing groups:

```python
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
```

Append the builder:

```python
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
            "Additions held under 180 days, less any sale proceeds not absorbed above",
            f"{fmt_money(result.additions_less_than_180)} less any excess proceeds",
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest unit_tests/ -v`
Expected: PASS — the whole unit-test directory, including Tasks 1-4

- [ ] **Step 5: Commit**

```bash
git add app/services/calc_trace_builders.py unit_tests/test_calc_trace_builders.py
git commit -m "feat(assets): Income Tax block calculation trace builder"
```

---

### Task 6: Persist traces — migration, models, schemas

**Files:**
- Create: `alembic/versions/d7a1c9b2e4f3_add_calc_trace_to_depreciation_lines.py`
- Modify: `app/models/depreciation.py` — `AssetDepreciationLine`, `ItBlockDepreciationLine`
- Modify: `app/schemas/depreciation.py`
- Test: `tests/test_depreciation_api.py` (append)

**Interfaces:**
- Produces: `AssetDepreciationLine.calc_trace`, `ItBlockDepreciationLine.calc_trace` (both `dict | None`); Pydantic `CalcStepSchema`, `CalcTraceSchema`; `calc_trace` on both line response models.

Nullable is deliberate: lines from runs computed before this feature have no trace, and the drawer says so rather than inventing one.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_depreciation_api.py`:

```python
@pytest.mark.asyncio
async def test_line_response_carries_a_calc_trace(client: AsyncClient):
    """A computed run's lines explain themselves without a second request."""
    env = await setup_depreciation_environment(client, "admin_trace_line@testco.com")
    headers, fy_id = env["headers"], env["fy_id"]

    run = await client.post(
        "/api/v1/depreciation/runs", json={"financial_year_id": fy_id}, headers=headers
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]

    lines = await client.get(f"/api/v1/depreciation/runs/{run_id}/lines", headers=headers)
    assert lines.status_code == 200, lines.text
    line = lines.json()[0]

    trace = line["calc_trace"]
    assert trace is not None
    assert trace["is_projection"] is False
    assert trace["computed_at"] is not None
    assert "Schedule II" in trace["title"]

    keys = [s["key"] for s in trace["steps"]]
    assert "depreciable_base" in keys
    assert "depreciation_for_year" in keys

    # The invariant, end to end: what the drawer will show equals what the row shows.
    charge = next(s for s in trace["steps"] if s["key"] == "depreciation_for_year")
    assert charge["emphasis"] is True
    assert charge["result"] == f"{Decimal(line['depreciation_for_year']):,.2f}"


@pytest.mark.asyncio
async def test_it_line_response_carries_a_calc_trace(client: AsyncClient):
    env = await setup_depreciation_environment(client, "admin_trace_itline@testco.com")
    headers, fy_id = env["headers"], env["fy_id"]

    run = await client.post(
        "/api/v1/depreciation/runs", json={"financial_year_id": fy_id}, headers=headers
    )
    run_id = run.json()["id"]

    it_lines = await client.get(f"/api/v1/depreciation/runs/{run_id}/it-lines", headers=headers)
    assert it_lines.status_code == 200, it_lines.text
    # Only the asset's own block carries figures; find it by a non-zero pool.
    with_figures = [l for l in it_lines.json() if Decimal(l["balance_before_depreciation"]) > 0]
    assert with_figures, "expected at least one block with a balance"
    trace = with_figures[0]["calc_trace"]

    assert trace is not None
    assert "Income Tax" in trace["title"]
    keys = [s["key"] for s in trace["steps"]]
    assert "balance_before_depreciation" in keys
    assert "total_depreciation" in keys
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_depreciation_api.py -v -k calc_trace`
Expected: FAIL — `KeyError: 'calc_trace'` (the response model has no such field)

- [ ] **Step 3a: Add the migration**

Create `alembic/versions/d7a1c9b2e4f3_add_calc_trace_to_depreciation_lines.py`:

```python
"""add_calc_trace_to_depreciation_lines

Revision ID: d7a1c9b2e4f3
Revises: c1f2e3d4a5b6
Create Date: 2026-08-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd7a1c9b2e4f3'
down_revision: Union[str, None] = 'c1f2e3d4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, with no backfill. A trace records how a figure was arrived at using the
    # inputs of the moment; synthesising one now for a run computed months ago would
    # attach today's inputs to yesterday's number. Lines without a trace are shown as
    # exactly that, and the UI offers a clearly-labelled projection instead.
    for table in ("asset_depreciation_lines", "it_block_depreciation_lines"):
        op.add_column(
            table,
            sa.Column(
                "calc_trace",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade() -> None:
    for table in ("asset_depreciation_lines", "it_block_depreciation_lines"):
        op.drop_column(table, "calc_trace")
```

- [ ] **Step 3b: Add the model columns**

In `app/models/depreciation.py`, add the JSONB import:

```python
from sqlalchemy.dialects.postgresql import JSONB, UUID
```

Add to `AssetDepreciationLine`, after `gain_loss_on_disposal`:

```python
    # How this line's figures were arrived at, for display only. Nullable because
    # lines computed before traces existed have none, and because nothing may depend
    # on a trace being present.
    calc_trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

Add the identical column to `ItBlockDepreciationLine`, after `has_stcl`.

- [ ] **Step 3c: Add the Pydantic schemas**

In `app/schemas/depreciation.py`, add above `AssetDepreciationLineResponse`:

```python
class CalcStepSchema(BaseModel):
    """One line of a calculation, already formatted for display.

    `formula` and `substitution` are empty for a plain input rather than a derivation.
    """

    key: str
    group: str
    label: str
    formula: str
    substitution: str
    result: str
    unit: str = "none"
    emphasis: bool = False
    note: Optional[str] = None


class CalcTraceSchema(BaseModel):
    title: str
    basis: str
    steps: List[CalcStepSchema] = []
    is_projection: bool = False
    computed_at: Optional[str] = None
```

Add to `AssetDepreciationLineResponse` and to `ItBlockDepreciationLineResponse`, before `model_config`:

```python
    calc_trace: Optional[CalcTraceSchema] = None
```

- [ ] **Step 4: Run the migration and confirm the test still fails for the right reason**

Run: `alembic upgrade head`
Expected: the two columns are added, no error.

Run: `pytest tests/test_depreciation_api.py -v -k calc_trace`
Expected: FAIL — `assert trace is not None` (the column exists and serializes, but nothing writes it yet; Task 7 does)

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/d7a1c9b2e4f3_add_calc_trace_to_depreciation_lines.py app/models/depreciation.py app/schemas/depreciation.py tests/test_depreciation_api.py
git commit -m "feat(assets): calc_trace column and schema on depreciation lines"
```

---

### Task 7: Write traces during a depreciation run

**Files:**
- Modify: `app/services/depreciation_query.py` — the asset loop (lines ~203-283) and the block loop (lines ~300-397)
- Test: `tests/test_depreciation_api.py` (the two tests from Task 6 now pass)

**Interfaces:**
- Consumes: `build_schedule_ii_trace`, `build_it_block_trace` (Tasks 4-5)
- Produces: `AssetDepreciationLine.calc_trace` and `ItBlockDepreciationLine.calc_trace` populated on every newly computed run.

- [ ] **Step 1: Confirm the target tests fail**

Run: `pytest tests/test_depreciation_api.py -v -k calc_trace`
Expected: FAIL — `assert trace is not None`

- [ ] **Step 2: Write the implementation**

In `app/services/depreciation_query.py`, add to the imports:

```python
from app.services.calc_trace_builders import (
    build_it_block_trace,
    build_schedule_ii_trace,
)
```

At the top of `execute_depreciation_run`, after `fy_end` is bound, capture one timestamp for the whole run so every trace on a run agrees:

```python
    fy_start: date = fy.start_date
    fy_end: date = fy.end_date
    # One stamp for the whole run: traces from a single run must not disagree about
    # when they were computed.
    computed_at = datetime.now(timezone.utc).isoformat()
```

In the asset loop, after `calc = calculate_asset_depreciation(inp, fy_start, fy_end)`:

```python
        calc = calculate_asset_depreciation(inp, fy_start, fy_end)
        trace = build_schedule_ii_trace(
            inp, calc, fy_label=fy.label, computed_at=computed_at
        )
```

and add to the `AssetDepreciationLine(...)` constructor, after `gain_loss_on_disposal=calc.gain_loss_on_disposal,`:

```python
            calc_trace=trace.to_dict(),
```

In the block loop, after `it_calc = calculate_it_block_depreciation(it_inp)`:

```python
        it_calc = calculate_it_block_depreciation(it_inp)
        it_trace = build_it_block_trace(
            it_inp, it_calc, fy_label=fy.label, computed_at=computed_at
        )
```

and add to the `ItBlockDepreciationLine(...)` constructor, after `has_stcl=it_calc.has_stcl,`:

```python
            calc_trace=it_trace.to_dict(),
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `pytest tests/test_depreciation_api.py -v`
Expected: PASS — including the two `calc_trace` tests

- [ ] **Step 4: Run the whole backend suite for regressions**

Run: `pytest -q`
Expected: PASS — no existing test broken by the new column or the engine changes

- [ ] **Step 5: Commit**

```bash
git add app/services/depreciation_query.py
git commit -m "feat(assets): record calculation traces on depreciation runs"
```

---

### Task 8: Projection endpoint

**Files:**
- Modify: `app/services/depreciation_query.py` — extract two input builders out of `execute_depreciation_run`
- Modify: `app/schemas/depreciation.py` — explain request/response
- Modify: `app/routers/depreciation.py` — `POST /api/v1/depreciation/explain`
- Test: `tests/test_depreciation_api.py` (append)

**Interfaces:**
- Produces:
  - `build_asset_depreciation_input(asset: Asset, prior_line: AssetDepreciationLine | None) -> AssetDepreciationInput` — raises `DepreciationDataError` when the asset has no useful life
  - `build_it_block_input(block: ItAssetBlock, block_assets: list[Asset], prior_line: ItBlockDepreciationLine | None, fy_start: date, fy_end: date) -> ItBlockDepreciationInput`
  - `DepreciationExplainRequest {asset_id, financial_year_id}`, `DepreciationExplainResponse {companies_act, income_tax}`
  - `POST /api/v1/depreciation/explain`

The extraction is what guarantees a projection cannot disagree with a run: both call the same assembly and the same engine.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_depreciation_api.py`:

```python
@pytest.mark.asyncio
async def test_explain_returns_a_projection_before_any_run(client: AsyncClient):
    """The drawer is useful during data entry, not only after a run."""
    env = await setup_depreciation_environment(client, "admin_explain_pre@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": asset_id, "financial_year_id": fy_id},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()

    ca = body["companies_act"]
    assert ca["is_projection"] is True
    assert ca["computed_at"] is None
    keys = [s["key"] for s in ca["steps"]]
    assert "depreciable_base" in keys
    assert "depreciation_for_year" in keys

    # The asset in the fixture is in the PM-15 block, so the tax book is present too.
    assert body["income_tax"] is not None
    assert body["income_tax"]["is_projection"] is True
    it_keys = [s["key"] for s in body["income_tax"]["steps"]]
    assert "asset_contribution" in it_keys


@pytest.mark.asyncio
async def test_projection_matches_the_recorded_run(client: AsyncClient):
    """The strongest guarantee in the feature: same assembly, same engine, same steps."""
    env = await setup_depreciation_environment(client, "admin_explain_match@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    run = await client.post(
        "/api/v1/depreciation/runs", json={"financial_year_id": fy_id}, headers=headers
    )
    run_id = run.json()["id"]
    lines = await client.get(f"/api/v1/depreciation/runs/{run_id}/lines", headers=headers)
    recorded = next(l for l in lines.json() if l["asset_id"] == asset_id)["calc_trace"]

    projected = (
        await client.post(
            "/api/v1/depreciation/explain",
            json={"asset_id": asset_id, "financial_year_id": fy_id},
            headers=headers,
        )
    ).json()["companies_act"]

    # Everything except the projection markers must be identical.
    assert projected["title"] == recorded["title"]
    assert projected["basis"] == recorded["basis"]
    assert projected["steps"] == recorded["steps"]
    assert recorded["is_projection"] is False
    assert projected["is_projection"] is True


@pytest.mark.asyncio
async def test_explain_surfaces_the_engine_validation_message(client: AsyncClient):
    """Incomplete inputs are explained, not hidden behind a generic failure."""
    env = await setup_depreciation_environment(client, "admin_explain_422@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    # Strip the useful life the way an unfinished data-entry session would leave it.
    async with TestSessionLocal() as session:
        asset = await session.get(Asset, uuid.UUID(asset_id))
        asset.useful_life_months = None
        await session.commit()

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": asset_id, "financial_year_id": fy_id},
        headers=headers,
    )
    assert res.status_code == 422, res.text
    assert "useful life" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_explain_omits_the_tax_book_without_a_block(client: AsyncClient):
    env = await setup_depreciation_environment(client, "admin_explain_noblock@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    async with TestSessionLocal() as session:
        asset = await session.get(Asset, uuid.UUID(asset_id))
        asset.it_block_id = None
        await session.commit()

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": asset_id, "financial_year_id": fy_id},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["income_tax"] is None


@pytest.mark.asyncio
async def test_explain_is_tenant_scoped(client: AsyncClient):
    """Another company's asset id must not resolve."""
    mine = await setup_depreciation_environment(client, "admin_explain_mine@testco.com")
    theirs = await setup_depreciation_environment(client, "admin_explain_theirs@testco.com")

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": theirs["asset_id"], "financial_year_id": mine["fy_id"]},
        headers=mine["headers"],
    )
    assert res.status_code == 404, res.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_depreciation_api.py -v -k explain`
Expected: FAIL — 404/405 from FastAPI, the route does not exist

- [ ] **Step 3a: Extract the asset input builder**

In `app/services/depreciation_query.py`, add above `execute_depreciation_run`:

```python
def build_asset_depreciation_input(
    asset: Asset,
    prior_line: Optional[AssetDepreciationLine],
) -> AssetDepreciationInput:
    """Assemble one asset's Schedule II engine input.

    Shared by the run and by the projection endpoint, so a projection cannot disagree
    with the figure a run would record.
    """
    if asset.useful_life_months is None:
        raise DepreciationDataError(
            f"Asset {asset.id} ({asset.asset_name}) has no useful life specified"
        )

    cap_date = asset.capitalization_date or asset.available_for_use_date
    cost = asset.original_cost if asset.original_cost is not None else Decimal("0.00")
    residual_pct = asset.residual_pct if asset.residual_pct is not None else Decimal("5.00")
    method = "WDV" if asset.dep_method == DepreciationMethod.wdv else "SLM"

    # Once a prior run exists its closing figures are the truth and the cutover values
    # are history, so the stated openings only apply until the asset has been run once.
    if prior_line is not None:
        opening_acc = prior_line.closing_accumulated_depreciation
        opening_wdv_in = prior_line.closing_carrying_amount
    else:
        opening_acc = (
            asset.opening_accumulated_depreciation
            if asset.opening_accumulated_depreciation is not None
            else Decimal("0.00")
        )
        opening_wdv_in = asset.opening_wdv

    return AssetDepreciationInput(
        asset_id=str(asset.id),
        asset_name=asset.asset_name,
        original_cost=cost,
        capitalization_date=cap_date,
        useful_life_months=asset.useful_life_months,
        residual_pct=residual_pct,
        residual_value=asset.residual_value,
        dep_method=method,
        opening_accumulated_dep=opening_acc,
        opening_wdv=opening_wdv_in,
        disposal_date=asset.disposal_date,
        disposal_type=asset.disposal_type,
        sale_proceeds=asset.sale_proceeds,
        is_pre_cutover=asset.is_pre_cutover,
    )
```

Then in the asset loop of `execute_depreciation_run`, delete everything from
`if asset.useful_life_months is None:` down to the closing paren of the
`inp = AssetDepreciationInput(...)` literal, and replace with:

```python
        inp = build_asset_depreciation_input(asset, prior_asset_lines.get(asset.id))
```

Keep the two `continue` guards above it (capitalized after FY end, disposed before FY
start) exactly as they are — they need the FY bounds and belong to the loop.

- [ ] **Step 3b: Extract the block input builder**

Add above `execute_depreciation_run`:

```python
def build_it_block_input(
    block: ItAssetBlock,
    block_assets: List[Asset],
    prior_line: Optional[ItBlockDepreciationLine],
    fy_start: date,
    fy_end: date,
) -> ItBlockDepreciationInput:
    """Assemble one Income Tax block's engine input from the assets in it."""
    rate = Decimal(str(block.dep_rate)) if block.dep_rate is not None else Decimal("15.00")

    add_more = Decimal("0.00")
    add_less = Decimal("0.00")
    sales = Decimal("0.00")
    has_active_assets = False

    if prior_line is not None:
        opening_wdv = prior_line.closing_wdv
    else:
        # First run for this block: rebuild its opening WDV from the assets' cutover
        # figures. Only the TAX figure will do. Book WDV was previously accepted as a
        # substitute, but the two essentially never agree in India — different rates,
        # block-wise rather than asset-wise, additional depreciation — so borrowing it
        # produced a wrong block base and therefore a wrong deduction, silently.
        opening_wdv = Decimal("0.00")
        for a in block_assets:
            if a.disposal_date and a.disposal_date < fy_start:
                continue
            cap_date = a.it_put_to_use_date or a.capitalization_date or a.available_for_use_date
            if cap_date is None:
                # Undatable asset: it cannot be classed as opening or as an addition,
                # so it would vanish from the block entirely.
                raise DepreciationDataError(
                    f"Asset {a.id} ({a.asset_name}) has no put-to-use, capitalization or "
                    f"available-for-use date, so it cannot be placed in an Income Tax block."
                )
            if cap_date < fy_start:
                if a.opening_it_wdv is None:
                    raise DepreciationDataError(
                        f"Asset {a.id} ({a.asset_name}) was in use before {fy_start} but has no "
                        f"opening Income Tax WDV. Set 'Opening WDV (tax)' — the book WDV is not "
                        f"a valid substitute for the tax written-down value."
                    )
                opening_wdv += a.opening_it_wdv

    active_or_current_assets = [
        a for a in block_assets if not (a.disposal_date and a.disposal_date < fy_start)
    ]

    for a in active_or_current_assets:
        cap_date = a.it_put_to_use_date or a.capitalization_date or a.available_for_use_date

        if cap_date and fy_start <= cap_date <= fy_end:
            days_put = (fy_end - cap_date).days + 1
            cost = a.original_cost if a.original_cost is not None else Decimal("0.00")
            if days_put >= 180:
                add_more += cost
            else:
                add_less += cost

        if a.disposal_date and fy_start <= a.disposal_date <= fy_end:
            proceeds = (
                a.disposal_it_proceeds
                if a.disposal_it_proceeds is not None
                else (a.sale_proceeds if a.sale_proceeds is not None else Decimal("0.00"))
            )
            sales += proceeds
        elif not a.disposal_date or a.disposal_date > fy_end:
            has_active_assets = True

    all_disposed = (len(active_or_current_assets) > 0) and (not has_active_assets)

    return ItBlockDepreciationInput(
        block_id=str(block.id),
        block_name=block.name,
        prescribed_rate=rate,
        opening_wdv=opening_wdv,
        additions_more_than_180=add_more,
        additions_less_than_180=add_less,
        realized_from_sales=sales,
        all_assets_disposed=all_disposed,
    )
```

Then in the block loop, delete everything from `rate = Decimal(str(block.dep_rate))...`
down to the closing paren of `it_inp = ItBlockDepreciationInput(...)`, and replace with:

```python
    for block in it_blocks:
        block_assets = assets_by_block.get(block.id, [])
        it_inp = build_it_block_input(
            block, block_assets, prior_block_lines.get(block.id), fy_start, fy_end
        )
```

Also add a helper the endpoint needs, below `build_it_block_input`:

```python
def asset_it_contribution(asset: Asset, fy_start: date, fy_end: date) -> Decimal:
    """How much of a block's pool this one asset accounts for.

    Its cost if it entered the block this year, otherwise its opening tax WDV. Shown
    for context only — the block's depreciation is never apportioned to an asset.
    """
    cap_date = (
        asset.it_put_to_use_date or asset.capitalization_date or asset.available_for_use_date
    )
    if cap_date and fy_start <= cap_date <= fy_end:
        return asset.original_cost if asset.original_cost is not None else Decimal("0.00")
    return asset.opening_it_wdv if asset.opening_it_wdv is not None else Decimal("0.00")
```

- [ ] **Step 3c: Verify the refactor changed nothing**

Run: `pytest tests/test_depreciation_api.py unit_tests/ -q`
Expected: PASS — the extraction is behaviour-preserving; the `explain` tests still fail

- [ ] **Step 3d: Add the schemas**

In `app/schemas/depreciation.py`, append:

```python
class DepreciationExplainRequest(BaseModel):
    asset_id: uuid.UUID
    financial_year_id: uuid.UUID


class DepreciationExplainResponse(BaseModel):
    """Traces computed on demand and never stored.

    `income_tax` is absent when the asset has not been assigned to a block.
    """

    companies_act: CalcTraceSchema
    income_tax: Optional[CalcTraceSchema] = None
```

- [ ] **Step 3e: Add the route**

In `app/routers/depreciation.py`, extend the imports:

```python
from app.models.assets import Asset
from app.models.asset_masters import ItAssetBlock
from app.schemas.depreciation import (
    DepreciationExplainRequest,
    DepreciationExplainResponse,
)
from app.services.calc_trace_builders import (
    build_it_block_trace,
    build_schedule_ii_trace,
)
from app.services.depreciation import calculate_asset_depreciation
from app.services.it_depreciation import calculate_it_block_depreciation
from app.services.depreciation_query import (
    _load_prior_run_lines,
    asset_it_contribution,
    build_asset_depreciation_input,
    build_it_block_input,
)
```

Append the route:

```python
@router.post("/explain", response_model=DepreciationExplainResponse)
async def explain_depreciation(
    body: DepreciationExplainRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Compute one asset's depreciation trace without recording anything.

    Reuses the run's own input assembly and engines, so a projection shows what a run
    would produce rather than a second opinion about it.
    """
    asset = await db.get(Asset, body.asset_id)
    if not asset or asset.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    fy = await db.get(FinancialYear, body.financial_year_id)
    if not fy or fy.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found"
        )

    prior_asset_lines, prior_block_lines = await _load_prior_run_lines(
        db, current_user.company_id, fy.start_date, fy.label
    )

    try:
        inp = build_asset_depreciation_input(asset, prior_asset_lines.get(asset.id))
        calc = calculate_asset_depreciation(inp, fy.start_date, fy.end_date)
    except DepreciationDataError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    companies_act = build_schedule_ii_trace(
        inp, calc, fy_label=fy.label, is_projection=True
    )

    income_tax = None
    if asset.it_block_id:
        block = await db.get(ItAssetBlock, asset.it_block_id)
        if block and block.company_id == current_user.company_id:
            block_assets = list(
                (
                    await db.execute(
                        select(Asset).where(
                            and_(
                                Asset.company_id == current_user.company_id,
                                Asset.it_block_id == block.id,
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
            try:
                it_inp = build_it_block_input(
                    block,
                    block_assets,
                    prior_block_lines.get(block.id),
                    fy.start_date,
                    fy.end_date,
                )
            except DepreciationDataError as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
                )
            it_calc = calculate_it_block_depreciation(it_inp)
            income_tax = build_it_block_trace(
                it_inp,
                it_calc,
                fy_label=fy.label,
                asset_name=asset.asset_name,
                asset_contribution=asset_it_contribution(asset, fy.start_date, fy.end_date),
                is_projection=True,
            )

    return DepreciationExplainResponse(
        companies_act=CalcTraceSchema(**companies_act.to_dict()),
        income_tax=CalcTraceSchema(**income_tax.to_dict()) if income_tax else None,
    )
```

Add `CalcTraceSchema` to the existing `app.schemas.depreciation` import block in the router.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_depreciation_api.py -v`
Expected: PASS — including the 5 `explain` tests

Run: `pytest -q`
Expected: PASS — full backend suite

- [ ] **Step 5: Commit**

```bash
git add app/services/depreciation_query.py app/schemas/depreciation.py app/routers/depreciation.py tests/test_depreciation_api.py
git commit -m "feat(assets): depreciation explain endpoint for projections"
```

---

### Task 9: Trace types and the acquisition-costing adapter

**Files:**
- Create: `frontend/src/components/calc/types.ts`
- Create: `frontend/src/components/calc/traceFromCostPreview.ts`
- Test: `frontend/src/components/calc/traceFromCostPreview.test.ts`

**Interfaces:**
- Produces: `CalcStep`, `CalcTrace`, `TraceTab` types; `MUL`/`DIV`/`SUB`/`ADD` constants; `traceFromCostPreview(input: CostTraceInput, options?: CostTraceOptions): CalcTrace`

The trace types are hand-written rather than taken from `schema.d.ts`. `npm run gen:api`
needs a running backend, and the drawer must not be blocked on that; regenerate the
schema when convenient (`npm run gen:api` with the API up) and the generated
`CalcTraceSchema` will match these by construction.

The operator constants are duplicated from `calc_trace_builders.py` on purpose — a
frontend-derived trace has to read identically to a backend one in the same drawer.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/calc/traceFromCostPreview.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { traceFromCostPreview } from './traceFromCostPreview'
import { ADD, DIV, MUL, SUB } from './types'

const INTRA_STATE = {
  quantity: 1,
  gross_basic_price: '100000.00',
  discount_amount: '5000.00',
  net_basic_price: '95000.00',
  gst_rate: '18.00',
  gst_split_basis: 'intra_state',
  cgst_amount: '8550.00',
  sgst_amount: '8550.00',
  igst_amount: '0.00',
  total_gst: '17100.00',
  recoverable_gst: '17100.00',
  capitalizable_gst: '0.00',
  freight_cost: '2000.00',
  installation_cost: '1500.00',
  other_capitalizable_cost: '0.00',
  landed_cost: '98500.00',
  total_acquisition_outlay: '115600.00',
  per_unit_cost: '98500.00',
  itc_treatment: 'eligible',
}

function step(trace: ReturnType<typeof traceFromCostPreview>, key: string) {
  const found = trace.steps.find((s) => s.key === key)
  if (!found) throw new Error(`no step ${key} in ${trace.steps.map((s) => s.key).join(', ')}`)
  return found
}

describe('traceFromCostPreview', () => {
  it('builds the price group with formula, substitution and result', () => {
    const trace = traceFromCostPreview(INTRA_STATE)

    const net = step(trace, 'net_basic_price')
    expect(net.formula).toBe(`Gross basic price${SUB}Discount`)
    expect(net.substitution).toBe(`100,000.00${SUB}5,000.00`)
    expect(net.result).toBe('95,000.00')
    expect(net.unit).toBe('money')
  })

  it('splits GST into CGST and SGST for an intra-state supply', () => {
    const trace = traceFromCostPreview(INTRA_STATE, { gstBasisLabel: 'Intra-state — CGST + SGST' })

    expect(step(trace, 'gst_split_basis').result).toBe('Intra-state — CGST + SGST')
    expect(step(trace, 'cgst_amount').substitution).toBe(`95,000.00${MUL}9.00%`)
    expect(step(trace, 'sgst_amount').result).toBe('8,550.00')
    expect(trace.steps.find((s) => s.key === 'igst_amount')).toBeUndefined()

    const total = step(trace, 'total_gst')
    expect(total.result).toBe('17,100.00')
    expect(total.emphasis).toBe(true)
  })

  it('shows recoverable GST as excluded from cost', () => {
    const trace = traceFromCostPreview(INTRA_STATE)
    const recoverable = step(trace, 'recoverable_gst')
    expect(recoverable.result).toBe('17,100.00')
    expect(recoverable.note ?? '').toMatch(/not part of the asset/i)
  })

  it('explains blocked ITC as capitalized into cost', () => {
    const trace = traceFromCostPreview({
      ...INTRA_STATE,
      itc_treatment: 'blocked',
      recoverable_gst: '0.00',
      capitalizable_gst: '17100.00',
      landed_cost: '115600.00',
    })
    const capitalizable = step(trace, 'capitalizable_gst')
    expect(capitalizable.result).toBe('17,100.00')
    expect(capitalizable.note ?? '').toMatch(/17\(5\)/)
  })

  it('shows IGST alone for an inter-state supply', () => {
    const trace = traceFromCostPreview({
      ...INTRA_STATE,
      gst_split_basis: 'inter_state',
      cgst_amount: '0.00',
      sgst_amount: '0.00',
      igst_amount: '17100.00',
    })
    expect(step(trace, 'igst_amount').result).toBe('17,100.00')
    expect(trace.steps.find((s) => s.key === 'cgst_amount')).toBeUndefined()
  })

  it('flags a manual split as reconciled to the invoice, without a rate formula', () => {
    const trace = traceFromCostPreview({ ...INTRA_STATE, gst_split_basis: 'manual' })
    expect(step(trace, 'cgst_amount').formula).toBe('')
    expect(step(trace, 'gst_split_basis').note ?? '').toMatch(/invoice/i)
  })

  it('builds the capitalized cost total from its components', () => {
    const trace = traceFromCostPreview(INTRA_STATE)
    const landed = step(trace, 'landed_cost')
    expect(landed.formula).toBe(
      `Net basic price${ADD}Capitalizable GST${ADD}Freight${ADD}Installation${ADD}Other capitalizable`,
    )
    expect(landed.substitution).toBe(
      `95,000.00${ADD}0.00${ADD}2,000.00${ADD}1,500.00${ADD}0.00`,
    )
    expect(landed.result).toBe('98,500.00')
    expect(landed.emphasis).toBe(true)
  })

  it('omits zero cost components so the total stays readable', () => {
    const trace = traceFromCostPreview({
      ...INTRA_STATE,
      freight_cost: '0.00',
      installation_cost: '0.00',
    })
    expect(trace.steps.find((s) => s.key === 'freight_cost')).toBeUndefined()
    expect(trace.steps.find((s) => s.key === 'installation_cost')).toBeUndefined()
  })

  it('shows per-unit allocation only when there is more than one unit', () => {
    const single = traceFromCostPreview(INTRA_STATE)
    expect(single.steps.find((s) => s.key === 'per_unit_cost')).toBeUndefined()

    const many = traceFromCostPreview({
      ...INTRA_STATE,
      quantity: 3,
      per_unit_cost: '32833.34',
    })
    const perUnit = step(many, 'per_unit_cost')
    expect(perUnit.formula).toBe(`Total capitalized value${DIV}Quantity`)
    expect(perUnit.substitution).toBe(`98,500.00${DIV}3`)
    expect(perUnit.note ?? '').toMatch(/sum/i)
  })

  it('distinguishes outlay from the depreciation base', () => {
    const trace = traceFromCostPreview(INTRA_STATE)
    const outlay = step(trace, 'total_acquisition_outlay')
    expect(outlay.result).toBe('115,600.00')
    expect(outlay.note ?? '').toMatch(/not the depreciation base/i)
  })

  it('groups steps in contiguous runs and is never a projection', () => {
    const trace = traceFromCostPreview(INTRA_STATE)
    const seen: string[] = []
    for (const s of trace.steps) {
      if (seen[seen.length - 1] !== s.group) {
        expect(seen).not.toContain(s.group)
        seen.push(s.group)
      }
    }
    expect(seen).toEqual(['Price', 'GST', 'Capitalized cost'])
    expect(trace.is_projection).toBe(false)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- traceFromCostPreview`
Expected: FAIL — cannot resolve `./traceFromCostPreview`

- [ ] **Step 3a: Write the types**

Create `frontend/src/components/calc/types.ts`:

```ts
/**
 * The shape of a calculation trace. Mirrors `CalcTraceSchema` on the backend, and is
 * hand-written so the drawer does not depend on regenerating `schema.d.ts`.
 */

export type CalcUnit = 'money' | 'percent' | 'days' | 'months' | 'count' | 'none'

export interface CalcStep {
  key: string
  group: string
  label: string
  /** Empty for a plain input rather than a derivation — the renderer omits the line. */
  formula: string
  substitution: string
  /** Already formatted. The renderer adds the unit's symbol and never rounds. */
  result: string
  unit: CalcUnit
  /** The figure the page displays. Anchors the trace to the row it was opened from. */
  emphasis: boolean
  note?: string | null
}

export interface CalcTrace {
  title: string
  basis: string
  steps: CalcStep[]
  is_projection: boolean
  computed_at?: string | null
}

/** One book in the drawer. Two tabs means Companies Act and Income Tax side by side. */
export interface TraceTab {
  id: string
  label: string
  trace: CalcTrace
}

/**
 * Operators, duplicated from `app/services/calc_trace_builders.py`. A trace built here
 * sits in the same drawer as one built there, so they have to read identically.
 */
export const MUL = ' × '
export const DIV = ' ÷ '
export const SUB = ' − '
export const ADD = ' + '
```

- [ ] **Step 3b: Write the adapter**

Create `frontend/src/components/calc/traceFromCostPreview.ts`:

```ts
import { formatMoney } from '@/lib/format'
import { ADD, DIV, MUL, SUB, type CalcStep, type CalcTrace } from './types'

/**
 * Turns an acquisition's cost figures into a calculation trace.
 *
 * There is no backend trace for costing: `CostPreviewResponse` and the saved
 * acquisition already carry every intermediate, and there is no historical version to
 * reconcile. This is presentation over data the caller already holds.
 */

/** Every field this needs. `CostPreviewResponse` and `AcquisitionResponse` both satisfy it. */
export interface CostTraceInput {
  quantity?: number | null
  gross_basic_price?: string | number | null
  discount_amount?: string | number | null
  net_basic_price?: string | number | null
  gst_rate?: string | number | null
  gst_split_basis?: string | null
  cgst_amount?: string | number | null
  sgst_amount?: string | number | null
  igst_amount?: string | number | null
  total_gst?: string | number | null
  recoverable_gst?: string | number | null
  capitalizable_gst?: string | number | null
  freight_cost?: string | number | null
  installation_cost?: string | number | null
  other_capitalizable_cost?: string | number | null
  landed_cost?: string | number | null
  total_acquisition_outlay?: string | number | null
  per_unit_cost?: string | number | null
  itc_treatment?: string | null
}

export interface CostTraceOptions {
  title?: string
  /** Passed in rather than looked up, to keep this component free of page imports. */
  gstBasisLabel?: string
}

const GROUP_PRICE = 'Price'
const GROUP_GST = 'GST'
const GROUP_COST = 'Capitalized cost'

/** Decimals arrive as strings from Pydantic; 0 is the right reading of an absent cost. */
function n(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0
  const parsed = typeof value === 'string' ? Number(value) : value
  return Number.isNaN(parsed) ? 0 : parsed
}

const m = (value: string | number | null | undefined) => formatMoney(n(value))
const p = (value: string | number | null | undefined) => n(value).toFixed(2)

export function traceFromCostPreview(
  input: CostTraceInput,
  options: CostTraceOptions = {},
): CalcTrace {
  const steps: CalcStep[] = []

  const add = (
    step: Pick<CalcStep, 'key' | 'group' | 'label' | 'result'> & Partial<CalcStep>,
  ) => {
    steps.push({
      formula: '',
      substitution: '',
      unit: 'money',
      emphasis: false,
      note: null,
      ...step,
    })
  }

  const quantity = input.quantity ?? 1
  const basis = input.gst_split_basis ?? null
  const isManual = basis === 'manual'
  const isInterState = n(input.igst_amount) > 0

  // --- Price ---------------------------------------------------------------
  add({ key: 'gross_basic_price', group: GROUP_PRICE, label: 'Gross basic price', result: m(input.gross_basic_price) })
  add({ key: 'discount_amount', group: GROUP_PRICE, label: 'Less discount', result: m(input.discount_amount) })
  add({
    key: 'net_basic_price',
    group: GROUP_PRICE,
    label: 'Net basic price',
    formula: `Gross basic price${SUB}Discount`,
    substitution: `${m(input.gross_basic_price)}${SUB}${m(input.discount_amount)}`,
    result: m(input.net_basic_price),
  })

  // --- GST -----------------------------------------------------------------
  add({ key: 'gst_rate', group: GROUP_GST, label: 'GST rate', result: p(input.gst_rate), unit: 'percent' })
  add({
    key: 'gst_split_basis',
    group: GROUP_GST,
    label: 'Split basis',
    result: options.gstBasisLabel ?? basis ?? '—',
    unit: 'none',
    note: isManual
      ? 'These amounts were entered by hand to reconcile with the invoice, so no rate is applied.'
      : null,
  })

  // Half the rate each for an intra-state supply; the whole rate as IGST otherwise.
  const halfRate = p(n(input.gst_rate) / 2)
  if (isInterState) {
    add({
      key: 'igst_amount',
      group: GROUP_GST,
      label: 'IGST',
      formula: isManual ? '' : `Net basic price${MUL}GST rate`,
      substitution: isManual ? '' : `${m(input.net_basic_price)}${MUL}${p(input.gst_rate)}%`,
      result: m(input.igst_amount),
    })
  } else {
    add({
      key: 'cgst_amount',
      group: GROUP_GST,
      label: 'CGST',
      formula: isManual ? '' : `Net basic price${MUL}Half the GST rate`,
      substitution: isManual ? '' : `${m(input.net_basic_price)}${MUL}${halfRate}%`,
      result: m(input.cgst_amount),
    })
    add({
      key: 'sgst_amount',
      group: GROUP_GST,
      label: 'SGST',
      formula: isManual ? '' : `Net basic price${MUL}Half the GST rate`,
      substitution: isManual ? '' : `${m(input.net_basic_price)}${MUL}${halfRate}%`,
      result: m(input.sgst_amount),
    })
  }

  add({
    key: 'total_gst',
    group: GROUP_GST,
    label: 'Total GST',
    formula: isInterState ? 'IGST' : `CGST${ADD}SGST`,
    substitution: isInterState
      ? m(input.igst_amount)
      : `${m(input.cgst_amount)}${ADD}${m(input.sgst_amount)}`,
    result: m(input.total_gst),
    emphasis: true,
  })
  add({
    key: 'recoverable_gst',
    group: GROUP_GST,
    label: 'Recoverable GST (input tax credit)',
    result: m(input.recoverable_gst),
    note: 'Recoverable tax is not part of the asset’s cost, so it does not depreciate.',
  })
  add({
    key: 'capitalizable_gst',
    group: GROUP_GST,
    label: 'Capitalizable GST',
    formula: `Total GST${SUB}Recoverable GST`,
    substitution: `${m(input.total_gst)}${SUB}${m(input.recoverable_gst)}`,
    result: m(input.capitalizable_gst),
    note:
      input.itc_treatment === 'blocked'
        ? 'Credit is blocked for this class of asset (CGST Act s.17(5)), so the tax is capitalized into cost and depreciates.'
        : 'Tax for which no credit is available becomes part of cost and depreciates.',
  })

  // --- Capitalized cost ----------------------------------------------------
  // Zero components are omitted: an unspent line adds nothing but length.
  if (n(input.freight_cost) !== 0) {
    add({ key: 'freight_cost', group: GROUP_COST, label: 'Add freight', result: m(input.freight_cost) })
  }
  if (n(input.installation_cost) !== 0) {
    add({ key: 'installation_cost', group: GROUP_COST, label: 'Add installation', result: m(input.installation_cost) })
  }
  if (n(input.other_capitalizable_cost) !== 0) {
    add({
      key: 'other_capitalizable_cost',
      group: GROUP_COST,
      label: 'Add other capitalizable cost',
      result: m(input.other_capitalizable_cost),
    })
  }
  add({
    key: 'landed_cost',
    group: GROUP_COST,
    label: 'Total capitalized value',
    formula: `Net basic price${ADD}Capitalizable GST${ADD}Freight${ADD}Installation${ADD}Other capitalizable`,
    substitution: [
      m(input.net_basic_price),
      m(input.capitalizable_gst),
      m(input.freight_cost),
      m(input.installation_cost),
      m(input.other_capitalizable_cost),
    ].join(ADD),
    result: m(input.landed_cost),
    emphasis: true,
  })
  if (quantity > 1) {
    add({
      key: 'per_unit_cost',
      group: GROUP_COST,
      label: 'Per-unit cost',
      formula: `Total capitalized value${DIV}Quantity`,
      substitution: `${m(input.landed_cost)}${DIV}${quantity}`,
      result: m(input.per_unit_cost),
      note: 'Rounded so the units sum to exactly the total, to the paisa.',
    })
  }
  add({
    key: 'total_acquisition_outlay',
    group: GROUP_COST,
    label: 'Total acquisition outlay',
    formula: `Total capitalized value${ADD}Recoverable GST`,
    substitution: `${m(input.landed_cost)}${ADD}${m(input.recoverable_gst)}`,
    result: m(input.total_acquisition_outlay),
    note: 'Total cash paid, including recoverable tax — not the depreciation base.',
  })

  return {
    title: options.title ?? 'Acquisition cost build-up',
    basis: `Quantity ${quantity}; GST at ${p(input.gst_rate)}%`,
    steps,
    is_projection: false,
    computed_at: null,
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- traceFromCostPreview`
Expected: PASS — 11 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/calc/types.ts frontend/src/components/calc/traceFromCostPreview.ts frontend/src/components/calc/traceFromCostPreview.test.ts
git commit -m "feat(assets): trace types and acquisition cost adapter"
```

---

### Task 10: The drawer

**Files:**
- Create: `frontend/src/components/calc/CalcStepRow.tsx`
- Create: `frontend/src/components/calc/traceToText.ts`
- Create: `frontend/src/components/calc/CalculationDrawer.tsx`
- Create: `frontend/src/components/calc/index.ts`
- Test: `frontend/src/components/calc/calc.test.tsx`

**Interfaces:**
- Consumes: `Drawer`, `Tabs`, `Button`, `Spinner` from `@/components/ui`; `CalcStep`, `CalcTrace`, `TraceTab` from Task 9.
- Produces:
  - `CalcStepRow({ step, focused }: { step: CalcStep; focused?: boolean })`
  - `traceToText(trace: CalcTrace): string`
  - `CalculationDrawer({ open, onClose, tabs, focusStep, loading, error, emptyNote, onShowProjection })`
  - barrel re-exporting `CalculationDrawer`, `CalcStepRow`, `ExplainLink` (added in Task 11), `traceFromCostPreview`, `traceToText`, and the types

`CalculationDrawer` props in full:

```ts
interface CalculationDrawerProps {
  open: boolean
  onClose: () => void
  tabs: TraceTab[]
  /** Step key to scroll to and highlight. Selects the tab containing it. */
  focusStep?: string
  loading?: boolean
  /** Message from a 422 — an explanation of what is missing, not a crash. */
  error?: string | null
  /** Shown when there are no tabs, e.g. a run recorded before traces existed. */
  emptyNote?: string
  /** When given, the empty state offers a projection instead. */
  onShowProjection?: () => void
  /** Provenance line, e.g. "Draft run" — so a draft is never read as the filed figure. */
  contextNote?: string
}
```

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/calc/calc.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CalculationDrawer } from './CalculationDrawer'
import { traceToText } from './traceToText'
import type { CalcTrace } from './types'

const CA: CalcTrace = {
  title: 'Depreciation — Companies Act Schedule II — FY 2024-25',
  basis: 'SLM — straight line; useful life 60 months; residual 5.00%; original cost 100,000.00',
  is_projection: false,
  computed_at: '2025-04-01T10:00:00Z',
  steps: [
    { key: 'original_cost', group: 'Inputs', label: 'Original cost', formula: '', substitution: '', result: '100,000.00', unit: 'money', emphasis: false },
    { key: 'depreciable_base', group: 'Rate', label: 'Depreciable base', formula: 'Original cost − Residual value', substitution: '100,000.00 − 5,000.00', result: '95,000.00', unit: 'money', emphasis: false },
    { key: 'depreciation_for_year', group: 'Charge for the year', label: 'Depreciation for the year', formula: 'Lower of the charge and the remaining depreciable base', substitution: 'lower of 19,000.00 and 95,000.00', result: '19,000.00', unit: 'money', emphasis: true, note: null },
    { key: 'effective_rate_pct', group: 'Roll-forward', label: 'Effective rate on cost', formula: 'Depreciation for the year ÷ Original cost', substitution: '19,000.00 ÷ 100,000.00', result: '19.00', unit: 'percent', emphasis: false },
  ],
}

const IT: CalcTrace = {
  title: 'Depreciation — Income Tax Act, block — FY 2024-25',
  basis: 'Block Plant & Machinery (General); prescribed rate 15.00%',
  is_projection: false,
  computed_at: '2025-04-01T10:00:00Z',
  steps: [
    { key: 'total_depreciation', group: 'Rate application', label: 'Total depreciation for the block', formula: 'Full-rate depreciation + Half-rate depreciation', substitution: '90,000.00 + 3,000.00', result: '93,000.00', unit: 'money', emphasis: true },
  ],
}

const TABS = [
  { id: 'ca', label: 'Companies Act', trace: CA },
  { id: 'it', label: 'Income Tax', trace: IT },
]

describe('CalculationDrawer', () => {
  it('renders each step as label, formula, substitution and result', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)

    expect(screen.getByText('Depreciable base')).toBeTruthy()
    expect(screen.getByText('Original cost − Residual value')).toBeTruthy()
    expect(screen.getByText('100,000.00 − 5,000.00')).toBeTruthy()
    expect(screen.getByText('₹95,000.00')).toBeTruthy()
  })

  it('adds the unit symbol without touching the digits', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.getByText('19.00%')).toBeTruthy()
  })

  it('renders a heading per group', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.getByText('Inputs')).toBeTruthy()
    expect(screen.getByText('Rate')).toBeTruthy()
    expect(screen.getByText('Charge for the year')).toBeTruthy()
  })

  it('shows the basis so the inputs a trace used are visible', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.getByText(/useful life 60 months/)).toBeTruthy()
  })

  it('shows tabs only when there are two books', () => {
    const { unmount } = render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.queryByText('Income Tax')).toBeNull()
    unmount()

    render(<CalculationDrawer open onClose={vi.fn()} tabs={TABS} />)
    expect(screen.getByText('Income Tax')).toBeTruthy()
  })

  it('opens on the tab that contains the focused step', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={TABS} focusStep="total_depreciation" />)
    // The Income Tax tab's content is showing, not the Companies Act one.
    expect(screen.getByText('Total depreciation for the block')).toBeTruthy()
    expect(screen.queryByText('Depreciable base')).toBeNull()
  })

  it('marks the focused step so the eye lands on it', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} focusStep="depreciable_base" />)
    const row = document.getElementById('calc-step-depreciable_base')
    expect(row).toBeTruthy()
    expect(row?.getAttribute('data-focused')).toBe('true')
  })

  it('labels a projection unmistakably', () => {
    render(
      <CalculationDrawer
        open
        onClose={vi.fn()}
        tabs={[{ ...TABS[0], trace: { ...CA, is_projection: true, computed_at: null } }]}
      />,
    )
    expect(screen.getByText(/not the recorded figure/i)).toBeTruthy()
    expect(screen.getByText(/Recompute the run to record this/i)).toBeTruthy()
  })

  it('shows when a recorded run was computed', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} />)
    expect(screen.queryByText(/not the recorded figure/i)).toBeNull()
    expect(screen.getByText(/Computed/)).toBeTruthy()
  })

  it('states the run status, so a draft is not read as the filed figure', () => {
    render(<CalculationDrawer open onClose={vi.fn()} tabs={[TABS[0]]} contextNote="Draft run" />)
    expect(screen.getByText(/Draft run/)).toBeTruthy()
  })

  it('renders a 422 message as an explanation', () => {
    render(
      <CalculationDrawer
        open
        onClose={vi.fn()}
        tabs={[]}
        error="Asset X is marked pre-cutover but carries neither an opening WDV nor opening accumulated depreciation."
      />,
    )
    expect(screen.getByText(/pre-cutover/)).toBeTruthy()
  })

  it('offers a projection when a run predates traces', () => {
    const onShowProjection = vi.fn()
    render(
      <CalculationDrawer
        open
        onClose={vi.fn()}
        tabs={[]}
        emptyNote="This run was recorded before calculation traces were kept."
        onShowProjection={onShowProjection}
      />,
    )
    expect(screen.getByText(/before calculation traces were kept/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /projection/i }))
    expect(onShowProjection).toHaveBeenCalled()
  })

  it('renders nothing when closed', () => {
    render(<CalculationDrawer open={false} onClose={vi.fn()} tabs={TABS} />)
    expect(screen.queryByText('Depreciable base')).toBeNull()
  })
})

describe('traceToText', () => {
  it('renders a pasteable plain-text version', () => {
    const text = traceToText(CA)
    expect(text).toContain('Depreciation — Companies Act Schedule II — FY 2024-25')
    expect(text).toContain('SLM — straight line')
    expect(text).toContain('Rate')
    expect(text).toContain('Depreciable base')
    expect(text).toContain('Original cost − Residual value')
    expect(text).toContain('100,000.00 − 5,000.00')
    expect(text).toContain('95,000.00')
  })

  it('marks a projection in the text too, so a paste cannot mislead', () => {
    const text = traceToText({ ...CA, is_projection: true, computed_at: null })
    expect(text).toMatch(/projection/i)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- calc.test`
Expected: FAIL — cannot resolve `./CalculationDrawer`

- [ ] **Step 3a: Write the step row**

Create `frontend/src/components/calc/CalcStepRow.tsx`:

```tsx
import { cn } from '@/lib/cn'
import type { CalcStep } from './types'

const PREFIX: Partial<Record<CalcStep['unit'], string>> = { money: '₹' }
const SUFFIX: Partial<Record<CalcStep['unit'], string>> = {
  percent: '%',
  days: ' days',
  months: ' mo',
}

/**
 * One line of a calculation.
 *
 * The result arrives already formatted; this only adds the unit's symbol. Nothing here
 * may reformat a number — that is how a drawer ends up disagreeing with the row that
 * opened it.
 */
export function CalcStepRow({ step, focused }: { step: CalcStep; focused?: boolean }) {
  return (
    <div
      id={`calc-step-${step.key}`}
      data-focused={focused ? 'true' : undefined}
      className={cn(
        'rounded-md border px-3 py-2 transition-colors',
        step.emphasis
          ? 'border-border-strong bg-bg-raised'
          : 'border-transparent bg-bg-inset/40',
        focused && 'ring-1 ring-accent',
      )}
    >
      <div className="flex items-baseline justify-between gap-4">
        <span
          className={cn(
            'text-sm',
            step.emphasis ? 'font-semibold text-text-primary' : 'text-text-secondary',
          )}
        >
          {step.label}
        </span>
        <span
          className={cn(
            'tabular-nums whitespace-nowrap',
            step.emphasis ? 'text-md font-semibold text-text-primary' : 'text-sm text-text-primary',
          )}
        >
          {PREFIX[step.unit] ?? ''}
          {step.result}
          {SUFFIX[step.unit] ?? ''}
        </span>
      </div>
      {/* An input step has no formula. Rendering blank lines for it would imply the
          value was derived from something. */}
      {step.formula && <p className="mt-0.5 text-xs text-text-muted">{step.formula}</p>}
      {step.substitution && (
        <p className="text-xs tabular-nums text-text-secondary">{step.substitution}</p>
      )}
      {step.note && <p className="mt-1 text-xs italic text-text-muted">{step.note}</p>}
    </div>
  )
}
```

- [ ] **Step 3b: Write the text renderer**

Create `frontend/src/components/calc/traceToText.ts`:

```ts
import type { CalcTrace } from './types'

const PREFIX: Record<string, string> = { money: '₹' }
const SUFFIX: Record<string, string> = { percent: '%', days: ' days', months: ' mo' }

/**
 * A pasteable rendering of a trace.
 *
 * The audience for this feature is people answering an auditor's query, so the trace
 * has to leave the app as text rather than a screenshot.
 */
export function traceToText(trace: CalcTrace): string {
  const lines: string[] = [trace.title, trace.basis]
  lines.push(
    trace.is_projection
      ? 'PROJECTION from current inputs — not the recorded figure.'
      : `Computed ${trace.computed_at ?? 'unknown'}`,
  )

  let group = ''
  for (const step of trace.steps) {
    if (step.group !== group) {
      group = step.group
      lines.push('', group)
    }
    const value = `${PREFIX[step.unit] ?? ''}${step.result}${SUFFIX[step.unit] ?? ''}`
    lines.push(`  ${step.label}: ${value}`)
    if (step.formula) lines.push(`    ${step.formula}`)
    if (step.substitution) lines.push(`    = ${step.substitution}`)
    if (step.note) lines.push(`    (${step.note})`)
  }

  return lines.join('\n')
}
```

- [ ] **Step 3c: Write the drawer**

Create `frontend/src/components/calc/CalculationDrawer.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react'
import { Button, Drawer, Spinner, Tabs } from '@/components/ui'
import { CalcStepRow } from './CalcStepRow'
import { traceToText } from './traceToText'
import type { CalcStep, TraceTab } from './types'

export interface CalculationDrawerProps {
  open: boolean
  onClose: () => void
  tabs: TraceTab[]
  /** Step key to scroll to and highlight. Also selects the tab containing it. */
  focusStep?: string
  loading?: boolean
  /** A 422's message — what is missing, rather than a failure. */
  error?: string | null
  /** Shown when there are no traces, e.g. a run recorded before traces existed. */
  emptyNote?: string
  /** When given, the empty state offers a projection instead. */
  onShowProjection?: () => void
  /** Provenance line, e.g. "Draft run" — so a draft is never read as the filed figure. */
  contextNote?: string
}

function groupSteps(steps: CalcStep[]): { group: string; steps: CalcStep[] }[] {
  const groups: { group: string; steps: CalcStep[] }[] = []
  for (const step of steps) {
    const last = groups[groups.length - 1]
    if (last && last.group === step.group) last.steps.push(step)
    else groups.push({ group: step.group, steps: [step] })
  }
  return groups
}

/**
 * Renders a calculation trace. Knows nothing about assets, depreciation or costing —
 * anything that can produce a trace can use it.
 */
export function CalculationDrawer({
  open,
  onClose,
  tabs,
  focusStep,
  loading,
  error,
  emptyNote,
  onShowProjection,
  contextNote,
}: CalculationDrawerProps) {
  // The tab holding the focused step is the one worth opening on.
  const preferred = useMemo(() => {
    if (focusStep) {
      const holder = tabs.find((t) => t.trace.steps.some((s) => s.key === focusStep))
      if (holder) return holder.id
    }
    return tabs[0]?.id ?? ''
  }, [tabs, focusStep])

  const [active, setActive] = useState(preferred)
  useEffect(() => setActive(preferred), [preferred])

  const current = tabs.find((t) => t.id === active) ?? tabs[0]
  const trace = current?.trace

  useEffect(() => {
    if (!open || !focusStep || !trace) return
    // The drawer animates in, so the node is not scrollable on the same frame.
    const id = window.setTimeout(() => {
      document
        .getElementById(`calc-step-${focusStep}`)
        ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 120)
    return () => window.clearTimeout(id)
  }, [open, focusStep, trace])

  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    if (!trace) return
    await navigator.clipboard.writeText(traceToText(trace))
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="How this was calculated"
      subtitle={trace?.title}
      width="lg"
      footer={
        <div className="flex items-center justify-end gap-2">
          {trace && (
            <Button variant="ghost" size="sm" onClick={handleCopy}>
              {copied ? 'Copied' : 'Copy calculation'}
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      {tabs.length > 1 && (
        <Tabs
          className="mb-3"
          layoutGroup="calc-drawer"
          tabs={tabs.map((t) => ({ id: t.id, label: t.label }))}
          value={active}
          onChange={setActive}
        />
      )}

      {loading && <Spinner className="mx-auto my-8 h-5 w-5" />}

      {!loading && error && (
        <div className="rounded-card border border-border-strong bg-bg-inset p-3">
          <p className="text-sm font-medium text-text-primary">
            This figure cannot be computed yet
          </p>
          <p className="mt-1 text-sm text-text-secondary">{error}</p>
        </div>
      )}

      {!loading && !error && !trace && (
        <div className="rounded-card border border-border bg-bg-inset p-3">
          <p className="text-sm text-text-secondary">
            {emptyNote ?? 'There is no calculation to show yet.'}
          </p>
          {onShowProjection && (
            <Button className="mt-3" variant="secondary" size="sm" onClick={onShowProjection}>
              Show a projection from current inputs
            </Button>
          )}
        </div>
      )}

      {!loading && !error && trace && (
        <div className="flex flex-col gap-3">
          {/* A projection has to be impossible to mistake for the recorded figure. */}
          {trace.is_projection ? (
            <div className="rounded-card border border-dashed border-status-pending bg-status-pending/5 px-3 py-2">
              <p className="text-xs font-medium text-status-pending">
                Projection from the asset’s current inputs — not the recorded figure.
              </p>
              <p className="mt-0.5 text-xs text-text-muted">
                Recompute the run to record this.
              </p>
            </div>
          ) : (
            <p className="text-xs text-text-muted">
              Computed {trace.computed_at ?? 'at an unrecorded time'}
              {contextNote ? ` · ${contextNote}` : ''}
            </p>
          )}

          <p className="text-xs text-text-secondary">{trace.basis}</p>

          {groupSteps(trace.steps).map(({ group, steps }) => (
            <section key={group} className="flex flex-col gap-1.5">
              <h4 className="mt-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
                {group}
              </h4>
              {steps.map((step) => (
                <CalcStepRow key={step.key} step={step} focused={step.key === focusStep} />
              ))}
            </section>
          ))}
        </div>
      )}
    </Drawer>
  )
}
```

- [ ] **Step 3d: Add the barrel**

Create `frontend/src/components/calc/index.ts`:

```ts
export { CalcStepRow } from './CalcStepRow'
export { CalculationDrawer } from './CalculationDrawer'
export type { CalculationDrawerProps } from './CalculationDrawer'
export { traceToText } from './traceToText'
export { traceFromCostPreview } from './traceFromCostPreview'
export type { CostTraceInput, CostTraceOptions } from './traceFromCostPreview'
export type { CalcStep, CalcTrace, CalcUnit, TraceTab } from './types'
export { ADD, DIV, MUL, SUB } from './types'
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run test -- calc.test`
Expected: PASS — 15 passed

If `status-pending` is not a Tailwind token in this project, check
`frontend/tailwind.config.js` and substitute the warning/attention token it does define;
the banner must be visually distinct from ordinary content, not merely worded
differently.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/calc/
git commit -m "feat(assets): calculation trace drawer"
```

---

### Task 11: The trigger, and a deep link from derived rows

**Files:**
- Create: `frontend/src/components/calc/ExplainLink.tsx`
- Modify: `frontend/src/components/calc/index.ts`
- Modify: `frontend/src/pages/company/assets/tabs/SectionShell.tsx` — `DerivedRow`
- Test: `frontend/src/components/calc/explainLink.test.tsx`

**Interfaces:**
- Produces: `ExplainLink({ onClick, label?, className? })`; `DerivedRow` gains `onExplain?: () => void`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/calc/explainLink.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ExplainLink } from './ExplainLink'
import { DerivedRow } from '@/pages/company/assets/tabs/SectionShell'

describe('ExplainLink', () => {
  it('reads as an invitation to see the working', () => {
    const onClick = vi.fn()
    render(<ExplainLink onClick={onClick} />)
    const button = screen.getByRole('button', { name: /see the calculation/i })
    fireEvent.click(button)
    expect(onClick).toHaveBeenCalled()
  })

  it('accepts a shorter label for tight spots', () => {
    render(<ExplainLink onClick={vi.fn()} label="See working" />)
    expect(screen.getByRole('button', { name: /see working/i })).toBeTruthy()
  })
})

describe('DerivedRow', () => {
  it('offers no explain affordance by default', () => {
    render(<DerivedRow label="Depreciable base" value="₹95,000.00" />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('deep-links into the calculation when given a handler', () => {
    const onExplain = vi.fn()
    render(<DerivedRow label="Depreciable base" value="₹95,000.00" onExplain={onExplain} />)
    fireEvent.click(screen.getByRole('button', { name: /how .*depreciable base.* calculated/i }))
    expect(onExplain).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- explainLink`
Expected: FAIL — cannot resolve `./ExplainLink`

- [ ] **Step 3a: Write ExplainLink**

Create `frontend/src/components/calc/ExplainLink.tsx`:

```tsx
import { Calculator } from 'lucide-react'
import { cn } from '@/lib/cn'

/**
 * Opens a calculation trace. Sized to sit in a Card header or beside a derived value
 * without competing with the figure it explains.
 */
export function ExplainLink({
  onClick,
  label = 'See the calculation',
  className,
}: {
  onClick: () => void
  label?: string
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1 rounded-btn px-1.5 py-1 text-xs font-medium text-accent',
        'hover:bg-bg-raised focus:outline-none focus:ring-1 focus:ring-accent',
        className,
      )}
    >
      <Calculator className="h-3.5 w-3.5" />
      {label}
    </button>
  )
}
```

Add to `frontend/src/components/calc/index.ts`:

```ts
export { ExplainLink } from './ExplainLink'
```

- [ ] **Step 3b: Give DerivedRow the deep link**

In `frontend/src/pages/company/assets/tabs/SectionShell.tsx`, add the icon import at the top:

```tsx
import { Calculator } from 'lucide-react'
```

Replace `DerivedRow` with:

```tsx
/** Read-only label/value row, for figures the system derives. */
export function DerivedRow({
  label,
  value,
  hint,
  emphasis,
  onExplain,
}: {
  label: string
  value: ReactNode
  hint?: string
  emphasis?: boolean
  /** Opens this figure's step in the calculation drawer. */
  onExplain?: () => void
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <div>
        <span className={cn('text-sm', emphasis ? 'font-medium text-text-primary' : 'text-text-secondary')}>
          {label}
        </span>
        {hint && <p className="text-xs text-text-muted">{hint}</p>}
      </div>
      <span className="flex items-baseline gap-1.5">
        <span
          className={cn(
            'tabular-nums',
            emphasis ? 'text-md font-semibold text-text-primary' : 'text-sm text-text-primary',
          )}
        >
          {value}
        </span>
        {/* A bare icon rather than a labelled link: these rows come in runs of six or
            more, and a link on each would crowd out the figures. */}
        {onExplain && (
          <button
            type="button"
            onClick={onExplain}
            aria-label={`How was ${label} calculated?`}
            className="rounded-btn p-0.5 text-text-muted hover:bg-bg-raised hover:text-accent focus:outline-none focus:ring-1 focus:ring-accent"
          >
            <Calculator className="h-3.5 w-3.5" />
          </button>
        )}
      </span>
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run test -- explainLink`
Expected: PASS — 4 passed

Run: `cd frontend && npm run test`
Expected: PASS — no existing asset test broken by the `DerivedRow` change

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/calc/ExplainLink.tsx frontend/src/components/calc/index.ts frontend/src/components/calc/explainLink.test.tsx frontend/src/pages/company/assets/tabs/SectionShell.tsx
git commit -m "feat(assets): explain trigger and derived-row deep link"
```

---

### Task 12: Extract the depreciation run card

**Files:**
- Create: `frontend/src/pages/company/assets/tabs/DepreciationRunCard.tsx`
- Modify: `frontend/src/pages/company/assets/tabs/DepreciationTab.tsx`
- Test: `frontend/src/pages/company/assets/tabs/reopen.test.tsx` (must keep passing unchanged)

**Interfaces:**
- Produces: `DepreciationRunCard({ assetId }: { assetId: string })` — Task 14 adds the `itBlockId` prop when the drawer needs it

A behaviour-preserving refactor with no new features. `DepreciationTab.tsx` is 532 lines
and holds four fieldsets plus the whole run/compute/finalize/reopen surface; two of the
new triggers land in that surface, and it is self-contained. Doing the move on its own
means the next task's diff is about the feature rather than about relocation.

- [ ] **Step 1: Establish the baseline**

Run: `cd frontend && npm run test -- reopen`
Expected: PASS — record that it passes before the move, since it is the regression net

- [ ] **Step 2: Create the card**

Create `frontend/src/pages/company/assets/tabs/DepreciationRunCard.tsx`:

```tsx
import { useState } from 'react'
import { Button, Card, Field, Modal, Spinner, Textarea, useToast } from '@/components/ui'
import { useFinancialYears } from '@/api/hooks/financialYears'
import {
  useAssetDepreciationLines,
  useCreateDepreciationRun,
  useDepreciationRuns,
  useFinalizeDepreciationRun,
  useReopenDepreciationRun,
} from '@/api/hooks/depreciation'
import { useCompanyAuth } from '@/auth/company'
import { CheckCircle, Play, RotateCcw } from 'lucide-react'
import { money } from '../assetFormat'

/**
 * The depreciation run surface for one asset: pick a financial year, compute, finalize,
 * reopen, and see the resulting line.
 *
 * Separate from DepreciationTab because it owns its own queries and mutations and none
 * of the tab's form state — the tab is inputs, this is results.
 */
export function DepreciationRunCard({ assetId }: { assetId: string }) {
  const toast = useToast()
  const { profile } = useCompanyAuth()
  const isAdmin = profile?.role === 'admin'

  const { data: fys = [] } = useFinancialYears()
  const { data: runs = [] } = useDepreciationRuns()
  const createRun = useCreateDepreciationRun()
  const finalizeRun = useFinalizeDepreciationRun()
  const reopenRunMutation = useReopenDepreciationRun()

  const [reopenOpen, setReopenOpen] = useState(false)
  const [reopenReason, setReopenReason] = useState('')
  const [selectedFyId, setSelectedFyId] = useState<string>(fys[0]?.id || '')

  const activeFyId = selectedFyId || fys[0]?.id || ''
  const latestRunForFy = runs.find((r) => r.financial_year_id === activeFyId)
  const { data: runLines = [], isLoading: linesLoading } = useAssetDepreciationLines(
    latestRunForFy?.id || '',
  )
  const assetLine = runLines.find((l) => l.asset_id === assetId)

  const handleRunDepreciation = async () => {
    if (!activeFyId) {
      toast.error('Please create or select a financial year first')
      return
    }
    try {
      await createRun.mutateAsync({ financialYearId: activeFyId })
      toast.success('Depreciation run computed successfully')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to run depreciation')
    }
  }

  const handleFinalize = async () => {
    if (!latestRunForFy) return
    try {
      await finalizeRun.mutateAsync(latestRunForFy.id)
      toast.success('Depreciation run finalized')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to finalize run')
    }
  }

  const handleReopen = async () => {
    if (!latestRunForFy || reopenReason.trim().length < 3) return
    try {
      await reopenRunMutation.mutateAsync({ runId: latestRunForFy.id, reason: reopenReason.trim() })
      toast.success('Run reopened to draft')
      setReopenOpen(false)
      setReopenReason('')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to reopen run')
    }
  }

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
        <div>
          <h4 className="text-sm font-semibold text-text-primary">
            Depreciation Calculation &amp; Schedule
          </h4>
          <p className="text-xs text-text-muted">Schedule II computation for the financial year</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            aria-label="Select Financial Year"
            value={activeFyId}
            onChange={(e) => setSelectedFyId(e.target.value)}
            className="h-8 rounded-btn border border-border-strong bg-bg-surface px-2.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
          >
            {fys.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label} ({f.status})
              </option>
            ))}
          </select>
          <Button
            size="sm"
            onClick={handleRunDepreciation}
            loading={createRun.isPending}
            disabled={!activeFyId}
          >
            <Play className="mr-1 h-3.5 w-3.5" />
            Compute
          </Button>
          {latestRunForFy && latestRunForFy.status === 'draft' && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleFinalize}
              loading={finalizeRun.isPending}
            >
              <CheckCircle className="mr-1 h-3.5 w-3.5" />
              Finalize
            </Button>
          )}
          {isAdmin && latestRunForFy && latestRunForFy.status === 'finalized' && (
            <>
              <Button variant="secondary" size="sm" onClick={() => setReopenOpen(true)}>
                <RotateCcw className="mr-1 h-3.5 w-3.5" />
                Reopen
              </Button>
              {/* ConfirmDialog renders a static message only, so the reason
                  field needs its own Modal-based dialog. */}
              <Modal
                open={reopenOpen}
                onClose={() => setReopenOpen(false)}
                title="Reopen finalized depreciation?"
                size="sm"
                footer={
                  <>
                    <Button
                      variant="secondary"
                      onClick={() => setReopenOpen(false)}
                      disabled={reopenRunMutation.isPending}
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={handleReopen}
                      loading={reopenRunMutation.isPending}
                      disabled={reopenReason.trim().length < 3}
                    >
                      Confirm reopen
                    </Button>
                  </>
                }
              >
                <p className="text-sm text-text-secondary">
                  {latestRunForFy.financial_year_label ?? 'This year'} will flip back to draft so
                  you can correct inputs and regenerate. Redo years oldest-first.
                </p>
                <Field
                  className="mt-3"
                  label="Reason (recorded in the audit log)"
                  required
                  hint="At least 3 characters"
                >
                  <Textarea
                    aria-label="Reason"
                    value={reopenReason}
                    onChange={(e) => setReopenReason(e.target.value)}
                  />
                </Field>
              </Modal>
            </>
          )}
        </div>
      </div>

      {linesLoading ? (
        <Spinner className="mx-auto my-6 h-5 w-5" />
      ) : assetLine ? (
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
          <div className="rounded-md border border-border bg-bg-inset/50 p-2.5">
            <span className="text-text-muted">Opening Gross Block</span>
            <p className="mt-0.5 font-semibold text-text-primary tabular-nums">
              {money(String(assetLine.opening_gross_block))}
            </p>
          </div>
          <div className="rounded-md border border-border bg-bg-inset/50 p-2.5">
            <span className="text-text-muted">Additions / Disposals</span>
            <p className="mt-0.5 font-semibold text-text-primary tabular-nums">
              +{money(String(assetLine.additions))} / -{money(String(assetLine.disposals))}
            </p>
          </div>
          <div className="rounded-md border border-border bg-bg-inset/50 p-2.5">
            <span className="text-text-muted">Depreciation (FY)</span>
            <p className="mt-0.5 font-semibold text-status-action tabular-nums">
              {money(String(assetLine.depreciation_for_year))}
            </p>
          </div>
          <div className="rounded-md border border-border bg-bg-inset/50 p-2.5">
            <span className="text-text-muted">Closing Carrying Amount (NBV)</span>
            <p className="mt-0.5 font-semibold text-status-verified tabular-nums">
              {money(String(assetLine.closing_carrying_amount))}
            </p>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-xs text-text-muted">
          No calculation run recorded yet for this financial year. Click "Compute" above to execute
          the depreciation engine.
        </p>
      )}
    </Card>
  )
}
```

- [ ] **Step 3: Strip DepreciationTab down**

In `frontend/src/pages/company/assets/tabs/DepreciationTab.tsx`:

1. Delete the whole `{/* Depreciation Calculation & Live Schedule */}` `<Card>` block (from that comment through its closing `</Card>`) and put in its place:

```tsx
      <DepreciationRunCard assetId={asset.id} />
```

2. Delete these now-unused declarations from the component body: `const { profile } = useCompanyAuth()`, `const isAdmin = ...`, `const { data: fys = [] } = useFinancialYears()`, `const { data: runs = [] } = useDepreciationRuns()`, `const createRun = ...`, `const finalizeRun = ...`, `const reopenRunMutation = ...`, the `reopenOpen`/`reopenReason`/`selectedFyId` state, `activeFyId`, `latestRunForFy`, the `useAssetDepreciationLines` call, `assetLine`, and the three handlers `handleRunDepreciation`, `handleFinalize`, `handleReopen`.

3. Fix the imports. The top of the file becomes:

```tsx
import { Card, Field, Input, Select, Textarea, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { AssetDetail } from '@/api/hooks/assets'
import { useUpdateAsset } from '@/api/hooks/assets'
import { useItBlocks, useAssetCategories } from '@/api/hooks/assetMasters'
import type { AssetUpdate } from '@/api/types'
import { DEPRECIATION_METHOD } from '@/api/enums'
import { dateOrDash, money, months, num } from '../assetFormat'
import { numOrNull, useSectionForm } from '../useSectionForm'
import { DerivedRow, SectionShell } from './SectionShell'
import { DepreciationRunCard } from './DepreciationRunCard'
```

The `useState`, `Button`, `Spinner`, `Modal`, `useCompanyAuth`, `useFinancialYears`,
`lucide-react`, and `@/api/hooks/depreciation` imports all go — they moved with the card.

- [ ] **Step 4: Verify nothing changed behaviourally**

Run: `cd frontend && npm run test -- reopen`
Expected: PASS — unchanged. The test mocks `@/api/hooks/depreciation` at module scope, which still intercepts the card's imports.

Run: `cd frontend && npm run lint`
Expected: PASS — no unused imports left behind in `DepreciationTab.tsx`

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/company/assets/tabs/DepreciationRunCard.tsx frontend/src/pages/company/assets/tabs/DepreciationTab.tsx
git commit -m "refactor(assets): extract DepreciationRunCard from DepreciationTab"
```

---

### Task 13: Projection client and hook

**Files:**
- Modify: `frontend/src/api/endpoints/depreciation.ts`
- Modify: `frontend/src/api/hooks/depreciation.ts`
- Test: `frontend/src/api/hooks/explainDepreciation.test.ts`

**Interfaces:**
- Produces:
  - `depreciationApi.explain(assetId: string, financialYearId: string): Promise<DepreciationExplain>`
  - `depreciationKeys.explain(assetId: string, fyId: string)`
  - `useExplainDepreciation(assetId: string, fyId: string, enabled: boolean)`
  - `interface DepreciationExplain { companies_act: CalcTrace; income_tax: CalcTrace | null }`

`enabled` is a required argument, not an optional flag: the projection must not be
fetched until the drawer is actually open.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/hooks/explainDepreciation.test.ts`:

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest'

const post = vi.fn()
vi.mock('@/api/clients/company', () => ({ companyClient: { get: vi.fn(), post, delete: vi.fn() } }))

const { depreciationApi } = await import('@/api/endpoints/depreciation')
const { depreciationKeys } = await import('@/api/hooks/depreciation')

describe('depreciationApi.explain', () => {
  beforeEach(() => post.mockReset())

  it('posts the asset and financial year to the explain endpoint', async () => {
    post.mockResolvedValue({ companies_act: { steps: [] }, income_tax: null })
    await depreciationApi.explain('asset-1', 'fy-1')

    expect(post).toHaveBeenCalledWith('/api/v1/depreciation/explain', {
      body: { asset_id: 'asset-1', financial_year_id: 'fy-1' },
    })
  })
})

describe('depreciationKeys.explain', () => {
  it('keys a projection by both asset and year, so switching year refetches', () => {
    expect(depreciationKeys.explain('a1', 'fy1')).not.toEqual(
      depreciationKeys.explain('a1', 'fy2'),
    )
    expect(depreciationKeys.explain('a1', 'fy1')).toEqual(depreciationKeys.explain('a1', 'fy1'))
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- explainDepreciation`
Expected: FAIL — `depreciationApi.explain is not a function`

- [ ] **Step 3a: Add the client method**

In `frontend/src/api/endpoints/depreciation.ts`, add the type and the method:

```ts
import type { CalcTrace } from '@/components/calc'
```

```ts
/** Traces computed on demand and never stored. `income_tax` is null without a block. */
export interface DepreciationExplain {
  companies_act: CalcTrace
  income_tax: CalcTrace | null
}
```

and inside `depreciationApi`:

```ts
  explain: (assetId: string, financialYearId: string) =>
    companyClient.post<DepreciationExplain>('/api/v1/depreciation/explain', {
      body: { asset_id: assetId, financial_year_id: financialYearId },
    }),
```

- [ ] **Step 3b: Add the hook**

In `frontend/src/api/hooks/depreciation.ts`, extend the key factory:

```ts
export const depreciationKeys = {
  runs: ['depreciation', 'runs'] as const,
  run: (id: string) => ['depreciation', 'run', id] as const,
  lines: (id: string) => ['depreciation', 'lines', id] as const,
  itLines: (id: string) => ['depreciation', 'it-lines', id] as const,
  explain: (assetId: string, fyId: string) =>
    ['depreciation', 'explain', assetId, fyId] as const,
}
```

and add the hook:

```ts
/**
 * A depreciation projection for one asset and year, computed on demand.
 *
 * `enabled` is required rather than defaulted: this fires the engine, so it must wait
 * until the drawer is actually open.
 */
export function useExplainDepreciation(assetId: string, fyId: string, enabled: boolean) {
  return useQuery({
    queryKey: depreciationKeys.explain(assetId, fyId),
    queryFn: () => depreciationApi.explain(assetId, fyId),
    enabled: enabled && !!assetId && !!fyId,
    // Inputs change while a user is editing the asset, so a stale projection would
    // explain figures they have already moved past.
    staleTime: 0,
    retry: false,
  })
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- explainDepreciation`
Expected: PASS — 2 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/endpoints/depreciation.ts frontend/src/api/hooks/depreciation.ts frontend/src/api/hooks/explainDepreciation.test.ts
git commit -m "feat(assets): projection client and hook for depreciation traces"
```

---

### Task 14: Wire the Depreciation tab

**Files:**
- Modify: `frontend/src/pages/company/assets/tabs/DepreciationRunCard.tsx`
- Create: `frontend/src/pages/company/assets/tabs/DepreciationDerivedCard.tsx`
- Modify: `frontend/src/pages/company/assets/tabs/DepreciationTab.tsx`
- Modify: `frontend/src/pages/company/assets/tabs/reopen.test.tsx` — extend the hook mock
- Test: `frontend/src/pages/company/assets/tabs/explain.test.tsx`

**Interfaces:**
- Consumes: `CalculationDrawer`, `ExplainLink`, `TraceTab` (Tasks 10-11); `useExplainDepreciation` (Task 13); `useItBlockDepreciationLines` (existing)
- Produces: `DepreciationDerivedCard({ assetId, originalCost, residualPct, warrantyExpiryDate })`

Three states the run card must distinguish, because conflating them is how a drawer
misleads:

| State | What the drawer shows |
|---|---|
| Line with a trace | The recorded trace, with `computed_at` |
| No line for this year | A projection, fetched automatically, banner-marked |
| Line without a trace (pre-feature run) | "Recorded before calculation traces were kept", with a button to see a projection instead |

**Note for the implementer:** `reopen.test.tsx` mocks `@/api/hooks/depreciation` with a
factory that lists each hook. Adding `useExplainDepreciation` and
`useItBlockDepreciationLines` to the card means that mock must list them too, or the
component calls `undefined`. Step 3d covers it.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/company/assets/tabs/explain.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from '@/components/ui/Toast'
import type { CalcTrace } from '@/components/calc'

const fy = {
  id: 'fy-1',
  company_id: 'c1',
  label: '2024-25',
  start_date: '2024-04-01',
  end_date: '2025-03-31',
  status: 'open' as const,
}

const run = {
  id: 'r1',
  company_id: 'c1',
  financial_year_id: 'fy-1',
  financial_year_label: '2024-25',
  run_date: '2025-03-31',
  status: 'draft' as const,
  total_gross_block: 0,
  total_depreciation: 0,
  total_carrying_amount: 0,
  total_it_depreciation: 0,
  total_it_closing_wdv: 0,
  created_at: '2025-03-31T00:00:00Z',
  updated_at: '2025-03-31T00:00:00Z',
}

const recordedTrace: CalcTrace = {
  title: 'Depreciation — Companies Act Schedule II — FY 2024-25',
  basis: 'SLM — straight line; useful life 60 months; residual 5.00%; original cost 100,000.00',
  is_projection: false,
  computed_at: '2025-04-01T10:00:00Z',
  steps: [
    { key: 'depreciable_base', group: 'Rate', label: 'Depreciable base', formula: 'Original cost − Residual value', substitution: '100,000.00 − 5,000.00', result: '95,000.00', unit: 'money', emphasis: false },
    { key: 'depreciation_for_year', group: 'Charge for the year', label: 'Depreciation for the year', formula: 'x', substitution: 'y', result: '19,000.00', unit: 'money', emphasis: true },
  ],
}

const projectedTrace: CalcTrace = { ...recordedTrace, is_projection: true, computed_at: null }

const line = (calc_trace: CalcTrace | null) => ({
  id: 'l1',
  run_id: 'r1',
  asset_id: 'asset-1',
  method: 'SLM',
  opening_gross_block: '100000.00',
  additions: '0.00',
  disposals: '0.00',
  closing_gross_block: '100000.00',
  opening_accumulated_depreciation: '0.00',
  depreciation_for_year: '19000.00',
  disposal_accumulated_depreciation: '0.00',
  closing_accumulated_depreciation: '19000.00',
  opening_carrying_amount: '100000.00',
  closing_carrying_amount: '81000.00',
  residual_value: '5000.00',
  remaining_useful_life_days: 1460,
  effective_rate_pct: '19.00',
  is_part_year: false,
  is_disposed: false,
  gain_loss_on_disposal: null,
  calc_trace,
})

const explain = vi.fn()
let lines: unknown[] = []

vi.mock('@/api/hooks/depreciation', () => ({
  useDepreciationRuns: () => ({ data: [run], isLoading: false }),
  useCreateDepreciationRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useFinalizeDepreciationRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReopenDepreciationRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAssetDepreciationLines: () => ({ data: lines, isLoading: false }),
  useItBlockDepreciationLines: () => ({ data: [], isLoading: false }),
  useExplainDepreciation: (_a: string, _f: string, enabled: boolean) =>
    enabled
      ? { data: explain(), isLoading: false, error: null }
      : { data: undefined, isLoading: false, error: null },
}))
vi.mock('@/api/hooks/financialYears', () => ({
  useFinancialYears: () => ({ data: [fy], isLoading: false }),
}))
vi.mock('@/auth/company', () => ({ useCompanyAuth: () => ({ profile: { role: 'admin' } }) }))

const { DepreciationRunCard } = await import('./DepreciationRunCard')

function renderCard() {
  return render(
    <ToastProvider>
      <DepreciationRunCard assetId="asset-1" itBlockId={null} />
    </ToastProvider>,
  )
}

describe('DepreciationRunCard calculation drawer', () => {
  it('opens the recorded trace from the header link', async () => {
    lines = [line(recordedTrace)]
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /see the calculation/i }))

    await waitFor(() => expect(screen.getByText('Depreciable base')).toBeTruthy())
    expect(screen.getByText(/Computed/)).toBeTruthy()
    expect(screen.queryByText(/not the recorded figure/i)).toBeNull()
  })

  it('deep-links from a stat tile to that figure', async () => {
    lines = [line(recordedTrace)]
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /how was depreciation \(fy\) calculated/i }))

    await waitFor(() =>
      expect(document.getElementById('calc-step-depreciation_for_year')?.getAttribute('data-focused')).toBe('true'),
    )
  })

  it('projects when no run exists for the year', async () => {
    lines = []
    explain.mockReturnValue({ companies_act: projectedTrace, income_tax: null })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /see the calculation/i }))

    await waitFor(() => expect(screen.getByText(/not the recorded figure/i)).toBeTruthy())
  })

  it('says so when a run predates traces, and offers a projection', async () => {
    lines = [line(null)]
    explain.mockReturnValue({ companies_act: projectedTrace, income_tax: null })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /see the calculation/i }))
    await waitFor(() =>
      expect(screen.getByText(/before calculation traces were kept/i)).toBeTruthy(),
    )
    // It does not silently substitute a projection for the recorded figure.
    expect(screen.queryByText('Depreciable base')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /projection/i }))
    await waitFor(() => expect(screen.getByText(/not the recorded figure/i)).toBeTruthy())
  })

  it('does not fetch a projection until the drawer is opened', () => {
    lines = []
    explain.mockClear()
    explain.mockReturnValue({ companies_act: projectedTrace, income_tax: null })
    renderCard()

    expect(explain).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- explain.test`
Expected: FAIL — no "See the calculation" button in the run card

- [ ] **Step 3a: Wire the run card**

In `frontend/src/pages/company/assets/tabs/DepreciationRunCard.tsx`:

Widen the signature to take the block, which the Income Tax tab of the drawer needs:

```tsx
export function DepreciationRunCard({
  assetId,
  itBlockId,
}: {
  assetId: string
  itBlockId?: string | null
}) {
```

and pass it from `DepreciationTab.tsx`:

```tsx
      <DepreciationRunCard assetId={asset.id} itBlockId={values.it_block_id} />
```

Extend the imports:

```tsx
import { useMemo, useState } from 'react'
import {
  CalculationDrawer,
  ExplainLink,
  type CalcTrace,
  type TraceTab,
} from '@/components/calc'
import { ApiError } from '@/api/http'
import {
  useAssetDepreciationLines,
  useCreateDepreciationRun,
  useDepreciationRuns,
  useExplainDepreciation,
  useFinalizeDepreciationRun,
  useItBlockDepreciationLines,
  useReopenDepreciationRun,
} from '@/api/hooks/depreciation'
```

Add a tile component above `DepreciationRunCard`:

```tsx
/** A run figure, with a deep link into the step that produced it. */
function RunTile({
  label,
  value,
  valueClass,
  onExplain,
}: {
  label: string
  value: string
  valueClass: string
  onExplain: () => void
}) {
  return (
    <button
      type="button"
      onClick={onExplain}
      aria-label={`How was ${label} calculated?`}
      className="rounded-md border border-border bg-bg-inset/50 p-2.5 text-left hover:border-border-strong focus:outline-none focus:ring-1 focus:ring-accent"
    >
      <span className="text-text-muted">{label}</span>
      <p className={`mt-0.5 font-semibold tabular-nums ${valueClass}`}>{value}</p>
    </button>
  )
}
```

Inside the component, after `assetLine` is derived, add the drawer state and trace resolution:

```tsx
  const { data: itLines = [] } = useItBlockDepreciationLines(latestRunForFy?.id || '')

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [focusStep, setFocusStep] = useState<string | undefined>(undefined)
  const [forceProjection, setForceProjection] = useState(false)

  // Read through a local shape rather than the generated response type: `calc_trace`
  // only appears in `schema.d.ts` once `npm run gen:api` has been run against a
  // backend carrying Task 6, and this must compile before then.
  type WithTrace = { calc_trace?: CalcTrace | null }
  const recordedCa = (assetLine as WithTrace | undefined)?.calc_trace ?? null
  const recordedIt = itBlockId
    ? ((itLines.find((l) => l.it_block_id === itBlockId) as WithTrace | undefined)
        ?.calc_trace ?? null)
    : null

  // Nothing recorded for this year at all: project straight away, since there is no
  // recorded figure a projection could be confused with.
  const noLineYet = !assetLine
  // A line that predates traces is a different case, and says so rather than being
  // quietly replaced by today's inputs.
  const linePredatesTraces = !!assetLine && !recordedCa

  const wantProjection = drawerOpen && (forceProjection || noLineYet)
  const projection = useExplainDepreciation(assetId, activeFyId, wantProjection)

  const tabs: TraceTab[] = useMemo(() => {
    if (wantProjection) {
      const data = projection.data
      if (!data) return []
      return [
        { id: 'ca', label: 'Companies Act', trace: data.companies_act },
        ...(data.income_tax
          ? [{ id: 'it', label: 'Income Tax', trace: data.income_tax }]
          : []),
      ]
    }
    return [
      ...(recordedCa ? [{ id: 'ca', label: 'Companies Act', trace: recordedCa }] : []),
      ...(recordedIt ? [{ id: 'it', label: 'Income Tax', trace: recordedIt }] : []),
    ]
  }, [wantProjection, projection.data, recordedCa, recordedIt])

  const projectionError =
    projection.error instanceof ApiError && typeof projection.error.detail === 'string'
      ? projection.error.detail
      : projection.error instanceof Error
        ? projection.error.message
        : null

  const openDrawer = (step?: string) => {
    setFocusStep(step)
    setForceProjection(false)
    setDrawerOpen(true)
  }
```

Add the header trigger, immediately after the `<p className="text-xs text-text-muted">Schedule II computation...</p>`:

```tsx
          <ExplainLink onClick={() => openDrawer()} />
```

Replace the four stat-tile `<div>`s with:

```tsx
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
          <RunTile
            label="Opening Gross Block"
            value={money(String(assetLine.opening_gross_block))}
            valueClass="text-text-primary"
            onExplain={() => openDrawer('opening_gross_block')}
          />
          <RunTile
            label="Additions / Disposals"
            value={`+${money(String(assetLine.additions))} / -${money(String(assetLine.disposals))}`}
            valueClass="text-text-primary"
            onExplain={() => openDrawer('additions')}
          />
          <RunTile
            label="Depreciation (FY)"
            value={money(String(assetLine.depreciation_for_year))}
            valueClass="text-status-action"
            onExplain={() => openDrawer('depreciation_for_year')}
          />
          <RunTile
            label="Closing Carrying Amount (NBV)"
            value={money(String(assetLine.closing_carrying_amount))}
            valueClass="text-status-verified"
            onExplain={() => openDrawer('closing_carrying_amount')}
          />
        </div>
```

And render the drawer just before the closing `</Card>`:

```tsx
      <CalculationDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        tabs={tabs}
        focusStep={focusStep}
        loading={wantProjection && projection.isLoading}
        error={wantProjection ? projectionError : null}
        emptyNote={
          linePredatesTraces && !forceProjection
            ? 'This run was recorded before calculation traces were kept.'
            : undefined
        }
        onShowProjection={
          linePredatesTraces && !forceProjection ? () => setForceProjection(true) : undefined
        }
        contextNote={
          latestRunForFy
            ? latestRunForFy.status === 'finalized'
              ? 'Finalized run'
              : 'Draft run'
            : undefined
        }
      />
```

- [ ] **Step 3b: Create the derived-parameters card**

Create `frontend/src/pages/company/assets/tabs/DepreciationDerivedCard.tsx`:

```tsx
import { useMemo, useState } from 'react'
import { Card } from '@/components/ui'
import { CalculationDrawer, ExplainLink, type TraceTab } from '@/components/calc'
import { ApiError } from '@/api/http'
import { useExplainDepreciation } from '@/api/hooks/depreciation'
import { useFinancialYears } from '@/api/hooks/financialYears'
import { dateOrDash, money, num } from '../assetFormat'
import { DerivedRow } from './SectionShell'

/**
 * The figures the register derives from the depreciation inputs above it.
 *
 * These are not a run's output, so the drawer here always projects: it answers "what
 * would this asset depreciate, on the inputs currently on screen". The current
 * financial year is used, since a derived parameter is not tied to a particular year.
 */
export function DepreciationDerivedCard({
  assetId,
  originalCost,
  residualPct,
  warrantyExpiryDate,
}: {
  assetId: string
  originalCost: string | null
  residualPct: string | null
  warrantyExpiryDate: string | null
}) {
  const { data: fys = [] } = useFinancialYears()
  const fyId = fys.find((f) => f.status === 'open')?.id ?? fys[0]?.id ?? ''

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [focusStep, setFocusStep] = useState<string | undefined>(undefined)

  const projection = useExplainDepreciation(assetId, fyId, drawerOpen)

  const tabs: TraceTab[] = useMemo(() => {
    const data = projection.data
    if (!data) return []
    return [
      { id: 'ca', label: 'Companies Act', trace: data.companies_act },
      ...(data.income_tax ? [{ id: 'it', label: 'Income Tax', trace: data.income_tax }] : []),
    ]
  }, [projection.data])

  const error =
    projection.error instanceof ApiError && typeof projection.error.detail === 'string'
      ? projection.error.detail
      : projection.error instanceof Error
        ? projection.error.message
        : null

  const open = (step?: string) => {
    setFocusStep(step)
    setDrawerOpen(true)
  }

  const cost = num(originalCost)
  const residual = num(residualPct)
  const residualAmount = cost !== null && residual !== null ? (cost * residual) / 100 : null
  const depreciableBase = cost !== null && residualAmount !== null ? cost - residualAmount : null

  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-text-primary">Derived Parameters</h4>
        <ExplainLink onClick={() => open()} />
      </div>
      <DerivedRow label="Original accounting cost" value={money(originalCost)} />
      <DerivedRow
        label="Residual value"
        value={residualAmount === null ? '—' : money(String(residualAmount))}
        hint={residual !== null ? `${residual}% of original cost` : undefined}
        onExplain={() => open('residual_value')}
      />
      <DerivedRow
        label="Depreciable base"
        value={depreciableBase === null ? '—' : money(String(depreciableBase))}
        hint="Cost less residual value"
        emphasis
        onExplain={() => open('depreciable_base')}
      />
      <DerivedRow label="Warranty expiry" value={dateOrDash(warrantyExpiryDate)} />

      <CalculationDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        tabs={tabs}
        focusStep={focusStep}
        loading={projection.isLoading}
        error={error}
        emptyNote="There is no financial year to compute against yet."
      />
    </Card>
  )
}
```

- [ ] **Step 3c: Use it from the tab**

In `frontend/src/pages/company/assets/tabs/DepreciationTab.tsx`, replace the whole
`Derived Parameters` `<Card>` block with:

```tsx
      <DepreciationDerivedCard
        assetId={asset.id}
        originalCost={asset.original_cost}
        residualPct={values.residual_pct}
        warrantyExpiryDate={asset.warranty_expiry_date}
      />
```

Add the import:

```tsx
import { DepreciationDerivedCard } from './DepreciationDerivedCard'
```

Remove `Card`, `DerivedRow`, `num`, `money` and `dateOrDash` from the imports if nothing
else in the file still uses them — `months` is still used by a field hint, and
`dateOrDash` by the warranty hint, so check each rather than deleting the line wholesale.
Also delete the now-unused `cost` / `residual` / `residualAmount` / `depreciableBase`
locals.

- [ ] **Step 3d: Extend the reopen test's mock**

In `frontend/src/pages/company/assets/tabs/reopen.test.tsx`, add to the
`vi.mock('@/api/hooks/depreciation', ...)` factory:

```ts
  useItBlockDepreciationLines: () => ({ data: [], isLoading: false }),
  useExplainDepreciation: () => ({ data: undefined, isLoading: false, error: null }),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run test -- explain.test`
Expected: PASS — 5 passed

Run: `cd frontend && npm run test`
Expected: PASS — whole frontend suite, `reopen.test.tsx` included

Run: `cd frontend && npx tsc -b --noEmit && npm run lint`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/company/assets/tabs/
git commit -m "feat(assets): calculation drawer on the depreciation tab"
```

---

### Task 15: Wire the Acquisition and Tax tabs

**Files:**
- Modify: `frontend/src/pages/company/assets/tabs/AcquisitionTab.tsx` — the cost build-up card (lines ~441-470)
- Modify: `frontend/src/pages/company/assets/tabs/TaxTab.tsx` — the GST card (lines ~211-228)
- Test: `frontend/src/pages/company/assets/tabs/costExplain.test.tsx`

**Interfaces:**
- Consumes: `traceFromCostPreview`, `CalculationDrawer`, `ExplainLink` (Tasks 9-11); `GST_BASIS_LABEL` from `../assetFormat`

No data fetching here: the acquisition object already holds every intermediate, so the
trace is built in a `useMemo` and the drawer opens instantly.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/company/assets/tabs/costExplain.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from '@/components/ui/Toast'

vi.mock('@/api/hooks/assets', () => ({ useUpdateAsset: () => ({ mutateAsync: vi.fn(), isPending: false }) }))
vi.mock('@/api/hooks/assetMasters', () => ({
  useSuppliers: () => ({ data: [] }),
  useItBlocks: () => ({ data: [] }),
  useAssetCategories: () => ({ data: [] }),
}))
vi.mock('@/api/hooks/branches', () => ({ useBranches: () => ({ data: [] }) }))

const acq = {
  id: 'acq-1',
  quantity: 3,
  gross_basic_price: '100000.00',
  discount_amount: '5000.00',
  net_basic_price: '95000.00',
  gst_rate: '18.00',
  gst_split_basis: 'intra_state',
  cgst_amount: '8550.00',
  sgst_amount: '8550.00',
  igst_amount: '0.00',
  total_gst: '17100.00',
  recoverable_gst: '17100.00',
  capitalizable_gst: '0.00',
  freight_cost: '2000.00',
  installation_cost: '1500.00',
  other_capitalizable_cost: '0.00',
  landed_cost: '98500.00',
  total_acquisition_outlay: '115600.00',
  per_unit_cost: '32833.34',
  itc_treatment: 'eligible',
  gst_amounts_overridden: false,
}

describe('cost build-up drawer', () => {
  it('explains the landed cost from the acquisition tab', async () => {
    const { AcquisitionTab } = await import('./AcquisitionTab')
    render(
      <ToastProvider>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <AcquisitionTab detail={{ asset: { id: 'a1' }, acquisition: acq } as any} locked={false} />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: /how was total capitalized value calculated/i }))

    await waitFor(() => expect(screen.getByText('Total capitalized value')).toBeTruthy())
    const row = document.getElementById('calc-step-landed_cost')
    expect(row?.getAttribute('data-focused')).toBe('true')
    // Built from data already on the page — no projection banner.
    expect(screen.queryByText(/not the recorded figure/i)).toBeNull()
  })

  it('shows the per-unit allocation for a multi-unit acquisition', async () => {
    const { AcquisitionTab } = await import('./AcquisitionTab')
    render(
      <ToastProvider>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <AcquisitionTab detail={{ asset: { id: 'a1' }, acquisition: acq } as any} locked={false} />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: /see the calculation/i }))
    await waitFor(() => expect(screen.getByText('Per-unit cost')).toBeTruthy())
    expect(screen.getByText(/98,500.00 ÷ 3/)).toBeTruthy()
  })

  it('explains the GST split from the tax tab', async () => {
    const { TaxTab } = await import('./TaxTab')
    render(
      <ToastProvider>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        <TaxTab detail={{ asset: { id: 'a1' }, acquisition: acq } as any} locked={false} />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: /how was total gst calculated/i }))

    await waitFor(() =>
      expect(document.getElementById('calc-step-total_gst')?.getAttribute('data-focused')).toBe('true'),
    )
    expect(screen.getByText('Intra-state — CGST + SGST')).toBeTruthy()
  })
})
```

**Note:** the mock list above may need adjusting to the hooks these two tabs actually
import — read the top of each file and mock exactly those. The assertions are the point;
the mocks are scaffolding.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- costExplain`
Expected: FAIL — no explain affordance in either tab

- [ ] **Step 3a: Wire the Acquisition tab**

In `frontend/src/pages/company/assets/tabs/AcquisitionTab.tsx`, add imports:

```tsx
import { useMemo, useState } from 'react'
import { CalculationDrawer, ExplainLink, traceFromCostPreview } from '@/components/calc'
import { GST_BASIS_LABEL } from '../assetFormat'
```

(If `useMemo`/`useState` are already imported from `react`, extend that import rather
than adding a second one. Likewise check whether `GST_BASIS_LABEL` is already imported.)

Inside the component, above the return:

```tsx
  const [calcOpen, setCalcOpen] = useState(false)
  const [calcStep, setCalcStep] = useState<string | undefined>(undefined)

  // Every intermediate is already on `acq`, so this is presentation, not a fetch.
  const costTrace = useMemo(
    () =>
      traceFromCostPreview(acq, {
        title: 'Acquisition cost build-up',
        gstBasisLabel: acq.gst_split_basis ? GST_BASIS_LABEL[acq.gst_split_basis] : undefined,
      }),
    [acq],
  )

  const openCalc = (step?: string) => {
    setCalcStep(step)
    setCalcOpen(true)
  }
```

Replace the cost build-up card's heading line with a header row, and add the deep links:

```tsx
      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-text-primary">Cost build-up</h4>
          <ExplainLink onClick={() => openCalc()} />
        </div>
        <DerivedRow label="Gross basic price" value={money(acq.gross_basic_price)} />
        <DerivedRow label="Less discount" value={money(acq.discount_amount)} />
        <DerivedRow label="Net basic price" value={money(acq.net_basic_price)} hint="Taxable value" />
        <DerivedRow
          label="Add capitalizable GST"
          value={money(acq.capitalizable_gst)}
          hint="GST that cannot be recovered becomes part of cost"
          onExplain={() => openCalc('capitalizable_gst')}
        />
        <DerivedRow label="Add freight" value={money(acq.freight_cost)} />
        <DerivedRow label="Add installation" value={money(acq.installation_cost)} />
        <DerivedRow label="Add other capitalizable" value={money(acq.other_capitalizable_cost)} />
        <div className="mt-1 border-t border-border pt-1">
          <DerivedRow
            label="Total capitalized value"
            value={money(acq.landed_cost)}
            hint="What goes on the balance sheet and depreciates"
            emphasis
            onExplain={() => openCalc('landed_cost')}
          />
          <DerivedRow
            label="Per-unit cost"
            value={money(acq.per_unit_cost)}
            hint={`Allocated across ${acq.quantity} unit${acq.quantity === 1 ? '' : 's'}, summing exactly to the total`}
            onExplain={() => openCalc('per_unit_cost')}
          />
          <DerivedRow
            label="Total acquisition outlay"
            value={money(acq.total_acquisition_outlay)}
            hint="Total cash paid, including recoverable GST — not the depreciation base"
            onExplain={() => openCalc('total_acquisition_outlay')}
          />
        </div>

        <CalculationDrawer
          open={calcOpen}
          onClose={() => setCalcOpen(false)}
          tabs={[{ id: 'cost', label: 'Cost build-up', trace: costTrace }]}
          focusStep={calcStep}
        />
      </Card>
```

- [ ] **Step 3b: Wire the Tax tab**

In `frontend/src/pages/company/assets/tabs/TaxTab.tsx`, add the imports:

```tsx
import { useMemo, useState } from 'react'
import { CalculationDrawer, ExplainLink, traceFromCostPreview } from '@/components/calc'
```

(`GST_BASIS_LABEL` and `money` are already imported from `../assetFormat`. If `useState`
is already imported from `react`, extend that import rather than adding a second one.)

Inside the component, above the return:

```tsx
  const [calcOpen, setCalcOpen] = useState(false)
  const [calcStep, setCalcStep] = useState<string | undefined>(undefined)

  // Same source data as the Acquisition tab's build-up, framed as the tax question.
  const costTrace = useMemo(
    () =>
      traceFromCostPreview(acq, {
        title: 'GST and input tax credit',
        gstBasisLabel: acq.gst_split_basis ? GST_BASIS_LABEL[acq.gst_split_basis] : undefined,
      }),
    [acq],
  )

  const openCalc = (step?: string) => {
    setCalcStep(step)
    setCalcOpen(true)
  }
```

Then give the GST derived card a header row and deep links:

```tsx
      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-text-primary">GST computation</h4>
          <ExplainLink onClick={() => openCalc()} />
        </div>
        <DerivedRow label="Taxable value" value={money(acq.net_basic_price)} />
        <DerivedRow label="CGST" value={money(acq.cgst_amount)} />
        <DerivedRow label="SGST" value={money(acq.sgst_amount)} />
        <DerivedRow label="IGST" value={money(acq.igst_amount)} />
        <DerivedRow
          label="Total GST"
          value={money(acq.total_gst)}
          emphasis
          onExplain={() => openCalc('total_gst')}
        />
```

Then keep the two conditional ITC rows, adding a deep link to each:

```tsx
        <DerivedRow
          label="Recoverable GST (input tax credit)"
          value={money(acq.recoverable_gst)}
          hint="Recovered, so not part of the asset's cost"
          onExplain={() => openCalc('recoverable_gst')}
        />
        <DerivedRow
          label="Capitalizable GST"
          value={money(acq.capitalizable_gst)}
          hint="No credit available, so it becomes part of cost and depreciates"
          onExplain={() => openCalc('capitalizable_gst')}
        />
```

Preserve whatever conditional wrapper and `hint` text those two rows already have —
lines 217-227 of the current file — and add only the `onExplain` prop. The block above
shows the shape, not a replacement for the existing wording.

Render the drawer before the card's closing tag:

```tsx
        <CalculationDrawer
          open={calcOpen}
          onClose={() => setCalcOpen(false)}
          tabs={[{ id: 'gst', label: 'GST and input tax credit', trace: costTrace }]}
          focusStep={calcStep}
        />
```

If the existing card has no `<h4>` heading, add the header row shown above anyway — the
trigger needs somewhere to sit, and the card needs a name for the drawer's sake.

- [ ] **Step 4: Run everything**

Run: `cd frontend && npm run test`
Expected: PASS — whole frontend suite

Run: `cd frontend && npx tsc -b --noEmit && npm run lint`
Expected: no errors

Run: `pytest -q`
Expected: PASS — whole backend suite

- [ ] **Step 5: Regenerate the API types**

With the backend running (`uvicorn app.main:app --reload` or the compose stack):

Run: `cd frontend && npm run gen:api`
Expected: `src/api/schema.d.ts` gains `CalcStepSchema`, `CalcTraceSchema`,
`DepreciationExplainRequest`, `DepreciationExplainResponse`, and `calc_trace` on the two
line response schemas. Then run `npx tsc -b --noEmit` again — the hand-written types in
`components/calc/types.ts` should agree with the generated ones. If they disagree, the
generated schema is authoritative: fix `types.ts`.

If the backend cannot be started in this environment, skip this step and say so in the
commit message; nothing depends on it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/company/assets/tabs/AcquisitionTab.tsx frontend/src/pages/company/assets/tabs/TaxTab.tsx frontend/src/pages/company/assets/tabs/costExplain.test.tsx frontend/src/api/schema.d.ts
git commit -m "feat(assets): calculation drawer on the acquisition and tax tabs"
```

---

## Manual verification

After Task 15, check the real app rather than only the tests:

1. Open an asset with a computed, finalized depreciation run. The Depreciation tab's run
   card shows "See the calculation". Open it: the Companies Act tab lists Inputs → Rate →
   Charge for the year → Roll-forward, `Depreciation for the year` is emphasised, and its
   figure matches the "Depreciation (FY)" tile exactly.
2. Click the "Closing Carrying Amount (NBV)" tile. The drawer opens scrolled to that step
   with it ring-highlighted.
3. Switch to the Income Tax tab. Confirm it states that the block figure is the block's,
   and shows this asset's share.
4. Open the drawer for an asset in a financial year with no run. Confirm the dashed amber
   projection banner and "Recompute the run to record this".
5. Clear an asset's useful life and open the drawer. Confirm the 422 message renders as an
   explanation rather than an error toast.
6. On the Acquisition tab, click the icon beside "Total capitalized value" and confirm the
   drawer lands on that step, with no projection banner.
7. Press "Copy calculation" and paste into a text editor. Confirm the plain text carries
   the title, the basis, the group headings, and every formula.
8. Check the drawer in both light and dark theme.
