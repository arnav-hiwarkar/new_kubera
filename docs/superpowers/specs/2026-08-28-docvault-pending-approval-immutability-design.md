# DocVault Pending Approval Strict Immutability Design Spec

## Overview
Enforce strict, end-to-end immutability on documents in the `pending_approval` state across the entire backend API and frontend interface. When a document is awaiting review, only the designated approver (`approver_id`) and company administrators (`role == 'admin'`) can modify metadata, toggle the Final status (`is_editable`), change the status, upload new versions, or archive/delete the document.

---

## 1. Security Policy & Role Definitions

### Eligible Actors for Documents in `pending_approval`:
- **Assigned Approver**: `current_user.id == doc.approver_id`
- **Company Admin**: `current_user.role == UserRole.admin` (or `role == 'admin'`)

### Blocked Actors:
- **Original Uploader / Creator**: `current_user.id == doc.created_by` (unless also the admin)
- **Other Employees**: Any other company user regardless of general DocVault module permissions.

---

## 2. Backend API Enforcement

All endpoints operating on documents in `app/routers/docvault.py` will enforce the security boundary before applying any database changes.

### A. Document Metadata & Property Updates (`PATCH /api/v1/docvault/documents/{doc_id}`)
When `doc.status == DocumentStatus.pending_approval`:
- Evaluate `is_approver_or_admin = (current_user.id == doc.approver_id or is_company_admin(current_user))`.
- If `not is_approver_or_admin`:
  - **Reject all modifications with `HTTP 403 Forbidden`**:
    ```json
    {
      "detail": "Only the assigned approver or an admin can modify, edit, or review this document while approval is pending"
    }
    ```
  - This strictly blocks changes to:
    - `status`
    - `approval_notes`
    - `is_editable` (Mark as Final toggle)
    - `title`
    - `tags`
    - `bucket_id`
    - `approver_id`
    - Any other future metadata fields.

### B. New Version Uploads (`POST /api/v1/docvault/documents/{doc_id}/versions`)
When `doc.status == DocumentStatus.pending_approval`:
- If `not is_approver_or_admin`:
  - **Reject version upload with `HTTP 403 Forbidden`**:
    ```json
    {
      "detail": "Cannot upload new versions while document is pending approval"
    }
    ```

### C. Document Archival / Deletion (`DELETE /api/v1/docvault/documents/{doc_id}`)
When `doc.status == DocumentStatus.pending_approval`:
- If `not is_approver_or_admin`:
  - **Reject deletion with `HTTP 403 Forbidden`**:
    ```json
    {
      "detail": "Cannot archive or delete a document while approval is pending"
    }
    ```

---

## 3. Frontend UI Alignment (`DocumentDrawer.tsx`)

In [`frontend/src/pages/company/docvault/DocumentDrawer.tsx`](file:///Users/ash/Projects/new_kubera/frontend/src/pages/company/docvault/DocumentDrawer.tsx):

1. **State Evaluation**:
   ```typescript
   const isPendingApproval = document.status === 'pending_approval'
   const isApprover = profile?.id === document.approver_id
   const isAdmin = profile?.role === 'admin'
   const canReview = isPendingApproval && (isApprover || isAdmin)
   const editFrozen = (!document.is_editable) || (isPendingApproval && !canReview)
   ```

2. **Control Disabling**:
   - **Editable (Final) Switch**:
     - `disabled = isArchived || update.isPending || (isPendingApproval && !canReview)`
     - Hint text displays: *"Locked while pending approval. Only the assigned approver or admin can adjust."* when `isPendingApproval && !canReview`.
   - **Title & Tags**: Disabled via `editFrozen`.
   - **Bucket Selector**: Disabled via `editFrozen`.
   - **Status Dropdown**: Replaced with the amber informational banner: *"Only [Approver Name] or admin can update status."*
   - **Upload New Version**: Hidden/replaced with info text: *"Document is pending approval by [Approver Name]. New versions cannot be uploaded."*
   - **Archive Action**: Disabled when `isPendingApproval && !canReview`.

---

## 4. Verification & Automated Test Strategy

### Automated Backend Tests ([`tests/test_docvault_approvals.py`](file:///Users/ash/Projects/new_kubera/tests/test_docvault_approvals.py)):
1. `test_pending_approval_creator_cannot_edit_properties`:
   - Creator attempts to PATCH `title` -> `HTTP 403 Forbidden`.
   - Creator attempts to PATCH `tags` -> `HTTP 403 Forbidden`.
   - Creator attempts to PATCH `bucket_id` -> `HTTP 403 Forbidden`.
   - Creator attempts to PATCH `is_editable` -> `HTTP 403 Forbidden`.
   - Creator attempts to PATCH `approver_id` -> `HTTP 403 Forbidden`.
2. `test_pending_approval_creator_cannot_upload_version_or_delete`:
   - Creator attempts `POST /api/v1/docvault/documents/{id}/versions` -> `HTTP 403 Forbidden`.
   - Creator attempts `DELETE /api/v1/docvault/documents/{id}` -> `HTTP 403 Forbidden`.
3. `test_pending_approval_peer_cannot_modify_or_delete`:
   - Another company employee attempts all the above -> `HTTP 403 Forbidden`.
4. `test_pending_approval_approver_and_admin_can_modify_and_resolve`:
   - Approver can review, update notes, and approve (`status = verified`) -> `HTTP 200 OK`.
   - Admin can review, change editable, and approve -> `HTTP 200 OK`.

### Automated Frontend Tests ([`frontend/src/pages/company/docvault/docvault_approvals.test.tsx`](file:///Users/ash/Projects/new_kubera/frontend/src/pages/company/docvault/docvault_approvals.test.tsx)):
- Test `DocumentDrawer` rendering for non-approver viewers when status is `pending_approval`, verifying that `Editable`, `Title`, `Tags`, `Bucket`, and `Upload new version` are all disabled/locked.
