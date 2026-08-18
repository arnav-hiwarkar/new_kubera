# Reporting: AuditEase Final Reports + Asset Register Depreciation Reports

**Date:** 2026-08-18
**Branch:** `v2`
**Modules:** AuditEase (`/app/auditease`), Asset Register (`/app/assets`)
**Status:** Approved — ready for implementation plan

Builds statutory-grade reporting for both modules: a shared reporting layer that
renders one report structure to both Excel and PDF, a Schedule III statement set
for AuditEase, a two-book depreciation engine for the asset register, and the
report suite that engine makes possible.

---

## 1. Why

Neither module can currently produce a report a chartered accountant would sign.

**AuditEase** has correct, centralised accounting but almost no presentation.
`app/services/trial_balance.py::summarize()` aggregates only at the four top
levels (Assets / Liabilities / Income / Expenditure); there is no level-1 or
level-2 subtotalling, so a statement cannot show sums at the sub-group level.
The only renderer is a hand-concatenated f-string at
`app/routers/auditease.py:1342` (`_report_to_html`), archived to docVault as raw
HTML. The module's own design doc
(`2026-07-13-auditease-fixes-and-report-preview-design.md:218`) lists PDF/Excel
export as out of scope.

The favourable part: `app/services/ledger_groups.py::SCHEDULE_III_SEED` already
seeds the complete Schedule III sub-group tree. Grouped statements are therefore
a presentation change, not an accounting one.

**Asset Register** cannot report depreciation because depreciation is never
computed. `frontend/src/pages/company/assets/tabs/DepreciationTab.tsx:342` says
so directly: *"Period depreciation, accumulated depreciation, net book value and
closing tax WDV are produced by the depreciation engine once a financial year is
set up."* There is no engine, no financial-year entity anywhere in the codebase,
and no disposal implementation — `AssetLifecycleStatus.disposed` exists as an
enum value with no supporting fields or endpoint (`app/routers/assets.py:753`
marks it "P2"). The Excel export at `app/routers/assets.py:320` emits 12 of the
roughly 90 available columns, with no totals and no filter support.

**Shared gaps.** No PDF library exists in the repo.
`app/services/export_service.py::generate_xlsx` writes flat tables only — no
styling, number formats, or subtotal rows — and swallows formatter errors with a
bare `except: pass`. Backend money formatting is duplicated inline as
`f"{v:,.2f}"` in three places. The frontend hardcodes `en-US` digit grouping in
`frontend/src/lib/format.ts` despite the product being India-specific.

## 2. Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Depreciation engine | Build it, then build reports on it | Reports over uncomputed columns would be empty; the engine is the actual missing capability |
| PDF rendering | WeasyPrint, server-side | Reuses the HTML the module already generates; gives page headers/footers, page numbers and repeating table headers |
| Disposals | In scope | The IT block report needs a moneys-payable column and the Companies Act note needs a deletions row; both are standard |
| Delivery | Direct download **and** docVault archive | Matches the existing `saveBlob` pattern while keeping the encrypted, versioned archive |

## 3. Architecture

The organising principle: **build a report once as a neutral document structure,
render it twice.** Excel and PDF must never compute a total independently. This
is the same discipline `trial_balance.py` already enforces between the
trial-balance grid and the report — one implementation of every subtotal, so two
surfaces cannot disagree.

```
                 ┌─────────────────────┐
  data sources → │ *_reports.py        │ → ReportDocument ─┬→ workbook.py → .xlsx
  (services)     │ (builders)          │                   ├→ pdf.py      → .pdf
                 └─────────────────────┘                   └→ templates/  → .html (preview)
```

New package `app/services/reporting/`:

- **`document.py`** — the neutral model, pure dataclasses.
  `ReportDocument(title, subtitle, company, period, units, sections, meta,
  warnings)`; `ReportSection(title, columns, rows, subtotals, note_ref,
  children)` — sections nest, which is what produces sums at every level;
  `ReportRow(cells, style)`; `ReportTotal(label, cells, level)` where `level`
  drives bold weight and rule style; `ColumnSpec(header, key, kind, width,
  align)` with `kind ∈ text|money|number|date|percent`.
- **`workbook.py`** — a real openpyxl writer: title block, merged section
  headers, number formats (`#,##0.00`, and `#,##,##0.00` for Indian grouping),
  bold subtotal rows with a top border, grand totals with a double underline,
  freeze panes, auto column widths, multi-sheet workbooks, and a Cover sheet
  carrying company, period, generated-at and basis-of-preparation notes.
  `export_service.generate_xlsx` keeps working unchanged so the sales export is
  untouched; new code uses the builder.
- **`pdf.py`** — `HTML(string=...).write_pdf()` over a shared base stylesheet:
  `@page` A4 (portrait or landscape per report) with margins, a running header
  (company + report title + period), a footer with `page X of Y`, and
  `thead { display: table-header-group }` so column headers repeat across pages.
- **`templates/`** — Jinja2 templates rendering `ReportDocument` to HTML, so the
  on-screen preview and the PDF share exactly one source. Replaces the f-string
  in `auditease.py`.
- **`format.py`** — one backend money/date/percent formatter, replacing the
  inline `f"{v:,.2f}"` at `auditease.py:147,1345` and
  `trial_balance_query.py:200,210`. Carries a `units` parameter (absolute /
  thousands / lakhs / crores), since Schedule III requires rounding-off, and
  Indian digit grouping.
- **`vault.py`** — extracts the docVault persistence currently inlined at
  `auditease.py:1457-1521`, reusing `app/routers/docvault.py::handle_file_upload`
  rather than duplicating the KEK/DEK encryption path.

**Delivery.** Every report gets `GET .../export?format=xlsx|pdf` returning a blob
(the frontend uses the existing `frontend/src/lib/download.ts::saveBlob`) and
`POST .../archive` writing into the module's docVault bucket.

**Infrastructure.** Add `weasyprint` and `jinja2` to `pyproject.toml`. Add
`libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libgdk-pixbuf-2.0-0 libffi8
shared-mime-info fonts-dejavu-core fonts-noto-core` to the `Dockerfile` apt
layer — the ₹ glyph needs a font carrying U+20B9. The Python packages ship
wheels; the system libraries are the real deployment risk and are verified in
the container, not just locally.

**Frontend.** A shared `ReportExportMenu` component (Excel / PDF / Save to
docVault) and an `en-IN` formatter added to `frontend/src/lib/format.ts`
alongside the existing helpers.

## 4. AuditEase reports

**Accounting change.** Extend `app/services/trial_balance.py` with hierarchical
aggregation: `build_group_tree(figures, index) -> GroupNode`, producing subtotals
at every level of `LedgerGroup` (0 → 1 → 2) rather than only the top four.
`GroupSubtotal` already carries the right fields; this generalises which keys it
is computed for. `summarize()` keeps its current signature and behaviour, so the
trial-balance grid and the existing report are unaffected.

1. **Balance Sheet (Schedule III)** — Equity and Liabilities (Shareholders'
   funds → Share capital, Reserves & surplus; Share application money pending
   allotment; Non-current liabilities; Current liabilities) and Assets
   (Non-current → PPE, CWIP, Investment property, Goodwill, Other intangibles,
   Non-current investments, LT loans & advances, Other non-current assets;
   Current → Current investments, Inventories, Trade receivables, Cash & cash
   equivalents, ST loans & advances, Other current assets). Section subtotals,
   group totals, grand total, note references. Summary and detailed variants.
2. **Statement of Profit and Loss (Schedule III)** — Revenue from operations,
   Other income, **Total revenue**; the seven expense heads, **Total expenses**;
   **Profit before tax**; Profit for the period.
3. **Notes to Accounts** — one numbered note per Schedule III sub-group holding
   ledgers, listing each ledger with its final figure and the note subtotal.
4. **Trial Balance — detailed** — code, name, group path, opening, debit,
   credit, closing, adjustment, final; subtotals rolled up level-2 → level-1 →
   top → grand, with the Dr = Cr check.
5. **Trial Balance — summary** — one row per sub-group.
6. **Extended Trial Balance (working paper)** — Unadjusted Dr/Cr | Adjustment
   Dr/Cr | Adjusted Dr/Cr | Balance Sheet / P&L allocation.
7. **Adjusting Entries (audit journal)** — each approved entry with its lines,
   per-entry Dr = Cr proof, grand total; proposed and rejected as an annexure.
8. **Ledger Mapping report** — ledger → group path, with unmapped ledgers as
   exceptions.
9. **Exceptions & Diagnostics** — unmapped, sign-unresolved and
   source-row-inconsistent ledgers, balance difference, unapproved-entry count.
   Every value already exists on `TBSummary` and `view_warnings`.

**Outputs.** One Excel workbook with a sheet per report, and a PDF "Final Report
Pack" (Cover → Balance Sheet → P&L → Notes → Entries → Exceptions).

**Files.** `app/routers/auditease.py` (replace `_report_to_html`, add
export/archive endpoints), `app/services/trial_balance.py`, new
`app/services/reporting/auditease_reports.py`,
`frontend/src/pages/company/auditease/ReportsTab.tsx`.

## 5. Financial year, depreciation engine, disposals

**Financial year.** New `financial_years` table (`company_id`, `label` e.g.
"2025-26", `start_date`, `end_date`, `status` open|closed), unique per company,
defaulting to 1 Apr – 31 Mar but stored as explicit dates so a different period
is representable. A nullable `financial_year_id` is added to `audit_engagements`
so AuditEase reports can carry real dates; `period_label` stays for
back-compatibility.

**Disposals.** Add to `Asset`: `disposal_date`, `disposal_type`
(sold|scrapped|written_off|transferred), `sale_proceeds`, `disposal_reference`,
`disposal_note`, `disposed_by`. New `POST /assets/{id}/dispose`, with validation
in `app/services/asset_validation.py`: the asset must be capitalized, and the
disposal date must be on or after the capitalization date and inside an open
financial year.

**Persisted results.** Depreciation must be reproducible, and each year's closing
WDV is the next year's opening, so runs are stored rather than recomputed on
read:

- `depreciation_runs` — company_id, financial_year_id, book
  (companies_act|income_tax), status (draft|finalized), computed_at, computed_by
- `asset_depreciation_lines` — run_id, asset_id, opening_gross, additions,
  deletions, closing_gross, opening_accumulated, charge_for_year,
  dep_on_deletions, closing_accumulated, closing_nbv, rate_or_life_applied,
  days_held
- `it_block_depreciation_lines` — run_id, it_block_id, opening_wdv,
  additions_ge_180, additions_lt_180, deletions, dep_full_rate, dep_half_rate,
  total_depreciation, closing_wdv, stcg_us_50

**Engine — Companies Act, per asset** (`app/services/depreciation.py`, pure
Decimal, no DB, mirroring the `asset_costing.py` precedent):

- Depreciable base = `original_cost` − `residual_value`; never depreciate below
  residual value.
- SLM: pro-rata on days from `available_for_use_date` (or the FY start, whichever
  is later) to the FY end or `disposal_date`.
- WDV: Schedule II rate `r = 1 − (residual/cost)^(1/n)`, where `n` is the useful
  life in years (`useful_life_months / 12`), applied to the opening WDV pro-rata
  for days held.
- `is_pre_cutover` assets start from `opening_accumulated_depreciation` and
  `opening_wdv` instead of recomputing history that cannot be reconstructed.
- On disposal: charge to the disposal date, remove cost and accumulated
  depreciation, and compute profit or loss against `sale_proceeds`.
- Reuses `asset_costing.money()` for the single rounding rule and `_add_months`
  for calendar arithmetic.

**Engine — Income Tax, block-wise, sec 32** (`app/services/it_depreciation.py`):

- Opening WDV = the prior finalized run's closing WDV, or the sum of
  `opening_it_wdv` across pre-cutover assets in the first year.
- Additions split by `it_put_to_use_date`: if the asset was put to use 180 days or
  more before the FY end, it takes the full rate; otherwise half. Assets already
  in the block at the FY start always take the full rate.
- Deletions reduce the block by moneys payable, applied against opening plus
  full-rate additions first, then against half-rate additions.
- `dep_full = rate × max(0, opening + additions_ge_180 − deletions)`;
  `dep_half = (rate/2) × remaining additions_lt_180`.
- A block at nil or negative value attracts no depreciation; a negative block
  produces a short-term capital gain u/s 50. A block emptied of all assets
  produces STCG or STCL.
- Rates come from `ItAssetBlock.dep_rate`, already seeded in
  `app/services/asset_seed.py::IT_BLOCKS` and capped at 40%.

Both engines are pure modules with dedicated unit tests, following the
`test_trial_balance.py` / `test_asset_costing.py` pattern. A thin async layer
(`app/services/depreciation_query.py`) loads assets and persists run lines — the
same split as `trial_balance.py` / `trial_balance_query.py`.

**Frontend.** Financial-year management under asset masters, a "Run
depreciation" action, and `DepreciationTab.tsx` replacing its placeholder
footnote with real computed figures.

## 6. Asset register reports

Items 1–6 are core; 7–10 build on the same foundation and can be dropped without
affecting the rest.

1. **Fixed Asset Register (full Excel)** — every column, in labelled groups:
   Identity; Acquisition (supplier, invoice, quantity, price, discount, HSN, GST
   split, ITC treatment, recoverable vs capitalizable GST,
   freight/installation/other, landed cost, per-unit cost); Assignment; Dates;
   Companies Act inputs; Income Tax inputs; Cost and cutover; Depreciation
   (computed); Disposal; Status; Custom fields. Subtotals per category and a
   grand total. Respects the list filters rather than always dumping the whole
   register.
2. **Companies Act / Schedule II depreciation schedule** — Gross block (Opening |
   Additions | Deletions | Closing), Depreciation (Opening accumulated | For the
   year | On deletions | Closing accumulated), Net block (Closing | Previous
   year). Per asset, subtotalled per category and per Schedule II class, with a
   grand total. Doubles as the PPE note for the financial statements.
3. **Income Tax depreciation schedule (Appendix I, block-wise)** — Opening WDV |
   Additions ≥180d | Additions <180d | Deletions | Dep @ full rate | Dep @ half
   rate | Total depreciation | Closing WDV | STCG u/s 50. Subtotalled by
   `block_class` (Building / Furniture / Plant & Machinery / Intangible) and
   grand-totalled.
4. **Income Tax — asset-wise annexure** — the supporting detail behind each block.
5. **Additions register** — assets capitalized during the FY with supplier and
   invoice detail; subtotals by category and by month.
6. **Disposals register** — date, cost, accumulated depreciation, WDV, sale
   proceeds, profit or loss on sale; subtotalled.
7. **CWIP / not-yet-capitalized** — draft and ready assets with cost and ageing.
8. **Location / department / custodian summary** — count, gross block and NBV per
   dimension.
9. **Physical verification sheet (PDF)** — printable checklist by location with
   tick and condition columns.
10. **GST / ITC summary on asset purchases** — taxable value, CGST/SGST/IGST,
    recoverable vs capitalized, per acquisition.

**Files.** New `app/routers/asset_reports.py`,
`app/services/reporting/asset_reports.py`, and a new
`frontend/src/pages/company/assets/reports/` page with a financial-year selector,
report picker, preview and export.

## 7. Sequencing

Four phases, each separately shippable. Phase 1 unblocks 2 and 4; phase 3
unblocks 4. Recommended order **1 → 2 → 3 → 4**: phase 2 is the fastest visible
win because the data already exists, and phase 3 is the largest and most
correctness-sensitive.

| Phase | Delivers | Depends on |
|---|---|---|
| 1 — Reporting foundation | Document model, Excel writer, PDF renderer, delivery, formatting | — |
| 2 — AuditEase reports | Schedule III statements, notes, working papers | 1 |
| 3 — FY, engine, disposals | Financial years, both depreciation books, disposal | — |
| 4 — Asset register reports | Full register Excel plus both depreciation schedules | 1, 3 |

## 8. Verification

**Unit tests** (`unit_tests/`): Companies Act SLM and WDV including part-year,
pre-cutover, mid-year disposal and the never-below-residual floor; Income Tax
180-day split, deletions exceeding the block, negative block producing STCG, and
block extinguished; hierarchical group subtotals proving every level sums to its
parent.

**Backend tests** (`tests/`): each export endpoint returns the correct MIME type
and a non-empty body; the archive endpoint creates a docVault document; the
workbook opens via `openpyxl.load_workbook` with the expected sheets and subtotal
cells; the PDF begins with `%PDF`.

**Cross-checks**, asserted in tests rather than by eye: Balance Sheet total
assets equals total equity and liabilities; every section subtotal equals the sum
of its rows; P&L profit equals the `summarize()` net profit; IT closing WDV
equals opening + additions − deletions − depreciation for every block; Companies
Act closing NBV equals closing gross less closing accumulated.

**Docker**: rebuild and confirm WeasyPrint renders inside the container and that
₹ appears rather than a tofu box.

**Manual**: generate the full pack for a real engagement and a real register,
open both in Excel and a PDF viewer, and confirm repeating headers, page numbers
and subtotal placement.

## 9. Out of scope

- Schedule II component accounting (independent useful lives for components
  rolling up to a parent) — `parent_asset_id` stays informational, as documented
  at `app/models/assets.py:338`.
- Cash Flow Statement and the Statement of Changes in Equity.
- Tax computation beyond depreciation: no current/deferred tax, no MAT, no
  full ITR schedules.
- Revaluation, impairment, and asset transfers between blocks or categories.
- Comparative prior-year columns on the AuditEase statements — one engagement
  carries one period, and multi-period comparison needs its own design.
- Asynchronous generation. Reports are built synchronously and buffered in
  memory, consistent with every other file path in the repo; a large register
  may warrant a Celery task later.
- The dead `report_templates` table remains untouched.
