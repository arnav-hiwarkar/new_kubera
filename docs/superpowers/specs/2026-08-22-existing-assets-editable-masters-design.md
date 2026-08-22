# Asset Register: Existing-Asset Entry, Editable Masters & Calculation-Safe Editing

**Date:** 2026-08-22
**Branch:** `graph`
**Modules:** Asset Register (`app/routers/assets.py`, `app/routers/asset_masters.py`, `app/routers/depreciation.py`, `frontend/src/pages/company/assets/`)
**Status:** Approved — ready for implementation plan

Five connected changes to the fixed-asset register: an Add-asset split flow with a
new existing-asset (opening-entry) page, Excel/CSV bulk import of pre-existing
assets, a fix to the category picker, fully editable master data via per-company
forking of seeded rows, and an impact-analysis + reopen workflow that keeps
finalized depreciation trustworthy while making every master editable.

---

## 1. Why

**Adding an asset that already exists is hostile.** The only creation path is the
quick-add modal, which models a fresh purchase. Assets owned before the register
cutover must be created as drafts and then have their opening accumulated
depreciation, opening WDV (books) and opening WDV (tax) — already columns on
`Asset` (`app/models/assets.py:335-337`) — filled in deep inside the detail
page's Depreciation tab. There is no entry surface that asks for these up front,
and no bulk path for migrating a legacy register.

**The category picker is broken.** In
`frontend/src/pages/company/assets/CategoryPicker.tsx`, one shared `value` state
drives both selects. Choosing a parent with more than one subcategory calls
`onChange('')` while awaiting the subcategory pick; since the category select's
displayed value derives from that same field, the choice visually snaps back to
the placeholder. Only "Office equipment" and "Electrical installations and
equipment" — the two parents with exactly one child, which auto-select it — work.
Users experience this as "most categories are not clickable."

**Masters are create-only.** Categories, suppliers and lookups ship edit hooks on
the frontend (`useUpdateCategory` etc.) but no UI; IT blocks are entirely
read-only and have no update endpoint at all. Seeded global rows
(`company_id IS NULL`) are locked by a 403 guard because they are shared by every
tenant — so in practice nobody can correct anything.

**Editing has no safety story.** Depreciation runs finalize per financial year;
a finalized run is immutable and feeds the next year's opening balances
(`app/services/depreciation_query.py`). Nothing tells a user whether editing a
master row will change their register, future calculations, or nothing at all —
and if wrong data was finalized, there is no redo: finalized runs cannot even be
deleted (`app/routers/depreciation.py:243`).

## 2. Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Master ownership | **Fork seeds at company creation** (Approach B); each company gets private categories + IT blocks from day one | True multi-tenant install; direct edits never leak across tenants; all global-row read-only machinery disappears |
| Legacy companies | User deletes and re-creates them; lazy auto-fork added as a safety net for any company found empty on first masters read | No migration machinery needed; auto-fork prevents empty pickers |
| Existing-asset entry | One asset per submission on a full page; bulk handled by Excel/CSV import with downloadable template | Covers both legacy migration and mid-year catch-up; atomic import avoids half-migrated registers |
| Lifecycle for entered/imported assets | Draft → normal submit → approve → capitalize | Consistent governance; approval is the second pair of eyes on opening values |
| Finalized-year corrections | Reopen endpoint (admin, reason required, audit-logged), blocked when a later FY is finalized | "Redo" is otherwise impossible after finalization; chronological guard protects chained openings |
| Warning placement | Impact computed live inside every edit dialog, before save | Users decide with facts, not generic scare messages |

## 3. Master data ownership: fork at creation

### 3.1 Forking

- `seed_global_asset_reference_data(db)` gains a `company_id: uuid.UUID`
  parameter (default `None` preserves today's template behavior). Company
  creation invokes it inside the company-creation transaction, stamping every
  Schedule II category and Appendix I block with the new company's id.
- Global rows (`company_id IS NULL`) remain solely as the template source. They
  are never listed, never referenced by assets, never editable through the API.

### 3.2 Lazy auto-fork guard

`ensure_company_masters_forked(db, company_id)` runs on the categories and
it-blocks list endpoints. If the company owns zero category rows *and* zero IT
blocks (i.e., a company created before this change), it forks immediately within
the request transaction. The existing unique indexes
(`uq_asset_categories_company_parent_name`, `uq_it_asset_blocks_company_code`)
make a concurrent double-fork raise `IntegrityError`; the helper catches it,
rolls back, and proceeds — the loser of the race sees the winner's fork.

### 3.3 Scoping simplification

All "seeded = read-only" special cases disappear:

- `list_categories`, `list_it_blocks`, `create_*`, `update_*` filter strictly by
  `company_id == current_user.company_id`; every `OR company_id IS NULL` clause
  goes away.
- `_load_category_for_write` drops its 403 seeded-global branch.
- The depreciation engine's block query
  (`depreciation_query.py:288-290`) becomes company-only.
- Frontend lock icons and "add your own instead of editing them" copy are
  removed from `CategoriesTab` and `ItBlocksTab`.

### 3.4 Editing endpoints

- Categories: existing `PATCH /asset-masters/categories/{id}` now serves any
  company row unchanged.
- IT blocks: **new** `PATCH /asset-masters/it-blocks/{id}` accepting name,
  dep_rate (0–100), block_class, code, is_active, display_order. Duplicate-code
  conflicts return 409. Existing `POST /asset-masters/it-blocks` stays for
  additions.
- Suppliers/Lookups: PATCH endpoints already exist and are unchanged.
- No hard deletes anywhere: `is_active = false` covers removal without breaking
  historical foreign keys.

## 4. Masters UI: edit everywhere

Every tab in `/app/assets/masters` gains row-level Edit actions opening a modal
pre-filled with current values, using the same field set as create:

- **CategoriesTab** — Edit on parent cards (name, tag prefix) and on each
  subcategory row (all default fields). Create modal unchanged.
- **ItBlocksTab** — converts from read-only table to an editable DataTable:
  New Block button plus Edit action per row (name, rate, class, active toggle).
- **SuppliersTab / LookupsTab** — Edit actions wired to the existing update
  hooks (`useUpdateSupplier`, `useUpdateLookup`) which are currently unused.

## 5. Add asset flow & existing-asset page

### 5.1 Split button

`AssetsPage`'s "New asset" button becomes "Add asset" with a two-option dropdown:

- **New asset** — opens the current `QuickAddAssetModal` unchanged.
- **Existing asset** — navigates to `/app/assets/new/existing`.

### 5.2 Existing-asset page

One full-page form, one asset per submission, five sections:

1. **Identity** — asset name\*, category\* (fixed CategoryPicker), description,
   manufacturer, brand/model, serial number.
2. **Cost & dates** — original cost\* (entered directly; these assets carry no
   acquisition record), purchase date (informational), put-to-use date,
   capitalization date. `available_for_use_date` is left NULL; the engine's
   coalescing already treats capitalization as the fallback.
3. **Depreciation inputs** — useful life, method, residual %, IT block + rate:
   auto-filled from category defaults, editable with a mandatory override reason
   when deviating from Schedule II defaults.
4. **Opening balances (cutover)** — opening accumulated depreciation (books),
   opening WDV books, opening WDV tax. Saved with `is_pre_cutover = true`.
5. **Assignment** — branch, location, department, cost centre, custodian
   name/employee code.

**Validation mirrors — and where cheap, tightens — what the depreciation engine
will later demand**, so errors surface at entry rather than at run time months
later. The engine hard-requires only opening WDV (tax) for pre-FY assets; this
form additionally requires the books figures because a cutover asset without
them is incomplete by definition:

- Put-to-use/capitalization date < current FY start ⇒ opening WDV (tax)\*,
  opening WDV (books) and opening accumulated depreciation required.
- Opening values may not exceed original cost; negatives rejected.
- An asset claimed to predate the FY start must carry a usable date
  (put-to-use or capitalization).

### 5.3 Backend endpoint

`POST /assets/existing` creates one standalone draft unit:

- `acquisition_id` stays NULL (column is already nullable).
- `original_cost` set from the request; tag allocated from the category prefix
  via `allocate_asset_codes`; category defaults applied via
  `apply_category_defaults`.
- Response returns the created asset id; frontend navigates to the detail page.
- From there the asset follows the normal submit → approve → capitalize path.

## 6. Bulk import

**Template** — `GET /assets/import/template` generates `.xlsx` (two sheets):
*Instructions* (column meanings, date format `YYYY-MM-DD`, worked example) and
*Assets* with header row: Asset name\*, Category\*, Subcategory\*, Original cost\*,
Purchase date, Put-to-use date, Capitalization date, Opening accumulated
depreciation, Opening WDV (books), Opening WDV (tax), Useful life months, Dep
method, Residual %, IT block code, Branch, Location, Department, Cost centre,
Custodian name, Serial number, Remarks.

**Endpoint** — `POST /assets/import` (multipart; `.xlsx` or `.csv`) reuses the
spreadsheet-parsing infrastructure built for trial-balance import
(`app/services/import_service.py::load_sheet`).

**Matching & validation**

- Categories resolve by name against the company's own forked tree,
  case-insensitive; unknown or ambiguous names fail the row.
- Structural checks first (missing required columns), then the identical
  per-row validation as §5.2.

**Semantics — atomic.** Any failing row aborts the whole import; the response
enumerates every failing row number with its reason. Valid files create
standalone draft units (`is_pre_cutover = true`, no acquisition), individually
tagged, entering the normal approval queue.

## 7. Impact analysis & reopening finalized years

### 7.1 The invariant

Finalized runs store snapshot lines — historical numbers cannot change when a
master row is edited. Draft runs are recomputed from scratch on every execution
(existing behavior: draft runs are deleted and regenerated). Master edits
therefore classify exhaustively:

| Edit | Effect |
|---|---|
| Category defaults (life/method/residual/block/ITC) | None on existing assets — defaults copy onto new assets at creation only (`apply_category_defaults`) |
| Category rename / deactivate | Cosmetic; deactivation blocks new selection only |
| IT block rate/name/class | Future runs only — prior finalized years keep stored rates |
| Supplier/lookup rename | Register labels update; acquisition GST snapshots untouched |

### 7.2 Impact preview endpoint

`GET /asset-masters/{kind}/{id}/impact-preview` (admin; kind ∈ category,
it_block, supplier, lookup) computes live:

- referencing asset counts (by lifecycle),
- financial years having draft vs finalized runs whose lines touch this row,
- classification: `none` or `future_only`,
- human message.

Special case: editing a block's rate while ≥1 finalized run recorded a different
`prescribed_rate` yields: *"FY 2024-25 was finalized at 15%. If that rate was
wrong, reopen that year after saving."*

### 7.3 In-dialog UX

Every masters edit modal fetches the preview on open and renders the verdict
above the save button. Any non-`none` classification requires ticking an explicit
"I understand" confirmation before save is enabled.

### 7.4 Reopen

`POST /depreciation/runs/{run_id}/reopen` (admin):

- Flips status finalized → draft, keeping lines visible for reference; stores the
  mandatory reason in `notes`; writes an audit-log entry.
- **Blocked** when any later financial year already has a finalized run — opening
  balances chain chronologically; years must be redone oldest-first. Error text
  says so.
- After correcting data (asset fields or masters), the user regenerates the run
  via the existing create-run endpoint (drafts supersede automatically) and
  re-finalizes; downstream years pick up corrected openings when their turn comes.

## 8. Category picker fix

`CategoryPicker` tracks `parentId` as its own internal state instead of deriving
both selects from the single leaf-or-empty `value`. External `value` changes sync
`parentId` once. Selecting a multi-child parent now visibly sticks and enables
the subcategory select; single-child parents still auto-select their child;
zero-child parents still select themselves; the statutory hint line is unchanged.

## 9. Auth matrix

| Endpoint | Gate |
|---|---|
| `POST /assets/existing` | Assets-module member (same as quick-add) |
| `POST /assets/import`, `GET /assets/import/template` | Assets-module member |
| `PATCH /asset-masters/it-blocks/{id}` | Admin |
| `GET /asset-masters/{kind}/{id}/impact-preview` | Admin |
| `POST /depreciation/runs/{run_id}/reopen` | Admin |

Tenant isolation throughout: cross-company reads/writes return 404. All
pre-existing master-write endpoints keep their admin gates.

## 10. Testing

### Backend (pytest)

1. **Forking** — company creation forks categories + blocks; list endpoints
   never return global rows; lazy auto-fork fires for empty companies and a
   concurrent double-fork degrades safely (no duplicates, no 500).
2. **IT-block PATCH** — admin edit succeeds; non-admin 403; dep_rate bounds;
   duplicate code 409; regression test proving **finalized run lines remain
   byte-identical after a block-rate edit while the next generated run uses the
   new rate**.
3. **Impact preview** — classification correctness per kind, including the
   finalized-at-old-rate message.
4. **Reopen** — happy path (status flip, reason persisted, audit entry);
   blocked-by-later-FY rule; non-admin 403; regenerate + re-finalize propagates
   corrected openings into the following year.
5. **Existing-asset create** — standalone draft without acquisition; tag
   allocation; category defaults applied; `is_pre_cutover` set; pre-FY
   validation errors; module-gate 403; cross-company 404.
6. **Import** — template contains expected columns; valid file creates N drafts;
   atomic abort leaves zero rows and reports each bad row; case-insensitive
   category matching.
7. **Updated suites** — `tests/test_asset_masters.py` expectations asserting
   seeded-global read-only behavior are revised; that behavior is intentionally
   gone.

### Frontend (vitest)

1. Picker regression: selecting a multi-child category sticks and enables the
   subcategory select.
2. Add-asset menu renders both options and routes correctly.
3. Masters tabs render Edit actions; modals pre-fill and save via the API.
4. Existing-asset page validation messages fire per §5.2 rules.
5. Import modal renders per-row error report and success count.

## 11. Out of scope

- Editing capitalized assets' cost or depreciation inputs en masse (per-asset
  editing already exists; mass adjustment is a separate feature).
- Per-asset impact analysis on the detail page (masters-level only this round).
- Statutory re-seed propagation to existing companies (template updates reach
  new companies; existing companies change deliberately).
- XLSX round-trip export of existing assets for offline edit + re-import
  (template import covers initial migration).
