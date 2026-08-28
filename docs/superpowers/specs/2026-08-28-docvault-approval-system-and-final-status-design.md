# DocVault Approval System & "Final" Status Specification

## 1. Overview
This specification details the design and implementation of two core enhancements to **DocVault**:
1. **"Final" Document Indicator**: A distinct emerald green dot badge (`● Final`) for documents where editing is disabled (`is_editable: false`), locking further versions and metadata modifications.
2. **First-Class Document Approval System**: A guarded review workflow where users can upload or mark documents as requiring review by a designated approver from their company with DocVault access. While pending approval, documents are locked from unauthorized modifications, approvers get interactive hover triggers in DocVault, review banners in the document drawer, dashboard alert widgets, and in-app notifications.

---

## 2. Requirements & User Stories
- **Uploader**:
  - When uploading a document or editing a document, can toggle "Lock document (Mark as Final)" to prevent future modifications.
  - Can choose "Request Approval" and select a designated approver from a searchable combobox displaying only active company members with DocVault access.
  - Receives an in-app notification when the approver approves, rejects, or updates the document status.
- **Approver**:
  - Receives an in-app notification when a document is assigned for their approval.
  - Sees pending documents highlighted on their company Dashboard with 1-click review shortcuts.
  - Sees a highlighted "Pending Your Review" indicator in DocVault with a prominent **"Review & Approve"** hover quick action button.
  - In the Document Drawer, can 1-click **Approve** (sets status to `Verified`), **Request Changes** (sets status to `Action Required` with feedback notes), or select a target status (e.g. `Submitted`).
- **Non-Approvers / Viewers**:
  - Cannot alter status, change metadata, or upload new versions while a document is in `pending_approval`.
  - See clear informational state indicating who is reviewing the document.
- **Company Admins**:
  - Full override capabilities to act as approver or reassign if the designated approver is unavailable.

---

## 3. Data Model & Architecture

### 3.1 Schema Extensions (`app/models/docvault.py`)
Add the following fields to the `documents` table:
* `approver_id: Mapped[uuid.UUID | None]`: Foreign key referencing `company_users.id` with `ondelete="SET NULL"`, indexed.
* `approval_requested_at: Mapped[datetime | None]`: Timestamp when approval was initiated.
* `approved_at: Mapped[datetime | None]`: Timestamp when approval was resolved.
* `approval_notes: Mapped[str | None]`: Text comment or feedback provided by the approver.

### 3.2 Transient / Eager Properties (`app/schemas/docvault.py`)
`DocumentResponse` will be extended with:
* `approver_id: Optional[uuid.UUID]`
* `approver_name: Optional[str]`
* `approval_requested_at: Optional[datetime]`
* `approved_at: Optional[datetime]`
* `approval_notes: Optional[str]`

Helper `_attach_uploader_names` in `app/routers/docvault.py` will also resolve `approver_name` for all returned documents in a single batched query.

### 3.3 Database Migration
Alembic migration: `add_docvault_approvals.py` adding columns to `documents` and creating index `ix_documents_company_approver_status` on `(company_id, approver_id, status)`.

---

## 4. API & Business Logic (`app/routers/docvault.py`)

### 4.1 Upload Document (`POST /api/v1/docvault/documents`)
- **New Form Parameters**:
  - `needs_approval: bool = False`
  - `approver_id: Optional[UUID] = None`
  - `is_editable: bool = True`
- **Validation**:
  - If `needs_approval` is `True`:
    - `approver_id` is mandatory.
    - `approver_id` must belong to an active, non-deleted user in the same company (`company_id == current_user.company_id`).
    - Approver must have DocVault access (either `role == UserRole.admin` or `'docvault' in accessible_modules`).
    - If `bucket_id` is provided and is a restricted bucket, approver MUST have access to that bucket.
    - Set `status = DocumentStatus.pending_approval`, `approval_requested_at = datetime.now(timezone.utc)`.
  - Dispatch in-app notification to `approver_id`:
    - `recipient_type = RecipientType.company_user`
    - `type = "docvault.approval_requested"`
    - `payload = {"document_id": str(doc.id), "title": doc.title, "uploader_name": current_user.full_name, "message": f"{current_user.full_name} requested your approval on '{doc.title}'"}`

### 4.2 Update Document (`PATCH /api/v1/docvault/documents/{document_id}`)
- **Security & Authorization Rules**:
  1. **Pending Approval Guard**:
     - If document is currently in `status == DocumentStatus.pending_approval`:
       - Only the assigned approver (`current_user.id == doc.approver_id`) or a Company Admin (`current_user.role == UserRole.admin`) is permitted to change `status` or provide `approval_notes`.
       - Non-approvers / non-admins attempting to change status receive `HTTP 403 Forbidden`.
       - Non-approvers / non-admins attempting to edit gated fields (`title`, `tags`, `bucket_id`) or upload versions while pending approval receive `HTTP 409 Conflict`.
  2. **Resolution Handling**:
     - When approver updates status away from `pending_approval` (e.g. to `verified`, `submitted`, `action_required`):
       - Record `approved_at = datetime.now(timezone.utc)` and `approval_notes = updates.approval_notes`.
       - Dispatch notification to document creator (`doc.created_by`):
         - `type = "docvault.approval_resolved"`
         - `payload = {"document_id": str(doc.id), "title": doc.title, "status": doc.status.value, "approver_name": current_user.full_name, "notes": doc.approval_notes, "message": f"{current_user.full_name} updated status of '{doc.title}' to {humanize(doc.status.value)}"}`
  3. **"Final" Document Guard (`is_editable == false`)**:
     - If `doc.is_editable == False` and the request does not explicitly set `is_editable = True`:
       - Gated fields (`title`, `tags`, `bucket_id`) and new version uploads are strictly blocked (`HTTP 409 Conflict`).

### 4.3 Version Upload (`POST /api/v1/docvault/documents/{document_id}/versions`)
- Blocked if `doc.is_editable == False` OR `doc.status == DocumentStatus.pending_approval` (unless uploader is an admin or approver acting intentionally).

### 4.4 Document Listing & Queries (`GET /api/v1/docvault/documents`)
- Add query parameters:
  - `pending_my_approval: Optional[bool] = None` (filters documents where `status == pending_approval` and `approver_id == current_user.id`).
  - `approver_id: Optional[UUID] = None`.

---

## 5. Frontend UI/UX Design

### 5.1 "Final" Document Badge
- Located in `DocVaultPage.tsx` table, `DocumentDrawer.tsx`, and 3D graph view.
- Component styling:
  ```tsx
  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.6)]" />
    Final
  </span>
  ```
- Upload modal toggle: *"Mark as Final (Lock document from future edits and versions)"*.

### 5.2 Searchable Approver Picker (`ApproverPicker.tsx`)
- Popover/combobox with:
  - Search input with auto-focus.
  - Filtered list of company users: must have `docvault` module access or `admin` role, and `!deleted_at` and `is_active`.
  - User item displays avatar/initials, full name, email, and department/role badge.
  - Clear button and active selection state.

### 5.3 DocVault Table Row Hover Trigger
- When row has `status === 'pending_approval'` and `current_user.id === doc.approver_id`:
  - Amber/accent subtle badge: `"Pending your review"`.
  - On hover over the row, a quick button **"Review & Approve"** appears in the row action area.
  - Clicking opens `DocumentDrawer` with approval action controls in focus.

### 5.4 Document Drawer Approval Review Section
- If `status === 'pending_approval'`:
  - **For Approver & Admin**:
    - Prominent banner: *"Approval requested by {created_by_name} on {date}"*.
    - Optional review notes text area.
    - Two action buttons:
      - **"Approve Document"** (Green / Accent, sets status to `Verified`).
      - **"Request Changes"** (Amber / Warning, sets status to `Action Required` with required notes).
      - Status dropdown to select other statuses (e.g. `Submitted`).
  - **For Non-Approvers**:
    - Blue/Neutral banner: *"Awaiting approval by {approver_name}. Edits are locked until review completes."*

### 5.5 Company Dashboard Widget (`Dashboard.tsx`)
- In `frontend/src/pages/company/Dashboard.tsx`:
  - A dedicated **"Pending Approvals"** Card:
    - Visible if there are documents awaiting current user's approval.
    - Displays count badge, document title, bucket name, uploader name, requested timestamp.
    - **"Review"** button navigating directly to `/app/docvault` with that document open.

### 5.6 Notifications Page Integration (`NotificationsPage.tsx`)
- Clicking an approval notification navigates directly to `/app/docvault` and opens the document drawer for instant review.

---

## 6. Comprehensive Test & Security Matrix

### 6.1 Standard Workflow Test Cases
1. **Final Lock Workflow**:
   - Upload doc with `is_editable=False` -> displays `● Final` green dot badge -> attempt to update title -> returns 409 -> attempt to upload version -> returns 409.
2. **Approval Request Flow**:
   - Upload doc with `needs_approval=True` and valid `approver_id` -> doc status is `pending_approval` -> approver receives notification -> approver sees item on Dashboard -> approver sees hover action in DocVault -> approver approves -> doc status becomes `verified` -> uploader receives resolution notification.
3. **Request Changes Flow**:
   - Approver reviews doc -> enters review note "Missing signatory page" -> clicks "Request Changes" -> status becomes `action_required` -> uploader receives notification with review note.

### 6.2 Security & Exploit Prevention Test Cases
1. **Cross-Tenant Approver Injection**:
   - Attacker attempts to assign `approver_id` belonging to Company B -> Backend rejects with `400 Bad Request`.
2. **Unauthorized User Approval Bypass**:
   - User X uploads doc and assigns User Y as approver. User Z (non-admin, non-approver) calls `PATCH /api/v1/docvault/documents/{id}` with `status=verified` -> Backend rejects with `403 Forbidden`.
3. **Assigning Ineligible / Revoked Approver**:
   - Attacker assigns a user whose `accessible_modules` does not include `docvault` -> Backend rejects with `400 Bad Request`.
   - Attacker assigns a soft-deleted user -> Backend rejects with `400 Bad Request`.
4. **Restricted Bucket Leakage Prevention**:
   - Doc uploaded into a `restricted` bucket with an approver who has NO access to that bucket -> Backend rejects with `400 Bad Request` ("Approver does not have access to this restricted bucket").
5. **Content Tampering During Approval**:
   - Uploader or third party attempts to upload a new version or change document tags/title while status is `pending_approval` -> Backend rejects with `409 Conflict`.
6. **Admin Override Legitimacy**:
   - Company Admin calls `PATCH /api/v1/docvault/documents/{id}` on a document assigned to User Y -> Admin is authorized and status is updated successfully.
