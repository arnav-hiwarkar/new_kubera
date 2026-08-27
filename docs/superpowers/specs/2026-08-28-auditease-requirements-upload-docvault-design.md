# AuditEase Requirements — Machine Upload & Modern DocVault Picker Design

**Spec + change sheet — single source of truth for this work**

| | |
|---|---|
| **Date** | 2026-08-28 |
| **Status** | Approved — ready to plan |
| **Target Area** | AuditEase Requirements Module & DocVault Picker Integration |

---

## 1. Executive Summary & Goals

The AuditEase Requirements application allows companies and auditors to collaborate on document requests for financial audits. This specification addresses three key improvements:

1. **Direct Machine Upload & Bucket Storage**: Provide an intuitive drag-and-drop file dropzone in the company response panel. Uploaded files are automatically stored in the company's dedicated DocVault engagement bucket (`Audit - <period_label>`), encrypted with tenant keys, tagged, and linked to the requirement submission round.
2. **Modern DocVault Picker Modal**: Redesign the "Select from DocVault" modal into an expansive, fluid micro-application built with `framer-motion`, featuring a left Bucket Rail, multi-attribute instant search, tag filters, "Selected Only" review mode, animated document cards with selection indicators, and a floating selection tray.
3. **Strict Security & Least-Privilege Protection**: Ensure assigned auditors can only access and download documents submitted to requirements or queries in active engagements. Non-admin company users are strictly scoped to their permitted buckets in the picker.
4. **Comprehensive Test Coverage**: Add thorough integration tests for upload/download boundaries, cross-tenant security, ACL scoping, and frontend unit tests for picker and dropzone components.

---

## 2. Architecture & Data Flow

### 2.1 Direct Machine Upload & DocVault Routing

```
[Company User in Requirement View]
         │
         │ 1. Drops files or picks from machine + optional text answer
         ▼
[POST /api/v1/auditease/engagements/{engagement_id}/requirement-requests/{req_id}/respond]
 (multipart form-data: files[], document_ids[], text_answer)
         │
         ├──▶ For each machine file:
         │      • Stored as a Document in the company's dedicated engagement bucket ("Audit - {period_label}")
         │      • Encrypted using the tenant's KEK/DEK encryption envelope
         │      • Tagged: ["audit-attachment", "engagement:{engagement_id}", "REQ-xxx"]
         │      • Joined to RequirementResponse via RequirementResponseDocument join record
         │      • Automatically creates DocumentAccessOverride for all active auditors on the engagement
         │
         ├──▶ For each picked DocVault document:
         │      • Validated that it belongs to the caller's company
         │      • Joined to RequirementResponse via RequirementResponseDocument join record
         │      • Automatically creates DocumentAccessOverride for all active auditors on the engagement
         │
         └──▶ Increments submission round_number (1, 2, 3...) in append-only history
```

### 2.2 Auditor Download & Access Evaluation

```
[Auditor in Requirements View]
         │
         │ 1. Views submission timeline and clicks Download on DocumentChip
         ▼
[GET /api/v1/auditor/documents/{document_id}/download]
         │
         ├──▶ Security Evaluation:
         │      1. Checks if document is linked to a submission or query in an active engagement
         │         where auditor holds 'requirements' or 'documents' area permission.
         │      2. Or checks for active DocumentAccessOverride grant.
         │      3. If neither condition is met: RETURNS 404 (Document not found / Access denied).
         │
         └──▶ On Success:
                • Decrypts document using company KEK/DEK
                • Streams plaintext with correct filename & Content-Disposition
                • Logs audit trail activity: "document.downloaded"
```

---

## 3. Detailed Component Specifications

### 3.1 `DocVaultPickerModal.tsx` (Complete Redesign)

The picker modal will provide a full-featured DocVault browsing experience inside a modal overlay:

1. **Header & Search Controls**:
   - Multi-attribute instant search matching on `title`, `tags`, `original_filename`, and `bucket_name`.
   - "Selected Only (N)" tab toggle allowing quick review of checked items without losing scroll state.
   - Batch selection actions: "Select all visible" and "Deselect all visible".
2. **Left Bucket Rail**:
   - Lists "All Buckets", "Uncategorized", and each accessible company bucket.
   - Shows active highlight bar, item count badges, and lock icons for restricted buckets.
   - Dynamically filters the document grid upon bucket selection.
3. **Interactive Document Grid / Cards**:
   - Fluid card layout with `framer-motion` enter/exit/layout animations.
   - Visual checkbox with animated checkmark on click.
   - Displays document title, version pill (`v1`, `v2`), bucket badge, tag pills, human-readable file size, and last modified date.
   - Hover and selected card highlight states.
4. **Docked Selection Tray**:
   - Animated slide-up tray (`AnimatePresence`) when `selectedDocIds.length > 0`.
   - Removable document chips with quick `X` dismissal.
   - "Attach Selected (N)" primary button and "Clear All" action.

### 3.2 `RespondPanel.tsx` (Enhanced Machine Upload & Staging)

1. **Interactive Drag-and-Drop Dropzone**:
   - Visual drop target supporting drag-over states (`isDragActive`), dashed border highlights, and file drop handling.
   - Click-to-browse file picker for machine files.
   - Secondary button to trigger `DocVaultPickerModal`.
2. **Unified File Staging Area**:
   - Local machine files staged with distinctive file icon, size badge, and remove button.
   - Picked DocVault documents staged with vault icon, title, and remove button.
   - Real-time total document counter.
3. **Submission Handling**:
   - Submits `text_answer`, `files`, and `document_ids` via `FormData`.
   - Disables submit during pending mutations.
   - Triggers TanStack Query invalidations for `['auditease', 'requirements']`, `['docvault', 'documents']`, and `['company', 'activity']`.

### 3.3 `SubmissionTimeline.tsx` & `DocumentChip.tsx`

1. Document chips render file type icon, filename, formatted file size, and direct download trigger.
2. Deleted documents gracefully display a disabled chip with a `(deleted)` badge preserving original filename history.

---

## 4. Security & Permissions Matrix

| Concern | Enforcement Mechanism | Failure Response |
|---|---|---|
| **Multi-Tenant Isolation** | All document lookups filter on `company_id`. All-or-nothing check on `document_ids`. | `404 Not Found` + zero DB changes |
| **Bucket Permissions (Company Users)** | Non-admin users restricted to `everyone` buckets or explicit `BucketAccessGrant` entries via `accessible_bucket_ids`. | Restricted buckets excluded from API results |
| **Auditor Least-Privilege Access** | Auditors can only download documents attached to requirements or queries in active engagements where they hold the area grant. | `404 Not Found / Access Denied` |
| **Unsubmitted Vault Documents** | Non-submitted company documents remain strictly inaccessible to auditors. | `404 Not Found` |
| **Encryption at Rest** | Uploaded files encrypted with DEK/KEK envelope. | Unauthenticated / unauthorized requests cannot obtain key |
| **Closed State Protection** | Submission on closed requirement or closed engagement is blocked. | `400 Bad Request` |

---

## 5. Master Change Inventory

### Frontend

| File | Action | Description |
|---|---|---|
| `frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx` | Rewrite | Complete redesign with bucket rail, search, tag filters, card animations, and selection tray. |
| `frontend/src/components/auditease/requirements/RespondPanel.tsx` | Modify | Add drag-and-drop dropzone, local file staging, and dual attachment handling. |
| `frontend/src/components/auditease/requirements/DocVaultPickerModal.test.tsx` | Create / Update | Unit tests for bucket rail, search, filters, selection, and confirm callbacks. |
| `frontend/src/components/auditease/requirements/RespondPanel.test.tsx` | Create / Update | Unit tests for drag-and-drop staging, vault picker staging, and form submission. |

### Backend & Tests

| File | Action | Description |
|---|---|---|
| `tests/test_requirement_submissions.py` | Modify / Extend | Add test cases verifying machine upload to engagement bucket, auditor download, security boundaries (unsubmitted doc protection), and role-based bucket scoping. |

---

## 6. Testing & Quality Assurance Plan

### 6.1 Backend Integration Tests
1. **Direct Machine Upload**: Verify file upload on `/respond` creates Document in `Audit - <period_label>` bucket with tags and DEK encryption.
2. **Auditor Download of Submitted File**: Verify assigned auditor can download submitted document.
3. **Auditor Download of Attached Vault Doc**: Verify auditor can download external vault document attached via `document_ids`.
4. **Security Boundary — Unsubmitted Docs**: Verify auditor receives 404 when requesting an unsubmitted company document.
5. **Security Boundary — Unassigned Auditor**: Verify unassigned auditor receives 404 on all documents.
6. **Cross-Tenant Prevention**: Verify tenant A cannot attach tenant B's document (404 rollback).
7. **Role-Based Bucket Scoping**: Verify employee role only sees permitted buckets and uncategorized documents.

### 6.2 Frontend Unit Tests
1. **`DocVaultPickerModal.test.tsx`**:
   - Bucket rail navigation and item count display.
   - Search filtering by title, tag, filename.
   - "Selected only" tab filter.
   - Selection toggle, Select All visible, Deselect All.
   - Modal confirm callback with selected document IDs.
2. **`RespondPanel.test.tsx`**:
   - Dropzone rendering and drag-over events.
   - File input staging.
   - DocVault picker modal opening and staged document removal.
   - Form submission payload verification.
