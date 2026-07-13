# AuditEase — Trial Balance / Entries Fixes + Report Preview

**Date:** 2026-07-13
**Branch:** `new_frontend`
**Module:** AuditEase
**Status:** Approved — ready for implementation plan

This spec covers four changes to the AuditEase module: two bug fixes, one small
UI addition, and one new feature (report preview). It is scoped as a single
implementation cycle.

---

## 1. Trial Balance crash — `readonly is not defined`

### Problem
Opening the Trial Balance view (auditor side, and any render of the interactive
company `TrialBalanceTable`) throws `readonly is not defined`.

`frontend/src/components/auditease/GroupMappingCell.tsx` declares `readonly?: boolean`
in its props type but destructures only `{ accountId, currentGroupId }`. Line ~77
(`if (readonly)`) then references an identifier that was never brought into scope,
throwing a `ReferenceError` on every render.

### Fix
Add `readonly` to the destructured props:
`function GroupMappingCell({ accountId, currentGroupId, readonly }: {...})`.

No other change. The shared `TrialBalanceTable` already supports both modes:
- Company TB tab / Mapping: interactive `<select>` dropdowns.
- Auditor TB tab: `readonly={true}` → renders the resolved group path as text.

This satisfies the requirement that the auditor and company see the *same* trial
balance view (same shared component), differing only in read/write affordance.

### Acceptance
- Auditor "Trial Balance" tab renders without error, showing ledgers grouped, with
  group mappings shown as read-only text paths.
- Company "Trial Balance" tab renders without error, with interactive group mapping.

---

## 2. "Unknown Ledger" in audit entries

### Problem
When viewing a specific audit entry, the auditor UI shows "Unknown Ledger" and the
company UI shows a blank ledger cell.

Root cause is a backend gap: `AuditEntryLineResponse`
(`app/schemas/auditease.py`) returns only `ledger_id`, `side`, `amount`, `id`,
`entry_id`. It never sends the ledger's name or code. The frontends read fields that
do not exist:
- Auditor (`AuditorEntriesTab.tsx`): `line.ledger?.ledger_name` (nested object).
- Company (`AuditEntriesTab.tsx`): `line.ledger_name` (flat field).

Neither shape is populated, so both fail.

### Fix

**Backend:**
- Add a relationship on `AuditEntryLine` → `TrialBalanceAccount` (e.g.
  `ledger = relationship("TrialBalanceAccount")`) in `app/models/auditease.py`.
- Add `ledger_name: str` and `ledger_code: Optional[str]` to
  `AuditEntryLineResponse` in `app/schemas/auditease.py`, populated from the
  relationship (via a computed/validator that reads `line.ledger`).
- Ensure every endpoint returning entries eager-loads the ledger, extending the
  existing `selectinload(AuditEntry.lines)` to also load
  `AuditEntryLine.ledger`. Affected endpoints:
  - `app/routers/auditease.py`: `list_entries`, `approve_reject_entry`.
  - `app/routers/auditor_engagements.py`: `create_entry`, `list_auditor_entries`.
- Regenerate the OpenAPI-derived `frontend/src/api/schema.d.ts` (or hand-extend if
  no codegen script exists — to be confirmed during planning).

**Frontend:**
- Standardize both entry tabs on the flat fields `line.ledger_name` and
  `line.ledger_code`. Remove the auditor's stale nested `line.ledger?.…` access.
- Update `frontend/src/api/types.ts` accordingly.

### Acceptance
- Auditor and company both see the correct ledger name (and code if present) on
  every debit/credit line of every audit entry.
- The name shown matches the ledger selected when the entry was created.

---

## 3. Report preview (new feature)

### Problem
`generate_report` (`app/routers/auditease.py`) builds one crude HTML table and dumps
it straight into docVault. There is no preview, and the accounting is minimal. The
company needs to preview the Balance Sheet, P&L, and a summary of audit entries
*before* generating, with all approved audit-entry adjustments applied.

### Design

**Shared compute helper (backend).**
Add `_compute_report(db, company_id, engagement)` that returns the structured report
data. Both the new preview endpoint and the existing `generate` endpoint call it, so
the math lives in exactly one place. `generate` renders the returned data to HTML for
docVault; no accounting logic is duplicated. No new dependencies (HTML only — no PDF
library is installed).

**Accounting model (linked, with balance check).**
Uses the existing sign convention already present in `generate_report`:
- Per ledger, from **approved** entries only:
  `adjustment = Σ(debit amounts) − Σ(credit amounts)`.
- `final = closing_balance + adjustment` for top group **Assets** or **Expenditure**;
  `final = closing_balance − adjustment` for **Liabilities** or **Income**.
- **P&L:** `Total Income − Total Expenditure = Net Profit/Loss`. Rendered as a short
  summary of income and expenditure ledgers grouped by top group.
- **Balance Sheet:** all Asset and Liability ledgers, grouped by their resolved
  sub-group path, with subtotals. Equity side = `Total Liabilities + Net Profit`.
- **Balance check:** compare `Total Assets` against `Total Liabilities + Net Profit`;
  report `difference` and a `balanced` boolean (within a small rounding epsilon).
- **Unmapped ledgers** are excluded from the statements; the response reports
  `unmapped_count` so the UI can warn the report is incomplete.
- **Entries summary:** list of approved entries (`code`, `description`, total amount,
  line count) plus `approved_count` and `proposed_count` (so the user knows any
  still-proposed adjustments are not yet reflected).

**New endpoint.**
`GET /api/v1/auditease/engagements/{id}/reports/preview` → JSON, roughly:

```jsonc
{
  "period_label": "FY2024",
  "lines": [
    {
      "ledger_id": "…", "ledger_name": "Cash", "ledger_code": "1001",
      "top_group": "Assets",            // Assets | Liabilities | Income | Expenditure | null
      "group_path": ["Assets", "Current Assets", "Cash"],
      "closing": 1000.0, "adjustment": 50.0, "final": 1050.0
    }
  ],
  "totals": { "assets": 0, "liabilities": 0, "income": 0, "expenditure": 0 },
  "net_profit": 0,
  "balance_check": { "assets": 0, "liabilities_plus_equity": 0, "difference": 0, "balanced": true },
  "entries": {
    "approved": [{ "code": "AJE-01", "description": "…", "total": 50.0, "line_count": 2 }],
    "approved_count": 1,
    "proposed_count": 0
  },
  "unmapped_count": 0
}
```

New Pydantic response schemas for the above are added to `app/schemas/auditease.py`.

**`generate` endpoint.**
Refactored to call `_compute_report` and render the same Balance Sheet + P&L +
entries summary as HTML, persisted to the "Final Reports" docVault bucket (unchanged
storage/encryption flow).

**Frontend `ReportsTab.tsx`.**
Fetches the preview via a new hook and renders:
- Balance Sheet table (Assets and Liabilities, grouped, with subtotals and totals).
- P&L table (Income, Expenditure, Net Profit).
- Balance-check badge (balanced / unbalanced + difference).
- Unmapped-ledgers warning when `unmapped_count > 0`.
- Entries summary (approved entries; note of any still-proposed).
- "Generate New Report" button (persists HTML to docVault, as today).

All tables use existing UI primitives and design tokens (theme-aware).

**API client + types.**
- `frontend/src/api/endpoints/auditease.ts`: add `previewReport(engagementId)`.
- `frontend/src/api/hooks/auditease.ts`: add `usePreviewReport(engagementId)`.
- `frontend/src/api/types.ts`: add the report preview types.

### Acceptance
- Reports tab shows a live preview (Balance Sheet, P&L, entries summary) before
  anything is generated.
- Approved audit-entry adjustments are reflected in each ledger's `final` value and
  in all totals.
- Balance Sheet shows all asset & liability ledgers; P&L is a short income/expenditure
  summary with a net profit/loss figure.
- Balance check and unmapped warning are visible.
- "Generate" saves an HTML report to docVault whose content matches the preview.

---

## 4. Mapping progress status bar

### Design
In `frontend/src/pages/company/auditease/MappingTab.tsx`, add a thin progress bar near
the "Ledgers (N)" header. It fills to `mapped / total`, where `mapped` is the count of
loaded accounts with a non-null `mapped_group_id`. Derived entirely from already-loaded
data; no new API call. Show the numeric ratio / percent alongside the bar.

### Acceptance
- The bar reflects the current mapped fraction and updates as ledgers are mapped or
  unmapped.
- At 0 ledgers the bar is empty/neutral (no divide-by-zero).

---

## Files touched

**Backend**
- `app/models/auditease.py` — `AuditEntryLine.ledger` relationship.
- `app/schemas/auditease.py` — enrich `AuditEntryLineResponse`; add report preview schemas.
- `app/routers/auditease.py` — enrich entry loaders; `_compute_report` helper; preview
  endpoint; refactor `generate_report`.
- `app/routers/auditor_engagements.py` — eager-load ledger on entry endpoints.

**Frontend**
- `frontend/src/components/auditease/GroupMappingCell.tsx` — destructure `readonly`.
- `frontend/src/pages/auditor/AuditorEntriesTab.tsx` — flat ledger fields.
- `frontend/src/pages/company/auditease/AuditEntriesTab.tsx` — flat ledger fields.
- `frontend/src/pages/company/auditease/ReportsTab.tsx` — preview UI.
- `frontend/src/pages/company/auditease/MappingTab.tsx` — progress bar.
- `frontend/src/api/endpoints/auditease.ts` — `previewReport`.
- `frontend/src/api/hooks/auditease.ts` — `usePreviewReport`.
- `frontend/src/api/types.ts` — report preview + enriched entry line types.
- `frontend/src/api/schema.d.ts` — regenerated (or hand-extended) OpenAPI types.

## Out of scope
- PDF/Excel export of reports (HTML-to-docVault only for this cycle).
- Any change to how audit entries are created or approved.
- KRA and other modules (separate cycle).
