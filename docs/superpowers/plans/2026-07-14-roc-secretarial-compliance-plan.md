# Implementation Plan — ROC + SecretarialEase Compliance

**Spec:** `docs/superpowers/specs/2026-07-14-roc-secretarial-compliance-design.md`
**Date:** 2026-07-14
**Branch:** `new_frontend`

Backend contract first, then the domain-parameterized frontend. Backend on `:8000`
(`--reload`), Vite on `:5173`, pytest via `.venv` with `VAULT_STORAGE_PATH` set to a
writable dir. The frontend `rocApi`/`secretarialApi` and `docvaultApi` clients
already exist and need no new methods (record_date flows through the regenerated
types).

---

## Phase A — Backend

### A1. `record_date` on records
- `app/models/compliance.py`: add to `MeetingRecord`
  `record_date: Mapped[date | None] = mapped_column(Date, nullable=True)`
  (import `Date` from sqlalchemy, `date` from datetime).
- `app/schemas/compliance.py`: add `record_date: Optional[date] = None` to
  `MeetingRecordBase` (so it's on both Create and Response). Import `date`.
- `app/routers/compliance.py`: in `create_meeting_record`, pass
  `record_date=record.record_date` into the `MeetingRecord(...)`.

### A2. Alembic migration for record_date
- Generate a revision adding `meeting_records.record_date` (nullable Date). Author
  it by hand mirroring an existing migration under `alembic/versions/` (upgrade:
  `op.add_column('meeting_records', sa.Column('record_date', sa.Date(), nullable=True))`;
  downgrade: `op.drop_column`). Set `down_revision` to the current head
  (`alembic heads` / inspect the latest file).
- Apply to the dev DB: `alembic upgrade head`. If the async env makes that awkward,
  fall back to a direct `ALTER TABLE meeting_records ADD COLUMN record_date DATE`
  against `localhost:5433/kubera` — but prefer the migration. (The test DB uses
  `create_all`, so tests need no migration.)

### A3. Delete-type guard
- In `create_compliance_router`'s `delete_document_type`, before deleting, count
  `MeetingRecord` rows with `doc_type_id == dt_id`; if > 0 raise
  `HTTPException(409, "This document type has records — remove them first.")`.

### A4. Verify Phase A
- App imports; `POST /roc/meeting-records` accepts/returns `record_date`; deleting a
  type that has a record → 409, an empty type → 200. (Full tests in Phase D.)

---

## Phase B — Frontend API layer

### B1. Regenerate types
- Backend up → `cd frontend && npm run gen:api`. Confirm `record_date` on
  `MeetingRecordCreate`/`MeetingRecordResponse` in `schema.d.ts`.
- `api/endpoints/compliance.ts`: no change (already complete).
- `api/types.ts`: no change needed (compliance types already exported;
  record_date is additive on existing ones).

### B2. Hooks — `api/hooks/compliance.ts` (new)
- `type Domain = 'roc' | 'secretarial'`; helper `apiFor(domain)` → `rocApi`/`secretarialApi`.
- `useDocumentTypes(domain)` (key `['compliance', domain, 'types']`),
  `useCreateDocumentType(domain)`, `useUpdateDocumentType(domain)`,
  `useDeleteDocumentType(domain)`; `useMeetingRecords(domain)` (key
  `['compliance', domain, 'records']`), `useCreateMeetingRecord(domain)`.
  Mutations invalidate the relevant `['compliance', domain, ...]` keys.

---

## Phase C — Frontend UI (`pages/company/compliance/`)

### C1. `CompliancePage.tsx`
Props `{ domain }`. PageHeader (title "ROC Compliance" / "SecretarialEase" by
domain). Tab bar (KRA/AuditEase style): **Records** (default) and **Document Types**.
Renders `RecordsTab` / `DocumentTypesTab` with the domain.

### C2. `DocumentTypesTab.tsx`
- `useDocumentTypes(domain)`. Table: name, template? (has `template_file_id`),
  field count (`metadata_schema.fields?.length`), `due_date_rule`, system/company
  badge (system = `company_id == null`). "New type" button → `DocumentTypeModal`.
- Row actions: Edit (company-owned) / Delete (company-owned; `409` → inline
  "has records" message). System rows: view-only (no edit/delete).

### C3. `DocumentTypeModal.tsx`
- Fields: `name`; **template upload** (file input) — on save, if a file is chosen,
  `resolveBucket('Compliance Templates')` then `docvaultApi.uploadDocument`
  (FormData: title=name+" template", file, bucket_id) → set `template_file_id`;
  **field builder** — add/remove rows of `{label, type(text/number/date/dropdown),
  options?, required?}`, `key` auto-slugged from label; store as
  `metadata_schema = { fields: [...] }`; optional `due_date_rule` text.
- Submit → create/update via hooks. Edit prefills from the type (including existing
  `metadata_schema.fields`). Existing template shown as a note; re-upload replaces.
- Shared helper `resolveBucket(name)`: `docvaultApi.listBuckets()` → find by name or
  `createBucket({name})`; returns the id. (Put in a small `compliance/buckets.ts`.)

### C4. `RecordsTab.tsx`
- `useMeetingRecords(domain)` + `useDocumentTypes(domain)` (to resolve type names +
  field labels). Controls: search box; type filter (Select of types); **This month**
  toggle; **view toggle** By type / By month.
- Grouping:
  - *By type*: group records under their document type's name.
  - *By month*: group by `record_date` month (label e.g. "July 2026"), newest first;
    null `record_date` → "Undated".
  - *This month*: filter to records whose `record_date` is within the current month
    (compute current month client-side; records list is small).
- Row: record date, type name, **Download** (resolve `document_id` →
  `docvaultApi.downloadDocument` → `saveBlob`), and up to ~2 key metadata values.
  Search matches type name + document title + stringified metadata.
- "New record" button → `RecordModal`.

### C5. `RecordModal.tsx`
- Select a document type → render its fields from `metadata_schema.fields`
  (text/number/date → Input, dropdown → Select); **record date** picker (default
  today); **Download template** link if the type has `template_file_id`; **file
  upload** for the completed document (required).
- Submit: `resolveBucket(domain === 'roc' ? 'ROC Compliance' : 'SecretarialEase')`
  → `docvaultApi.uploadDocument` (title = type name + record date, file, bucket_id)
  → `document_id`; then `useCreateMeetingRecord(domain)` with `doc_type_id`,
  `document_id`, `structured_metadata` (values keyed by field key), `record_date`.
  Client-side check required fields + a file before submit. Surface errors via toast.

### C6. Routing
- `company.routes.tsx`: replace the `compliance/roc` and `compliance/secretarial`
  `ModulePlaceholder`s with `<CompliancePage domain="roc" />` /
  `<CompliancePage domain="secretarial" />`.

---

## Phase D — Tests

### D1. Backend (`tests/test_compliance.py`, extend)
- Create a company doc type; create a record with `record_date` → response carries
  it; list returns it.
- Delete guard: create a type + a record referencing it → delete type `409`; delete
  the type after (no records) → success. (Records have no delete endpoint, so use a
  fresh empty type for the success case.)
- Domain isolation: a type created under `/roc` is not returned by `/secretarial`
  and a `/secretarial/meeting-records` create against a ROC type → `400`.
- Keep any existing test_compliance cases green.

### D2. Frontend (`compliance.test.tsx`)
- DocumentTypesTab renders a system + a company type (mock hooks/endpoints);
  create-type modal adds a field row and calls createDocumentType with a
  `metadata_schema.fields` array.
- RecordsTab renders records, filters by type and by This month, toggles By
  type/By month.
- RecordModal: selecting a type renders its fields; submitting uploads (mock
  docvaultApi.uploadDocument) then calls createMeetingRecord.
- Use `vi.mocked(...)`, full mock objects, no `any`.

---

## Phase E — Full verification
- `cd frontend && npm run build && npm run test && npm run lint` (0 errors; the 6
  pre-existing warnings remain).
- Backend `pytest` green.
- Live E2E (script, unique emails): create a ROC type with a template + fields →
  create a record (upload a file) with a record_date → it appears in By-month and
  This-month views → download works → deleting the type is blocked (409) → repeat a
  minimal pass under `/secretarial` to confirm domain isolation.

## Rollout notes
- One DB migration (`record_date`) — apply to dev DB; test DB auto-creates it.
- No new frontend dependencies; the compliance + docvault API clients already exist.
