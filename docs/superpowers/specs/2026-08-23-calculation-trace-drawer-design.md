# Calculation Trace Drawer — Design

**Date:** 2026-08-23
**Module:** Assets (fixed-asset register)
**Status:** Approved, ready for planning

## Problem

The assets module shows derived figures — depreciation for the year, closing carrying
amount, landed cost, recoverable vs. capitalizable GST — with no way to see how they
were arrived at. When an auditor or a finance user questions a number, the only
recourse is to read the engine source.

The engines compute the interesting intermediates and discard them. `depreciation.py`
derives the Schedule II WDV rate `1-(s/c)^(1/n)`, the pro-rata active-day fraction and
the residual cap, then returns only the final line. `it_depreciation.py` splits the
full-rate and half-rate pools and drops the split. Nothing that explains a figure
survives the function call.

## Goal

Wherever a major derived figure appears, offer a "See the calculation" affordance that
opens a panel showing, for each step: the formula, the same formula with this asset's
values substituted in, and the result.

## Scope

In scope:

- Companies Act Schedule II per-asset depreciation
- Income Tax Act s.32 block depreciation
- Acquisition cost build-up (gross price through landed cost)
- GST split and ITC treatment

Out of scope for v1 (the drawer is reusable, so these are later additions, not rework):

- Asset reports and register roll-forwards
- Disposal gain/loss as a standalone site — it appears as steps inside the
  depreciation trace for a disposal year, but the disposal modal gets no trigger

## Core concept: the calculation trace

One format, three producers, one renderer. The renderer knows nothing about assets.

```
CalcStep {
  key: string          // stable id, the deep-link target
  group: string        // section heading
  label: string
  formula: string      // "Cost - Residual value"
  substitution: string // "1,20,000.00 - 6,000.00"
  result: string       // "1,14,000.00"
  unit: 'money' | 'percent' | 'days' | 'months' | 'count' | 'none'
  emphasis?: boolean   // the figure shown on the page
  note?: string        // only where a rule surprises
}

CalcTrace {
  title: string
  basis: string        // the inputs this trace used
  steps: CalcStep[]
  is_projection: boolean
  computed_at?: string // null on projections
}
```

Two rules:

**Formatting happens at the producer.** `substitution` and `result` arrive as finished
strings, formatted with the same Decimal quantization the engine used. The renderer
lays out text and never rounds. This is what makes it impossible for the drawer to
display a different number than the row it explains.

**Groups, not nesting.** Steps are a flat ordered list; the drawer renders a heading
whenever `group` changes. A depreciation computation reads as a sequence — cost, base,
rate, charge, roll-forward — and flat keeps deep-linking and scrolling trivial.

`note` is used sparingly, only where a rule genuinely surprises people: the 180-day
half rate (s.32(1) proviso), blocked ITC (CGST s.17(5)), and the residual cap. Every
other step is formula and numbers.

### Step keys

The key set is a contract between the builders and the trigger call sites.

**Schedule II** (`companies_act`):

| group | key |
|---|---|
| Inputs | `original_cost`, `residual_pct`, `residual_value`, `useful_life_months`, `opening_gross_block`, `opening_accumulated_depreciation`, `opening_carrying_amount` |
| Rate | `depreciable_base`, `useful_years`, `wdv_rate`, `annual_depreciation` |
| Charge for the year | `active_days`, `total_fy_days`, `prorata_depreciation`, `residual_cap`, `depreciation_for_year` |
| Roll-forward | `additions`, `disposals`, `closing_gross_block`, `closing_accumulated_depreciation`, `closing_carrying_amount`, `remaining_useful_life`, `effective_rate_pct` |
| Disposal | `nbv_at_disposal`, `sale_proceeds`, `gain_loss` |

**Income Tax** (`income_tax`):

| group | key |
|---|---|
| Block pool | `prescribed_rate`, `opening_wdv`, `additions_more_than_180`, `additions_less_than_180`, `asset_contribution`, `realized_from_sales`, `balance_before_depreciation` |
| Rate application | `full_pool`, `remaining_full_pool`, `remaining_half_pool`, `depreciation_full_rate`, `depreciation_half_rate`, `total_depreciation` |
| Closing | `closing_wdv`, `capital_gain_or_loss` |

**Acquisition costing** (frontend adapter):

| group | key |
|---|---|
| Price | `gross_basic_price`, `discount_amount`, `net_basic_price` |
| GST | `gst_rate`, `gst_split_basis`, `cgst_amount`, `sgst_amount`, `igst_amount`, `total_gst`, `recoverable_gst`, `capitalizable_gst` |
| Capitalized cost | `freight_cost`, `installation_cost`, `other_capitalizable_cost`, `landed_cost`, `total_acquisition_outlay`, `per_unit_cost` |

Steps are omitted when not applicable — no `wdv_rate` for SLM, no disposal group
outside a disposal year, no `per_unit_cost` at quantity 1.

## Architecture

```
engine -> intermediates -> builder -> CalcTrace -> (JSONB | response) -> CalculationDrawer
                                                        ^
                                    cost preview -> adapter (frontend)
```

Three producers:

**Depreciation, recorded.** Traces are built when a run is computed and persisted with
the line. A finalized FY2023 line explains itself with FY2023's inputs forever,
regardless of later edits to the asset.

**Depreciation, projected.** A dry-run endpoint calls the same engine with the same
input assembly and returns a trace without writing. A projection therefore cannot
disagree with what a run would produce.

**Acquisition costing.** No backend change. `CostPreviewResponse` already carries every
intermediate; a frontend adapter maps its fields to steps. Saved acquisitions share the
field names, so one adapter serves the live form preview and the stored acquisition.

The trace is a presentation artifact. Nothing reads it back to compute anything, so it
never becomes a second source of truth.

## Backend changes

### `app/services/calc_trace.py` (new)

`CalcStep` and `CalcTrace` dataclasses plus formatters (`fmt_money`, `fmt_pct`,
`fmt_days`) reusing the existing quantization from `asset_costing.money`. No domain
knowledge.

### Engines stay math-only

`AssetDepreciationResult` and `ItBlockDepreciationResult` each gain one field:

```python
intermediates: Mapping[str, Decimal | int | str | bool] = field(default_factory=dict)
```

Raw values, no formatting. Almost every value is already a local variable at the
return site, so this is a dict literal there. The two exceptions are `total_life_days`
and `consumed`, which live inside `_remaining_life_days`; that helper changes to return
them alongside the day count.

- `depreciation.py` (`calculate_asset_depreciation`): `depreciable_base`,
  `useful_years`, `wdv_rate` (WDV only), `carrying_for_calc`, `annual_dep`,
  `raw_annual`, `active_days`, `total_fy_days`, `max_dep_allowed`, `is_addition`,
  `nbv_at_disposal` (disposal only), `total_life_days`, `consumed`
- `it_depreciation.py` (`calculate_it_block_depreciation`): `rate_fraction`,
  `half_rate_fraction`, `total_pool`, `full_pool`, `remaining_full_pool`,
  `remaining_half_pool`, `branch` (`standard` | `stcg` | `stcl`)

`calculate_it_block_depreciation` has three return sites (STCG, STCL, standard); each
populates `intermediates` for its own branch.

### `app/services/calc_trace_builders.py` (new)

Turns `(input, result, intermediates)` into a `CalcTrace`. Two builders:
`build_schedule_ii_trace` and `build_it_block_trace`. All labels, formula strings,
statutory notes and formatting live here.

Keeping the builders out of the engines means statutory wording can be reworded
without touching computation, and the engine tests stay about numbers.

### Persistence

One Alembic migration adds a nullable `calc_trace` JSONB column to
`asset_depreciation_lines` and `it_block_depreciation_lines`.

Nullable is load-bearing: lines from runs computed before this feature have no trace,
and the drawer handles that explicitly rather than pretending.

`execute_depreciation_run` calls the relevant builder immediately after each engine
call (`depreciation_query.py:260` for Schedule II, `:377` for IT) and stores the
serialized trace on the line.

### API

`calc_trace` is added as an optional object to `AssetDepreciationLineResponse` and
`ItBlockDepreciationLineResponse`. The Depreciation tab's existing
`useAssetDepreciationLines` query therefore already carries the trace — a recorded run
needs no extra fetch.

New endpoint:

```
POST /api/v1/depreciation/explain
body:     { asset_id, financial_year_id }
returns:  { companies_act: CalcTrace, income_tax: CalcTrace | null }
```

Reader permission, no writes, `is_projection: true` on both traces. `income_tax` is
null when the asset has no IT block assigned.

The per-asset input assembly currently inline in `execute_depreciation_run` is
extracted into a function that both the run and this endpoint call, so a projection and
a run cannot diverge.

### The Income Tax book is block-wise

An asset's IT trace is its *block's* trace, with the asset's own contribution to
additions surfaced as the `asset_contribution` step. The drawer states this, rather
than implying the block figure belongs to the single asset.

## Frontend changes

### `frontend/src/components/calc/` (new)

**`CalculationDrawer.tsx`** — wraps the existing `Drawer` (`width="lg"`).
Props: `open`, `onClose`, `traces: CalcTrace[]`, `focusStep?`, `loading?`, `error?`.
With two traces it renders the existing `Tabs` (Companies Act / Income Tax) inside;
with one, no tabs. On open, scrolls `focusStep` into view and ring-highlights it
briefly. Knows nothing about assets or depreciation.

**`CalcStepRow.tsx`** — one step: label, `formula` in muted text, `substitution` in
`tabular-nums`, `result` right-aligned and semibold. `emphasis` steps get a stronger
background so the figure you clicked from is visibly the one you landed on. `note`
renders as a caption beneath.

**`ExplainLink.tsx`** — the trigger. Small ghost button, calculator icon plus
"See the calculation", sized for a `Card` header or beside a `DerivedRow` value.
Accepts `stepKey` for deep-linking.

**`traceFromCostPreview.ts`** — the acquisition adapter. Accepts the shared cost field
shape (`CostPreviewResponse` or a saved acquisition) and returns a `CalcTrace` with
groups `Price`, `GST`, `Capitalized cost`. Formats with `money()` from `assetFormat`.
Emits the blocked-ITC note when `itc_treatment` is blocked, and the per-unit allocation
step only when quantity > 1.

### Data

`useExplainDepreciation(assetId, fyId)` in `api/hooks/depreciation.ts`, `enabled` only
while the drawer is open so nothing fires on page load. Recorded traces arrive on the
existing line query; this hook serves only the projection path.

### `DerivedRow`

Gains one optional prop, `onExplain?: () => void`, rendering a bare icon button after
the value. This is the deep-link mechanism for derived rows — no new row component.

### Trigger placement

| Site | Trigger | Deep links |
|---|---|---|
| `DepreciationRunCard` | header `ExplainLink` | stat tiles -> `depreciation_for_year`, `closing_carrying_amount`, `opening_gross_block` |
| `DepreciationTab` Derived Parameters | header `ExplainLink` | `depreciable_base` row |
| `AcquisitionTab` cost build-up | header `ExplainLink` | `landed_cost` row |
| `TaxTab` GST card | header `ExplainLink` | `total_gst`, `capitalizable_gst` rows |

### One extraction

`DepreciationTab.tsx` is 532 lines and holds the run controls, reopen modal, FY
selector and four fieldsets. The "Depreciation Calculation & Schedule" card moves to
`tabs/DepreciationRunCard.tsx` — a self-contained unit with its own queries and
mutations, and where two of the triggers land. This takes the tab under 400 lines.

No other refactoring.

## Edge cases and error handling

**Runs computed before this feature** have `calc_trace = null`. The drawer states
"This run was recorded before calculation traces were kept" and offers a button to show
a projection from current inputs instead, badged as such. It never silently substitutes
one for the other.

**Projections are visually unmistakable:** dashed border, amber caption reading
"Projection from the asset's current inputs — not the recorded figure", no
`computed_at`, and a footer line "Recompute the run to record this."

**Incomplete inputs are informative, not a failure.** `explain` calls the same engine
and raises the same `DepreciationDataError` — "marked pre-cutover but carries neither
an opening WDV nor opening accumulated depreciation", "WDV requires a residual value
greater than zero". The endpoint returns 422 with that message and the drawer renders
it as an explanatory state. This surfaces validation that would otherwise fail
mid-run for the whole company.

**Draft vs finalized:** the drawer subtitle carries run status and `computed_at`, so a
draft trace is never mistaken for the filed figure.

**Stale traces:** a finalized trace keeps the inputs it was computed with, which may no
longer match the asset. The `basis` line states those inputs explicitly ("SLM,
60 months, residual 5%, cost 1,20,000.00") so a divergence is visible on its face.
Input-diffing is deliberately not built — showing what was used is sufficient, and
diffing invites arguments about which fields count.

**No IT block assigned:** `income_tax` is null, one tab, with a line explaining the
asset is not in a block yet.

**Long traces** scroll inside the drawer body. The footer holds Close and
"Copy calculation", which puts a plain-text rendering on the clipboard — the audience
for this feature is people answering an auditor's query.

## Testing

**Engines.** Extend existing tests to assert `intermediates` are internally consistent:
`depreciable_base == cost - residual`, `active_days <= total_fy_days`, `branch` matches
the returned STCG/STCL flags.

**Builders.** One case per branch: SLM full year, SLM part-year addition, WDV,
pre-cutover with a stated opening WDV, disposal year with a gain, disposal year with a
loss, IT standard, IT STCG, IT STCL.

**The invariant that matters.** For every builder case, each `emphasis` step's `result`
string equals the formatted value persisted on the corresponding line field. This is
what makes it structurally impossible for the drawer to contradict the number it
explains.

**Endpoint.** A projection's trace equals the recorded trace for the same asset and FY;
422 with the engine's message on incomplete input; tenant scoping enforced.

**Frontend.** `traceFromCostPreview` for intra-state, inter-state, manual override,
blocked ITC, and quantity > 1 (allocation steps sum to the total). `CalculationDrawer`
render tests for `focusStep` highlight, two-book tabs, projection banner, and the
null-trace fallback. An integration test in the style of `assets.test.tsx`: open the
drawer from the Depreciation tab and assert the step text.

## Decisions made and rejected

| Decision | Rejected alternative | Why |
|---|---|---|
| Backend trace for depreciation | Recompute the steps in TypeScript | Duplicating statutory math is how the panel ends up contradicting the figure above it; and a finalized run must explain itself with the inputs it used |
| Frontend adapter for costing | Backend trace for costing too | `CostPreviewResponse` already returns every intermediate, and there is no historical version to reconcile |
| Engines emit raw `intermediates`; builders add labels | Engines build labelled traces directly | Keeps statutory prose out of computation, and engine tests about numbers |
| Right-side drawer | Centred modal; inline expander | A trace is a tall ordered list; the drawer holds that shape and works identically from a card or a table row |
| One trigger per block, with step deep-linking | An icon on every derived number | Keeps pages clean while still letting high-traffic figures jump to the questioned line |
| Projection when no run exists | Empty state only | The engines are pure functions, so a dry run is cheap, and it makes the drawer useful during data entry |
| State the inputs a trace used | Diff trace inputs against current asset | Showing what was used answers the question; diffing invites disputes over which fields count |
