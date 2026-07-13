# Implementation Plan — Assets + Custom Fields

**Spec:** `docs/superpowers/specs/2026-07-14-assets-and-custom-fields-design.md`
**Date:** 2026-07-14
**Branch:** `new_frontend`

Ordered so the backend contract is complete before the frontend consumes it.
Backend on `:8000` (uvicorn `--reload`), Vite on `:5173`. Run pytest via the local
`.venv` (Python 3.12) with `VAULT_STORAGE_PATH` pointed at a writable dir.
`purchase_date` importability (spec §1c) is already done and committed.

---

## Phase A — Backend additions

### A1. Asset import inspect endpoint
**Files:** `app/schemas/assets.py`, `app/routers/assets.py`
- Add response schemas to `schemas/assets.py`:
  ```python
  class AssetSheetInfo(BaseModel):
      name: str
      headers: List[str]
      preview_rows: List[List[Any]]
  class AssetImportInspectResponse(BaseModel):
      sheets: List[AssetSheetInfo]
  ```
- Add endpoint to `routers/assets.py` (admin only), mirroring the TB inspect:
  ```python
  @router.post("/import/inspect", response_model=AssetImportInspectResponse)
  async def inspect_asset_import(file: UploadFile = File(...),
      current_user: CompanyUser = Depends(require_admin), ...):
      content = await file.read()
      from app.services.import_service import inspect_spreadsheet
      return {"sheets": inspect_spreadsheet(file.filename, content)}
  ```
  Wrap unsupported-format `ValueError` into `HTTPException(400)`.
- **Note:** register this route BEFORE `@router.get("/{asset_id}")`? Not needed —
  it's a POST and the path is static (`/import/inspect`), no collision with the
  GET `/{asset_id}`. Keep it next to the existing `/import` route.

### A2. `include_inactive` on custom-field list
**File:** `app/routers/custom_fields.py`
- Add `include_inactive: bool = False` query param to `list_custom_fields`; only
  apply the `is_active == True` filter when it is false. Ordering unchanged.

### A3. Verify Phase A
- `pytest` (new tests land in Phase F, but do a smoke check now):
  `curl` the inspect endpoint with a small CSV (admin token) → sheets/headers.
  `GET /custom-fields/asset_management?include_inactive=true` after deactivating a
  field shows it.

---

## Phase B — Frontend API layer

### B1. Regenerate OpenAPI types
- Backend running → `cd frontend && npm run gen:api` (updates `schema.d.ts` with
  `AssetImportInspectResponse` + the `include_inactive` param).

### B2. Endpoint clients
- `api/endpoints/customFields.ts`: change `list` to
  `list: (module, includeInactive = false) => companyClient.get(..., { query: { include_inactive: includeInactive } })`.
  (`reactivate` already exists.)
- `api/endpoints/assets.ts`: add
  `inspectImport: (formData: FormData) => companyClient.post<AssetImportInspectResponse>('/api/v1/assets/import/inspect', { formData })`.
  (`list/get/create/update/import/exportExcel` already exist.)

### B3. types.ts
- Add `export type AssetImportInspectResponse = S['AssetImportInspectResponse']`
  and `AssetSheetInfo` if needed by the modal.

### B4. Hooks
- `api/hooks/customFields.ts` (new): `useCustomFields(module, includeInactive)`,
  `useCreateCustomField`, `useUpdateCustomField`, `useDeactivateCustomField`,
  `useReactivateCustomField`. Query key `['custom-fields', module, includeInactive]`;
  mutations invalidate `['custom-fields', module]` (prefix).
- `api/hooks/assets.ts` (new): `useAssets(filters)` (key `['assets','list',filters]`),
  `useCreateAsset`, `useUpdateAsset`, `useInspectAssetImport` (mutation),
  `useImportAssets` (mutation). Mutations invalidate `['assets']`. Export is a
  direct `assetsApi.exportExcel()` + `saveBlob` call in the page (no cache).

### B5. Verify
- `npx tsc -b` clean.

---

## Phase C — Custom Fields screen (admin-only)

**File:** `pages/company/customfields/CustomFieldsPage.tsx` (new)
- Guard: `useCompanyAuth().profile.role`; non-admin → admin-only notice (UsersDirectory pattern).
- Module tabs: `asset_management` / `sales_tracking` (labels "Assets" / "Sales"),
  same tab-bar styling as KRA/AuditEase.
- `useCustomFields(module, true)` → table (DataTable or simple table): name, key,
  type, required (✓/—), options (joined), status badge (active/inactive). Inactive
  rows muted.
- **New Field** (`Modal` + `footer`): `field_name`, `field_key` (auto-slug from
  name via a `slugify` helper — lowercase, non-alnum→`_`; editable), `field_type`
  (`Select` over `CUSTOM_FIELD_TYPE`), `is_required` (checkbox), `dropdown_options`
  (a `Textarea`, one option per line; only shown when type=dropdown → send as
  string[]), `display_order` (number). Submit → `useCreateCustomField`; `409` →
  inline "key already exists".
- **Edit** (`Modal`): only `field_name`, `is_required`, `dropdown_options`,
  `display_order` editable; key + type shown read-only. Submit → `useUpdateCustomField`.
- **Deactivate / Reactivate** row buttons → respective hooks; confirm on deactivate.
- Verify: create text + dropdown fields, deactivate one (row shows inactive),
  reactivate it.

---

## Phase D — Assets screen

**File:** `pages/company/assets/AssetsPage.tsx` (new)
- `const isAdmin = profile.role === 'admin'`.
- `useAssets({ category, status })` (filter `Select`s bound to state).
- Custodian names: admins `useQuery(['users'], usersApi.list)`; build id→name map.
  Non-admins skip that query and render own name when `custodian_id === profile.id`
  else "Unassigned".
- `DataTable` columns: Asset Name (+ serial subtext), Category (`StatusBadge`),
  Status (`StatusBadge`), Purchase Cost (`formatMoney`), Custodian. Row click →
  `AssetDrawer`.
- Header actions (admin only): New Asset (opens drawer create), Import (opens
  `ImportAssetsModal`), Export (`assetsApi.exportExcel()` → `saveBlob(blob, 'assets.xlsx')`).

### D1. Asset drawer — `pages/company/assets/AssetDrawer.tsx` (new)
- Props: `{ open, onClose, asset: AssetResponse | null, isAdmin, users, activeFields }`.
  `asset === null` → create; non-admin → read-only view.
- Base fields: asset_name (req), serial_number, category (req Select over
  `ASSET_CATEGORY`), status (Select over `ASSET_STATUS`), purchase_date (date
  input), purchase_cost (number), depreciation_rate (number).
- Custodian: `Select` over `users` (id→name); "Unassigned" option.
- Document link: optional `Select` over `useQuery(['docvault','documents'],
  docvaultApi.listDocuments)` titles → `document_id`.
- Custom fields: iterate `activeFields` (from `useCustomFields('asset_management',
  false)`), render by `field_type` (text/number→Input, date→date Input,
  dropdown→Select of options); track values in a `custom_fields` state object.
- Submit (admin): assemble `AssetCreate`/`AssetUpdate` incl. `custom_fields`.
  Client-side check required custom fields present; on backend `400` with
  `detail.custom_field_errors`, surface the messages (toast + inline). Uses
  `useCreateAsset`/`useUpdateAsset`.
- Read-only view (non-admin): render the same fields as static rows.

### D2. Import modal — `pages/company/assets/ImportAssetsModal.tsx` (new)
Reference: `ImportTrialBalanceModal.tsx`. Steps:
1. File input (`.csv,.xlsx`); keep `File` in state.
2. On file chosen → `useInspectAssetImport` with FormData(file) → sheets. Show
   the first sheet's headers + a few preview rows (single sheet for CSV).
3. Mapping table: rows = importable targets
   [`asset_name`*, `category`*, `serial_number`, `status`, `purchase_date`,
   `purchase_cost`] + each active custom-field key (label = field_name); each maps
   to a source-column `Select` (or "— skip —"). Disable Import until `asset_name`
   and `category` are mapped.
4. Import: `useImportAssets` with FormData(file, mappings=JSON of
   `[{source_column, target_field}]` for mapped rows) → render `ImportResult`
   (imported/skipped + per-row error list). On success invalidate assets list.
- Verify: import a small CSV incl. a purchase_date column; confirm counts + a
  bad-date row reported.

---

## Phase E — Routing
**File:** `frontend/src/routes/company.routes.tsx`
- Import `AssetsPage`, `CustomFieldsPage`; replace the `/app/assets` and
  `/app/custom-fields` `ModulePlaceholder` elements with the real pages.
- Sidebar already links both paths — no nav change.

---

## Phase F — Tests

### F1. Backend
- `tests/test_custom_fields.py` (new): create → list (active only) → deactivate →
  list hides it → `include_inactive=true` shows it → reactivate; `update` changes
  name/required/options/order; duplicate key `409`; two modules isolated;
  non-admin create → `403`.
- `tests/test_assets.py` (new): admin create + get/list; custom-field validation
  (define a required dropdown field, create asset missing it → `400`
  `custom_field_errors`); `import/inspect` returns headers; `import` with a mapping
  covering base + `purchase_date` + a custom field (assert imported count, parsed
  date on the row, and a bad-date row skipped with an error); `export/excel`
  returns the spreadsheet content-type; non-admin create → `403`; non-admin list
  scoped (asset with another custodian not visible).
- Run: `pytest tests/test_custom_fields.py tests/test_assets.py` then full suite.

### F2. Frontend
- `pages/company/customfields/customfields.test.tsx`: mock `customFieldsApi` +
  `useCompanyAuth` (admin); renders an active and an inactive field; New Field
  create calls `create`; deactivate/reactivate call their APIs. (Use
  `vi.mocked(...)`, not leading-semicolon casts — `no-extra-semi`.)
- `pages/company/assets/assets.test.tsx`: admin profile → New/Import/Export
  visible, drawer renders a custom field input; non-admin profile → no action
  buttons, read-only drawer. Mock `assetsApi`, `usersApi`, `customFieldsApi`.
- Run: `npm run test`.

---

## Phase G — Full verification
- `cd frontend && npm run build && npm run test && npm run lint` (0 errors; only
  the pre-existing 6 react-refresh warnings remain).
- Backend `pytest` green.
- Live end-to-end (script against `:8000`, unique emails): admin defines a custom
  field → creates an asset with it → imports a CSV (with purchase_date) → exports
  → deactivates/reactivates the field; a non-admin custodian sees only their own
  asset and cannot create (`403`).

## Rollout notes
- No DB migration. Two additive backend endpoints/params + the already-shipped
  `purchase_date` importer change.
- No new frontend dependencies (file headers come from the inspect endpoint).
