# DocVault Approval Workflow Fix Design

## Overview
This design addresses the KUB-007 vulnerability in the DocVault module, where the approval workflow could be bypassed and document metadata mass-assigned by unauthorized users. The fix separates lifecycle state transitions from general metadata editing, enforces strict access controls on both, and adds explicit tracking of the approver.

## 1. Database Schema & Migration

### Schema Changes
- **`Document` Model**: Add an `approved_by` column (UUID, nullable, Foreign Key to `CompanyUser.id`). This explicitly tracks the user who performed the verification.

### Backfill Strategy (Log-based)
- We will implement a log-based backfill for existing verified documents.
- The Alembic migration will scan the `ActivityLog` table for `document.updated` actions where the `updated_fields` metadata contains `status` and the document ended up as `verified`.
- The `actor_id` from that log entry will be assigned to `approved_by`.
- If no such log exists (indicating a bypass/self-approval exploit without proper workflow), `approved_by` will remain `NULL`. This preserves an accurate historical compliance record.

## 2. API Changes

### Schemas (`app/schemas/docvault.py`)
- **`DocumentUpdate`**: Remove `status` and `approval_notes`. This schema is now strictly for metadata updates.
- **New Schema `DocumentReviewRequest`**:
  ```python
  class DocumentReviewRequest(BaseModel):
      decision: Literal["verified", "action_required"]
      approval_notes: Optional[str] = Field(None, max_length=1000)
  ```

### Endpoints (`app/routers/docvault.py`)

#### New Endpoint: `POST /api/v1/docvault/documents/{document_id}/review`
- Handles all approval lifecycle transitions.
- **Validation**:
  - The document must currently be in the `pending_approval` state.
  - The `current_user` must be the assigned `approver_id` or a company admin.
  - The `current_user` cannot be the `created_by` user (prevent self-approval), unless they are an admin.
- **Action**:
  - Updates `status` to the requested decision.
  - Sets `approved_by` to `current_user.id` and `approved_at` to the current timestamp.
  - Updates `approval_notes`.

#### Modified Endpoint: `PATCH /api/v1/docvault/documents/{document_id}`
- **Ownership Check**: Introduce `_may_edit_document(user, doc)`. Only the document's creator, the assigned approver, or a company admin can edit metadata. Mere bucket access is read-only.
- **Immutability Control**: Restrict toggling `is_editable` to `True`. Only the document's creator or an admin can unlock a document.
- Status transition logic is removed from this endpoint.

## 3. Audit Logging
- Ensure the `POST /review` endpoint logs a specific `document.reviewed` action instead of a generic `document.updated`.
- The log metadata should include: `{"from": "pending_approval", "to": decision, "notes": approval_notes}`.

## 4. Testing Plan
- **Regression Tests**:
  - Employee cannot self-verify using the `PATCH` endpoint (should return 422 for `status` field).
  - Review endpoint requires the document to be `pending_approval`.
  - Review endpoint rejects non-approvers.
  - Uploader cannot approve their own document (even via the review endpoint).
  - Unrelated user (even with bucket access) cannot edit document metadata via `PATCH`.
- **Existing Tests**: Update any tests currently using `PATCH` for status approval to use the new `POST /review` endpoint.
