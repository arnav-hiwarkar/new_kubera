# ROC + SecretarialEase Compliance Module

**Date:** 2026-07-14
**Branch:** `new_frontend`
**Modules:** ROC Compliance (`/app/compliance/roc`), SecretarialEase (`/app/compliance/secretarial`)
**Status:** Approved — ready for implementation plan

ROC and SecretarialEase share one backend (`create_compliance_router` mounted at
`/api/v1/roc` and `/api/v1/secretarial`, differing only by a `domain` value). This
builds a single domain-parameterized frontend module rendered for both, plus two
small backend additions.

---

## 1. Backend additions

### 1a. `record_date` on records
Add a nullable `record_date` (Date) column to `MeetingRecord`
(`app/models/compliance.py`), plus `record_date` on `MeetingRecordCreate` /
`MeetingRecordResponse` (`app/schemas/compliance.py`). This is the date the
document pertains to (meeting/filing period) and drives the month / "this month"
views. Add an Alembic migration and apply it to the dev DB. (The test DB is created
via `Base.metadata.create_all`, so it picks up the column automatically.)

### 1b. Delete-type guard
`delete_document_type` (in the `create_compliance_router` factory) must return
`409` when any `MeetingRecord` references the type, with a clear message. Empty
types still delete. Prevents the FK IntegrityError and orphaned records.

No other backend changes. All compliance endpoints remain open to any authenticated
company user (no admin gating).

---

## 2. Shared module architecture

One `CompliancePage` parameterized by `domain: 'roc' | 'secretarial'`, mounted at
both routes. All hooks/components take the domain and target `/api/v1/{domain}/*`.

```
frontend/src/api/hooks/compliance.ts          (new — domain-parameterized hooks)
frontend/src/pages/company/compliance/
  CompliancePage.tsx        (tabs: Records | Document Types)
  DocumentTypesTab.tsx
  DocumentTypeModal.tsx     (create/edit type + field builder + template upload)
  RecordsTab.tsx            (list + views + filters)
  RecordModal.tsx           (create record: type form + date + template dl + upload)
frontend/src/routes/company.routes.tsx         (swap two placeholders)
```

`api/endpoints/compliance.ts` is extended to cover, per domain: list/create/update/
delete document types, and list/create records. `api/types.ts` already exports the
compliance types; add any new ones (record_date is additive on existing types).

---

## 3. Document Types tab

Lists **system** types (`company_id=null`, read-only) and **company** types. Row:
name, has-template indicator, field count, `due_date_rule`, system/company badge.

- **Create / Edit** (`DocumentTypeModal`; system types open read-only): `name`;
  optional **template upload** → `docvaultApi.uploadDocument` into a "Compliance
  Templates" bucket, then set `template_file_id`; a **field builder** producing
  `metadata_schema = { fields: [{ key, label, type, options?, required? }] }`
  (type ∈ text/number/date/dropdown; key auto-slugged from label); optional
  `due_date_rule` free-text. Company types only for edit.
- **Delete** (company-owned): calls delete; on `409` show "This type has records —
  remove them first."

`metadata_schema` shape is frontend-owned (backend stores the JSONB as-is and does
not validate it).

---

## 4. Records tab

- **Create** (`RecordModal`): select a document type → render its fields from
  `metadata_schema`; a **record date** picker (defaults to today); a **Download
  template** link when the type has `template_file_id`
  (`docvaultApi.downloadDocument` → `saveBlob`); and a **file upload** for the
  completed document. On submit:
  1. Upload the file via `docvaultApi.uploadDocument` into the domain bucket
     ("ROC Compliance" / "SecretarialEase") → `document_id`.
  2. `POST /{domain}/meeting-records` with `doc_type_id`, `document_id`,
     `structured_metadata` (field values keyed by field `key`), and `record_date`.
- **View / list**: a searchable list (search over type name, metadata values,
  document title) with:
  - a **view toggle**: *By type* (grouped by document type) and *By month* (grouped
    by `record_date` month, newest first);
  - a **This month** quick filter (records whose `record_date` is in the current
    month) and a **document-type** filter;
  - each row: record date, type name, a docVault **Download** link for the document,
    and a couple of key metadata values.

Records whose `record_date` is null are grouped under "Undated" in the By-month
view and always shown in the By-type view.

---

## 5. docVault integration
- Template files → "Compliance Templates" bucket (shared across domains).
- Record documents → domain bucket ("ROC Compliance" / "SecretarialEase").
- Both use the existing `docvaultApi.uploadDocument` (multipart with title + bucket)
  and `downloadDocument` (blob) + `saveBlob`. Buckets are found-or-created by name;
  if the docVault upload API requires an existing bucket id, resolve/create it via
  `docvaultApi.listBuckets` / bucket create first.

---

## 6. Error handling
- Delete type with records → `409`, shown inline in the types tab.
- Record create is two-step (upload then record POST); if the record POST fails
  after upload, surface the error (the uploaded doc remains in docVault — acceptable
  for V1).
- Invalid document type for domain → backend `400`, toasted.
- Required type-fields: client-side check before submit (backend does not enforce).

---

## 7. Testing
**Backend** (`tests/test_compliance.py`, extend):
- `record_date` round-trips on create/list.
- Delete-type guard: `409` when a record references the type; success when empty.
- Doc-type CRUD + record create per domain; domain isolation (a ROC type is not
  visible/usable under secretarial).

**Frontend** (`compliance.test.tsx`):
- Document Types tab renders system + company types; create-type modal builds fields.
- Records tab renders, filters by type and by "This month", toggles By type / By month.
- Create-record flow: selecting a type renders its fields, upload + submit calls
  uploadDocument then the record create endpoint.

Full suite stays green (backend + frontend).

---

## 8. Out of scope
- Automated due-date reminders / a compliance calendar (`due_date_rule` is stored
  and displayed only; the notifications/worker integration is a later slice).
- In-app document generation / template auto-fill (no backend for it; templates are
  download-and-fill).
- Editing a record's uploaded file in place (upload a new record instead); record
  edit beyond what the backend exposes (backend has create/list only for records).
- Admin-only restriction on type management (backend allows all company users).
