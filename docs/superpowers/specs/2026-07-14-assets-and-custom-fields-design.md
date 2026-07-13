# Assets + Custom Fields Modules

**Date:** 2026-07-14
**Branch:** `new_frontend`
**Modules:** Assets (`/app/assets`), Custom Fields (`/app/custom-fields`)
**Status:** Approved — ready for implementation plan

Builds the frontend for the Assets register and the Custom Fields admin screen it
depends on, against the already-built backend. Two small backend additions are
included (an asset-import inspect endpoint and an `include_inactive` list param);
everything else is frontend.

---

## 1. Backend additions

### 1a. Asset import inspect endpoint
`POST /api/v1/assets/import/inspect` (admin only). Accepts the uploaded file
(multipart), reuses the existing `import_service.inspect_spreadsheet(filename,
content)` helper, and returns the sheets with their headers and preview rows:

```jsonc
{ "sheets": [ { "name": "Sheet1", "headers": ["Name","Serial",...], "preview_rows": [["Laptop","SN1",...]] } ] }
```

A response schema (e.g. `AssetImportInspectResponse` with a nested sheet model, or
reuse of the TB `TBInspectResponse` shape) is added to `app/schemas/assets.py`.
No parsing logic is added — only the endpoint wrapper.

### 1b. `include_inactive` on custom-field list
`GET /api/v1/custom-fields/{module}?include_inactive=false` (default false keeps
current behaviour). When `true`, the `is_active == True` filter is dropped so the
admin screen can show deactivated fields and reactivate them. Ordering by
`display_order` is unchanged.

No other backend changes. No DB migration.

---

## 2. Custom Fields screen (`/app/custom-fields`, admin-only)

`CustomFieldsPage.tsx`. If a non-admin reaches it, render an admin-only notice
(the same 403 pattern used by `UsersDirectory`).

- **Module switcher** — tabs **Assets** (`asset_management`) / **Sales**
  (`sales_tracking`). Sales fields are definable now even though the Sales page is
  a later slice.
- **List** — fetched with `include_inactive=true`, ordered by `display_order`.
  Columns: field name, key, type, required, dropdown options (if any), and an
  active/inactive `StatusBadge`. Inactive rows are visually muted.
- **New Field modal** — `field_name`; `field_key` auto-slugged from the name
  (lowercase, underscores) but editable; `field_type` (text/number/date/dropdown);
  `is_required`; `dropdown_options` (a line/comma editor, shown only when
  type=dropdown); `display_order` (number). On `409` (duplicate key for the
  module) show an inline error.
- **Edit modal** — only the fields the backend `CustomFieldUpdate` accepts:
  `field_name`, `is_required`, `dropdown_options`, `display_order`. `field_key`
  and `field_type` are immutable and shown read-only.
- **Deactivate / Reactivate** — per-row action calling the respective endpoint.

Hooks (`api/hooks/customFields.ts`): `useCustomFields(module, includeInactive)`,
`useCreateCustomField`, `useUpdateCustomField`, `useDeactivateCustomField`,
`useReactivateCustomField`. Mutations invalidate the module's list.
`api/endpoints/customFields.ts` gains the `include_inactive` query param and a
`reactivate` call (verify existing shape during implementation).

---

## 3. Assets screen (`/app/assets`)

`AssetsPage.tsx`. Visible to all authenticated company users; the backend scopes
the list for non-admins to assets they are custodian of (or unassigned).

- **Table** (`DataTable`) — base columns: Asset Name (with serial number as
  subtext), Category (`StatusBadge`), Status (`StatusBadge`), Purchase Cost
  (`formatMoney`), Custodian. Custom-field values are shown in the drawer, not the
  table, to keep width manageable.
- **Filters** — Category and Status dropdowns mapped to the backend `category` /
  `status` query params.
- **Admin actions** — New Asset / Import / Export buttons render only when
  `profile.role === 'admin'`. Non-admins get the list plus a read-only drawer.
- **Custodian names** — admins resolve names via `usersApi.list()`; non-admins
  (who cannot list users) show their own name when `custodian_id === profile.id`,
  otherwise "Unassigned".

Hooks (`api/hooks/assets.ts`): `useAssets(filters)`, `useCreateAsset`,
`useUpdateAsset`, `useInspectAssetImport` (mutation), `useImportAssets`
(mutation), and an export download helper. Mutations invalidate the asset list.

### 3a. Asset drawer (`AssetDrawer.tsx`)
Create / edit / read-only view in one drawer (read-only for non-admins).
- **Base fields:** `asset_name` (required), `serial_number`, `category`
  (required select), `status` (select), `purchase_date` (date), `purchase_cost`
  (number), `depreciation_rate` (number, %).
- **Custodian picker:** select from company users (admin has the list).
- **Document link:** optional docVault document selector (`document_id`).
- **Custom fields section:** rendered dynamically from the active
  `asset_management` definitions — text→text input, number→number input,
  date→date input, dropdown→select of `dropdown_options`, with required markers.
- **Submit:** builds the body including a `custom_fields` object. A client-side
  required-field check mirrors the backend; a backend `400` with
  `detail.custom_field_errors` is surfaced inline/as a toast.

### 3b. Import modal (`ImportAssetsModal.tsx`)
Mirrors the AuditEase TB import (inspect → map → import):
1. **Upload** a `.csv`/`.xlsx` file (held as a `File` in modal state).
2. **Inspect** — call `import/inspect`; show detected columns + a few preview rows.
3. **Map** — for each importable target field
   (`asset_name` [required], `category` [required], `serial_number`, `status`,
   `purchase_cost`, and each active custom-field key) pick a source column or
   leave unmapped. Enforce that the two required targets are mapped before import.
4. **Import** — `POST /import` with the same `File` + `mappings` JSON
   (`[{source_column, target_field}]`), then show the `ImportResult`
   (`imported`, `skipped`, per-row `errors`). On success, invalidate the list.

Note: only the five base targets above plus custom-field keys are importable;
`purchase_date`, `depreciation_rate`, `custodian_id`, `document_id` are not import
targets in the backend and are omitted from the mapping UI.

---

## 4. Routing & navigation
`company.routes.tsx`: replace the `/app/assets` and `/app/custom-fields`
`ModulePlaceholder`s with `AssetsPage` and `CustomFieldsPage`. The existing
sidebar entries already point at these paths — no nav change needed.

---

## 5. Error handling
- Custom-field validation: backend `400 {detail:{custom_field_errors:[...]}}` on
  asset create/update and per-row on import — surfaced inline (form) / in the
  import result table (rows).
- Duplicate field key: `409` on custom-field create — inline error in the modal.
- `403`: admin-only actions are hidden from non-admins; any stray 403 is toasted.
- Import file errors (unsupported format, empty sheet): surfaced from the
  inspect/import responses.

---

## 6. Testing
**Backend**
- `tests/test_custom_fields.py`: create → list (active) → deactivate → list
  (hidden) → list with `include_inactive` (shown) → reactivate; update allowed
  fields; duplicate-key `409`; module scoping; admin-only guard.
- `tests/test_assets.py`: CRUD; custom-field validation on create (required +
  type + dropdown); import inspect returns headers; import with a mapping
  (imported + skipped rows with errors); export returns a spreadsheet; admin-only
  guards; non-admin custodian scoping on list.

**Frontend**
- `customfields.test.tsx`: renders active + inactive fields, create flow calls the
  API, deactivate/reactivate actions fire.
- `assets.test.tsx`: admin sees New/Import/Export and the drawer renders custom
  fields; non-admin sees a read-only list (no action buttons); import modal maps a
  column and calls import.

All new tests pass and the existing suite stays green (backend + frontend).

---

## 7. Out of scope
- The Sales module page (later slice) — only its custom-field definitions are
  manageable here.
- Depreciation calculation (fields stored, not computed).
- Bulk edit/delete of assets; asset deletion (no backend delete endpoint exists).
- Asset categories/tags beyond the fixed `category` enum.
