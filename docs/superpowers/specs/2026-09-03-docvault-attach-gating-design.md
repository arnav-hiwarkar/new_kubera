# DocVault attach gating for Assets, AuditEase, and Requirements

## Problem

Assets, AuditEase query messages, and AuditEase requirement responses all let a user attach an *existing* DocVault document by ID. Each of these three call sites only checks that the document belongs to the caller's company — none of them check whether the caller actually has the `docvault` module, or whether they have access to the specific bucket the document lives in (per `Bucket.visibility` / `BucketAccessGrant`).

Result: a user with only the `assets` module (no `docvault`) can attach any tenant document — including one in an admin-only restricted bucket — to an asset they own, then fully decrypt/download it through the asset's own thumbnail endpoint. The same gap exists for AuditEase query-message attachments (which additionally leaks the document to an external auditor) and for requirement-response submissions.

Separately, the Assets module has no "attach an existing DocVault document" UI at all today — `DocumentsTab.tsx` only supports uploading a brand-new file. The backend endpoint for it (`POST /assets/{asset_id}/documents`) exists but is unused by the frontend.

## Scope

In scope:
- Backend: gate the three attach call sites (Assets, AuditEase query messages, AuditEase requirement responses) on (a) caller has the `docvault` module and (b) caller can access the specific document's bucket.
- Frontend: build the "attach existing DocVault document" flow for Assets (currently missing), reusing the AuditEase requirements-page picker.
- Frontend: hide the "Select from DocVault" option in Assets and AuditEase when the caller lacks DocVault access (currently AuditEase shows it unconditionally, relying on the picker's underlying API calls to fail).

Out of scope (explicitly, per user decision):
- The compliance/ROC/Secretarial router's document linking, the asset `dispose` gate, activity log scoping, and custom-fields module gate — these are separate, out-of-scope findings from the wider security review and are not addressed here.

**Correction found during planning:** the original draft of this spec assumed AuditEase's download side already worked permissively, matching Assets. It does not. Assets has its own dedicated `stream_document` endpoint (`app/routers/asset_documents.py`) that only checks the `assets` module — so it already behaves the way the "download stays permissive" principle requires, and needs no change. AuditEase has **no such dedicated endpoint**: both `QueriesTab.tsx` and `RequirementsTab.tsx` download attachments through the generic `GET /api/v1/docvault/documents/{id}/download`, which is gated on the `docvault` module *and* bucket access. So today, a company user with `auditease` but not `docvault` access cannot download their own query/requirement attachment — the opposite of the intended behavior. Fixing this is now in scope (see below).

## Backend design

### Shared helper: `app/services/bucket_access.py` (new file)

Move `accessible_bucket_ids` and `can_access_bucket` out of `app/routers/docvault.py` (currently private to that module, unused elsewhere) into this new service module. `docvault.py` imports them from here instead of defining them locally — no behavior change for existing docvault routes.

Add one new function:

```python
async def assert_document_attachable(
    db: AsyncSession, user: CompanyUser, document_id: uuid.UUID
) -> Document:
    """Raise 403/404 unless `user` may attach `document_id` elsewhere in the app
    (Assets, AuditEase query/requirement attachments). Admins bypass both checks."""
    if not user_has_module(user, "docvault"):
        raise HTTPException(status_code=403, detail="No access to the docvault module")
    doc = await db.get(Document, document_id)
    if doc is None or doc.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await can_access_bucket(db, user, doc.bucket_id):
        raise HTTPException(status_code=403, detail="You don't have access to this document")
    return doc
```

`user_has_module(user, module_id) -> bool` is extracted from the existing `require_module` closure in `app/auth.py` (admin bypass + `module_id in accessible_modules` check) so it can be called directly outside of FastAPI's `Depends` machinery.

### Call sites updated

1. **`app/routers/asset_documents.py`**
   - `attach_asset_document` and `attach_acquisition_document`: replace `_verify_document(db, body.document_id, current_user.company_id)` with `await assert_document_attachable(db, current_user, body.document_id)`.
   - `upload_asset_document` / `upload_acquisition_document` (brand-new file upload into the dedicated "Assets" bucket) and `stream_document` (download) are **unchanged** — no docvault/bucket check, matching the scope decision above.

2. **`app/routers/auditease.py`** — `add_query_message`: when `attached_document_id` is provided, call `assert_document_attachable(db, current_user, attached_document_id)` before calling `document_access.grant_document_access_to_auditors`.

3. **`app/services/requirements.py`** — `validate_document_ids(db, unique_ids, company_id)` gains a `user: CompanyUser` parameter and calls `assert_document_attachable` for each id (or a bulk variant that loads all candidate docs in one query, then checks each against `accessible_bucket_ids` once). Caller (`create_submission`, invoked from `respond_requirement` in `auditease.py`) passes `current_user` through.

### New: dedicated AuditEase document endpoints (company-user side)

Mirroring the pattern the auditor side already uses (`GET /api/v1/auditor/documents/{id}` + `GET /api/v1/auditor/documents/{id}/download`, both gated by `document_access.auditor_can_access_document`), add two endpoints to `app/routers/auditease.py`:

- `GET /api/v1/auditease/documents/{document_id}` — returns `DocumentResponse` (same schema DocVault itself returns).
- `GET /api/v1/auditease/documents/{document_id}/download` — decrypts and streams the current version, `Content-Disposition` filename from `DocumentVersion.original_filename`.

Both gated by a new `document_access.company_user_can_access_engagement_document(db, company_id, document_id) -> Optional[Document]`: returns the document if it's attached to a `RequirementResponseDocument` or a `QueryMessage` belonging to an engagement of the caller's company — independent of the caller's own DocVault module or bucket access. This is the company-user mirror of `auditor_can_access_document`: once a document is attached to a query or requirement submission, everyone with legitimate access to that engagement's AuditEase record can read it, the same way any accepted auditor already can.

Frontend rewiring:
- `RequirementsTab.tsx`'s `handleDownload` already receives `filename` from `RequirementResponseDocumentOut.filename` (a denormalized column, no metadata round-trip needed) — just swap the blob call from `docvaultApi.downloadDocument` to a new `auditeaseCompanyApi.downloadDocument(documentId)`.
- `QueriesTab.tsx`'s `handleDownload` has no filename available (`QueryMessageResponse` carries only the raw `attached_document_id`), so it needs the two-call pattern the auditor frontend already uses: `auditeaseCompanyApi.getDocument(docId)` for metadata (to read `original_filename` off the current version), then `auditeaseCompanyApi.downloadDocument(docId)` for the blob, combined via the existing `saveBlob` helper (`frontend/src/lib/download.ts`).

### Error contract

All three sites surface the same two failure modes as plain `HTTPException`, consistent with existing `require_module` errors:
- 403 `"No access to the docvault module"` — caller lacks the module entirely.
- 403 `"You don't have access to this document"` — caller has the module but not this bucket.
- 404 `"Document not found"` — wrong company or nonexistent id (unchanged from today).

## Frontend design

### 1. Relocate and generalize the picker

Move `frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx` → `frontend/src/components/docvault/DocVaultPickerModal.tsx`. Add optional `title`/`description` props, defaulted to the current AuditEase copy, so existing callers need only an import-path update.

### 2. AuditEase: gate the existing button

In `RespondPanel.tsx` and `QueriesTab.tsx`, wrap the "Select from DocVault" button with `hasModuleAccess(profile, 'docvault')` (profile from `useCompanyAuth()`). No other behavior change — the picker and submit flow are already correct.

### 3. Assets: add the attach-existing-document flow (new)

In `DocumentsTab.tsx`:
- New "Attach from DocVault" button next to the existing upload dropzone, shown only when `hasModuleAccess(profile, 'docvault')`.
- Opens `DocVaultPickerModal` with `multiple={false}`.
- On confirm, branch exactly like `handleUpload` already does on the selected `role`: if `ACQUISITION_DOC_ROLES.includes(role)`, call the new `useAttachAssetDocument` hook against `POST /asset-acquisitions/{acq_id}/documents`; otherwise against `POST /assets/{asset_id}/documents`. Both wire up the already-defined `assetsApi.attachDocument()` (currently unused).
- On success, invalidate the same query key `handleUpload` invalidates so the new attachment shows up in the list immediately (it renders via the existing `_hydrate`-backed shape, no list-rendering changes needed).
- On failure (403 from `assert_document_attachable`), show a generic error toast via the existing `ApiError` handling pattern already used in this file.

### 4. Requirements page

No frontend change. Existing multi-select picker and submit flow stay as-is; only the backend validation described above is added.

## Testing plan

**Backend (pytest, colocated with existing `tests/test_module_enforcement.py` conventions):**
- `assert_document_attachable` unit tests: admin bypass; no `docvault` module → 403; has `docvault` but wrong bucket → 403; has both → returns doc.
- `attach_asset_document` / `attach_acquisition_document`: regression test — `assets`-only user (no `docvault`) gets 403 attaching an existing document; `docvault` user scoped to bucket A gets 403 attaching a document in restricted bucket B.
- `add_query_message` with `attached_document_id`: same matrix. Additionally assert the new `GET /api/v1/auditease/documents/{id}/download` still works for an `auditease`-only user (no `docvault`, no bucket access) once a document is legitimately attached to one of their queries — locks in the "gate attach, not download" split so a future change doesn't accidentally regress it. Also assert the generic `/api/v1/docvault/documents/{id}/download` still correctly 403s the same user (the new endpoint is additive, not a bypass of the existing one).
- `validate_document_ids` / `create_submission`: same matrix for the requirement-response path.

**Frontend (vitest):** render `DocumentsTab`, `RespondPanel`, `QueriesTab` with a profile lacking `docvault` in `accessible_modules` and assert the attach-from-DocVault control is absent; render with it present and assert it renders and opens the picker.
