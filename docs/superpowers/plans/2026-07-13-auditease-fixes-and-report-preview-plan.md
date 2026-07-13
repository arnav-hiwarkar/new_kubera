# Implementation Plan — AuditEase Fixes + Report Preview

**Spec:** `docs/superpowers/specs/2026-07-13-auditease-fixes-and-report-preview-design.md`
**Date:** 2026-07-13
**Branch:** `new_frontend`

Steps are ordered so backend contract changes land before the frontend consumes
them. Each step lists exact files, the change, and how to verify it. Backend
(FastAPI) runs on `:8000`; frontend (Vite) on `:5173`.

---

## Phase A — Backend: enrich audit entry lines with ledger name/code (Fix 2)

### A1. Add `ledger` relationship on `AuditEntryLine`
**File:** `app/models/auditease.py`
- On `AuditEntryLine`, add:
  ```python
  ledger = relationship("TrialBalanceAccount", lazy="raise")
  ```
  (`lazy="raise"` so an unloaded access is a loud error, not a lazy IO in async
  context — every read path below eager-loads it.)
- `TrialBalanceAccount` is defined earlier in the same module, so the string
  reference resolves. No back-ref needed.

### A2. Add ledger fields to `AuditEntryLineResponse`
**File:** `app/schemas/auditease.py`
- Extend `AuditEntryLineResponse`:
  ```python
  class AuditEntryLineResponse(AuditEntryLineBase):
      id: uuid.UUID
      entry_id: uuid.UUID
      ledger_name: str
      ledger_code: Optional[str] = None
      model_config = {"from_attributes": True}

      @model_validator(mode="before")
      @classmethod
      def _pull_ledger(cls, data):
          # data is an ORM AuditEntryLine; surface ledger name/code as flat fields.
          led = getattr(data, "ledger", None)
          if led is not None:
              # build a dict so from_attributes still works for the rest
              ...
  ```
  Prefer the simplest approach that works with `from_attributes=True`: add two
  computed fields via a `@computed_field`/property on a thin wrapper, OR (cleaner)
  populate flat attributes on the ORM instance right before serialization in the
  routers. **Chosen approach:** set `line.ledger_name` / `line.ledger_code` are not
  ORM columns, so instead expose them through Pydantic using `@property` on a
  from-attributes model. Concretely: keep `AuditEntryLineResponse` with
  `ledger_name`/`ledger_code` fields and a `model_validator(mode="before")` that
  accepts the ORM object and reads `obj.ledger.ledger_name` / `obj.ledger.ledger_code`.
- Guard for a missing ledger (should not happen — FK is non-null — but avoid a hard
  crash): fall back to `ledger_name="(deleted ledger)"`, `ledger_code=None`.

### A3. Eager-load the ledger everywhere entries are returned
Extend the existing `selectinload(AuditEntry.lines)` to also load the line's ledger.
Pattern:
```python
from sqlalchemy.orm import selectinload
.options(selectinload(AuditEntry.lines).selectinload(AuditEntryLine.ledger))
```
**Files / functions:**
- `app/routers/auditease.py`: `list_entries`, `approve_reject_entry` (the `refresh`
  path — after `db.refresh(entry)` re-select with the nested loader, or load before
  returning).
- `app/routers/auditor_engagements.py`: `create_entry` (the final re-select at the
  end), `list_auditor_entries`.
- Import `AuditEntryLine` where needed.

### A4. Verify Phase A
- Start backend. With an engagement that has ≥1 proposed entry, call:
  - `GET /api/v1/auditor/engagements/{id}/entries` (auditor token)
  - `GET /api/v1/auditease/engagements/{id}/entries` (company token)
  Confirm each `lines[]` element now includes `ledger_name` (and `ledger_code`).
- `pytest tests/test_auditease.py` still passes (update assertions if any check the
  line shape).

---

## Phase B — Backend: report compute helper, preview endpoint, generate refactor (Feature 3)

### B1. Report response schemas
**File:** `app/schemas/auditease.py` — add:
```python
class ReportLine(BaseModel):
    ledger_id: uuid.UUID
    ledger_name: str
    ledger_code: Optional[str] = None
    top_group: Optional[str] = None          # Assets|Liabilities|Income|Expenditure|None
    group_path: Optional[List[str]] = None
    closing: float
    adjustment: float
    final: float

class ReportTotals(BaseModel):
    assets: float; liabilities: float; income: float; expenditure: float

class ReportBalanceCheck(BaseModel):
    assets: float; liabilities_plus_equity: float; difference: float; balanced: bool

class ReportEntrySummary(BaseModel):
    code: Optional[str]; description: str; total: float; line_count: int

class ReportEntriesBlock(BaseModel):
    approved: List[ReportEntrySummary]
    approved_count: int
    proposed_count: int

class ReportPreviewResponse(BaseModel):
    period_label: str
    lines: List[ReportLine]
    totals: ReportTotals
    net_profit: float
    balance_check: ReportBalanceCheck
    entries: ReportEntriesBlock
    unmapped_count: int
```

### B2. `_compute_report` helper
**File:** `app/routers/auditease.py` — add an async helper that both endpoints call.
Signature: `async def _compute_report(db, company_id, engagement) -> ReportPreviewResponse`.
Logic:
1. Load all `TrialBalanceAccount` for the engagement.
2. `path_map = await lg.resolve_group_paths(db, company_id)`; for each account,
   `group_path = path_map.get(mapped_group_id)`, `top_group = group_path[0] if group_path else None`.
3. Load **approved** entries with lines eager-loaded; build
   `adjustments[ledger_id] = Σdebit − Σcredit`.
4. Per account: `adj = adjustments.get(id, 0.0)`;
   `final = closing + adj if top_group in ("Assets","Expenditure") else closing − adj`.
   (Unmapped `top_group=None` → treat `final = closing`, but exclude from totals.)
5. Totals: sum `final` by `top_group` for the four groups (skip `None`).
6. `net_profit = income − expenditure`.
7. `balance_check`: `assets` vs `liabilities + net_profit`;
   `difference = assets − (liabilities + net_profit)`;
   `balanced = abs(difference) < 0.01`.
8. `entries`: approved summaries (total = Σ debit amounts per entry), `approved_count`,
   and a separate count of `proposed` entries.
9. `unmapped_count = number of accounts with top_group is None`.
Return the populated `ReportPreviewResponse`.

Keep floats rounded to 2 dp on the way out.

### B3. Preview endpoint
**File:** `app/routers/auditease.py`
```python
@router.get("/engagements/{engagement_id}/reports/preview", response_model=ReportPreviewResponse)
async def preview_report(engagement_id, current_user, db):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    return await _compute_report(db, current_user.company_id, eng)
```

### B4. Refactor `generate_report` to reuse the helper
**File:** `app/routers/auditease.py`
- Replace the inline account/adjustment/HTML logic with a call to `_compute_report`,
  then render its data to HTML: a Balance Sheet section (Assets & Liabilities grouped
  by `group_path`, subtotals, total), a P&L section (Income, Expenditure, Net Profit),
  a balance-check line, and an approved-entries summary table.
- Keep the existing docVault persistence block (bucket lookup, encryption, version)
  exactly as-is — only the `html` string construction changes.

### B5. Verify Phase B
- `GET /api/v1/auditease/engagements/{id}/reports/preview` returns the JSON with
  correct totals. Manually check on an engagement where you know the numbers:
  income/expenditure/net_profit, and that an approved entry shifts a ledger's `final`.
- `POST …/reports/generate` still returns `{id, url}` and the saved HTML now contains
  Balance Sheet + P&L + entries summary.
- `pytest tests/test_auditease.py` passes.

---

## Phase C — Frontend API layer (regenerate types + clients/hooks)

### C1. Regenerate OpenAPI types
- With the backend running: `cd frontend && npm run gen:api`
  (regenerates `src/api/schema.d.ts` from `http://localhost:8000/openapi.json`).
- If the backend can't be reached during this work, hand-extend
  `AuditEntryLineResponse` and add the report schemas in `schema.d.ts` to match B1/A2.

### C2. `types.ts` exports
**File:** `frontend/src/api/types.ts`
- Confirm `AuditEntryResponse` now carries `ledger_name`/`ledger_code` on lines
  (via the regenerated schema).
- Add `export type ReportPreviewResponse = S['ReportPreviewResponse']` (and any nested
  types the tab needs).

### C3. Endpoint + hook
- `frontend/src/api/endpoints/auditease.ts`: add
  `previewReport: (id) => companyClient.get<ReportPreviewResponse>('/api/v1/auditease/engagements/'+id+'/reports/preview')`.
- `frontend/src/api/hooks/auditease.ts`: add
  `usePreviewReport(engagementId)` — `useQuery`, key `['auditease','report-preview',id]`,
  `enabled: !!id`. Invalidate this key inside `useApproveRejectEntry`'s `onSuccess`
  (approving an entry changes the preview).

### C4. Verify Phase C
- `npm run build` (tsc) passes with no type errors.

---

## Phase D — Frontend fixes + UI

### D1. Fix 1 — `readonly` crash
**File:** `frontend/src/components/auditease/GroupMappingCell.tsx`
- Change destructure to `{ accountId, currentGroupId, readonly }`.
- **Verify:** auditor "Trial Balance" tab renders read-only paths; company TB tab
  renders interactive selects. No console error.

### D2. Fix 2 — entry tabs use flat ledger fields
- `frontend/src/pages/auditor/AuditorEntriesTab.tsx`: replace
  `l.ledger?.ledger_name || 'Unknown Ledger'` with
  `l.ledger_code ? \`\${l.ledger_code} — \${l.ledger_name}\` : l.ledger_name`
  (both debit & credit lists).
- `frontend/src/pages/company/auditease/AuditEntriesTab.tsx`: line already reads
  `line.ledger_name`; optionally prefix with code for consistency. Confirm it renders.
- **Verify:** both sides show real ledger names on every entry line.

### D3. Feature 3 — Reports tab preview
**File:** `frontend/src/pages/company/auditease/ReportsTab.tsx`
- Use `usePreviewReport(engagementId)`.
- Split `preview.lines` by `top_group`:
  - Balance Sheet: Assets + Liabilities, grouped by `group_path` (join with ` › `),
    subtotals per group, and section totals. Render as a bordered table matching
    `TrialBalanceTable` styling (design tokens, `formatMoney`, `tabular-nums`).
  - P&L: Income and Expenditure lines/totals + a **Net Profit/Loss** row.
- Balance-check badge: `StatusBadge`-style pill, green when `balanced`, red otherwise,
  showing the `difference`.
- Unmapped warning banner when `unmapped_count > 0`
  ("N ledgers are unmapped and excluded from these statements").
- Entries summary: table of `entries.approved` (code, description, total, line count);
  a note when `entries.proposed_count > 0` ("N proposed entries are not yet reflected").
- Keep the "Generate New Report" button + existing success toast; on success also
  note it's saved to the Final Reports docVault bucket.
- Loading (`Spinner`) and empty (no TB imported → `EmptyState`) states.
- **Verify:** preview matches the backend JSON; approving an entry (company Entries
  tab) then returning to Reports shows updated numbers.

### D4. Mapping progress bar
**File:** `frontend/src/pages/company/auditease/MappingTab.tsx`
- Compute `mapped = accounts.filter(a => a.mapped_group_id).length`, `total = accounts.length`,
  `pct = total ? Math.round(mapped/total*100) : 0`.
- Render near the "Ledgers (N)" header: a thin track (`bg-bg-raised`, rounded) with a
  filled `bg-accent` bar at `width: pct%`, and a label `mapped/total (pct%)`.
- Guard `total === 0` (empty bar, no NaN).
- **Verify:** bar fills as ledgers are mapped/unmapped in real time.

---

## Phase E — Full verification
- `cd frontend && npm run build && npm run test && npm run lint`.
- `pytest` (backend) green.
- Manual end-to-end in the running app:
  1. Company: import TB → map some ledgers (watch the progress bar) → leave some
     unmapped.
  2. Invite/accept auditor → auditor opens TB (no crash, read-only) → proposes an entry
     (ledger names visible) → company sees entry with ledger names → approves it.
  3. Company Reports tab: preview shows Balance Sheet, P&L with net profit, balance-check
     badge, unmapped warning, approved-entry summary reflecting the adjustment.
  4. Generate → HTML saved to docVault matches the preview.

## Rollout notes
- No DB migration required — `AuditEntryLine.ledger` is a relationship over an existing
  FK column; the new schemas are response-only.
- No new dependencies.
