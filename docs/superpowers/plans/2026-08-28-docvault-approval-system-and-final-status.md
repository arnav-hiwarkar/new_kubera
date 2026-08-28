# DocVault Approval System & "Final" Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the DocVault document approval workflow and "Final" status lock, including searchable approver assignment, server-side permission enforcement, DocVault table hover quick action triggers, dashboard widgets, and in-app notifications.

**Architecture:** Extend `Document` model with `approver_id`, `approval_requested_at`, `approved_at`, and `approval_notes`. Add an Alembic migration and guardrails in `app/routers/docvault.py` restricting status transitions and content edits during `pending_approval`. On the frontend, build an accessible `ApproverPicker` combobox, an emerald green dot `Final` indicator for `is_editable=false` docs, row hover quick review triggers, a dedicated review section in `DocumentDrawer`, a "Pending Approvals" dashboard widget, and notification integration.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL, Pydantic v2, React 18, TypeScript, TailwindCSS, TanStack Query, Lucide Icons, Pytest, Vitest.

## Global Constraints
- Tenant isolation: All queries, approver lookups, and updates must strictly filter by `company_id`.
- Non-approvers (except Company Admins) receive `403 Forbidden` if attempting to change status or approval notes while document is in `pending_approval`.
- While `pending_approval`, document metadata (`title`, `tags`, `bucket_id`) and new version uploads are blocked (`409 Conflict`).
- When `is_editable` is `False`, document is marked as `● Final` (emerald badge) and cannot receive new versions or metadata edits without being unlocked.
- Approver selector must only list active, non-deleted users who have `docvault` in `accessible_modules` (or `role == 'admin'`).

---

### Task 1: Database Migration & Model Extensions

**Files:**
- Create: `alembic/versions/e9f0a1b2c3d4_docvault_approval_system.py`
- Modify: `app/models/docvault.py:67-85`
- Modify: `app/schemas/docvault.py:52-77`
- Test: `tests/test_docvault_approvals.py`

**Interfaces:**
- Consumes: `app.models.docvault.Document`, `app.models.company.CompanyUser`
- Produces: `Document.approver_id`, `Document.approval_requested_at`, `Document.approved_at`, `Document.approval_notes` on ORM and `DocumentResponse`

- [ ] **Step 1: Write the failing test for schema and model attributes**

```python
# tests/test_docvault_approvals.py
import pytest
from app.models.docvault import Document, DocumentStatus

def test_document_model_has_approval_fields():
    assert hasattr(Document, "approver_id")
    assert hasattr(Document, "approval_requested_at")
    assert hasattr(Document, "approved_at")
    assert hasattr(Document, "approval_notes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_docvault_approvals.py -k test_document_model_has_approval_fields -v`
Expected: FAIL with attribute error on `Document`

- [ ] **Step 3: Update `app/models/docvault.py` with approval columns**

```python
# app/models/docvault.py
    approver_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True, index=True)
    approval_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
```

- [ ] **Step 4: Update `app/schemas/docvault.py` with approval fields**

```python
# app/schemas/docvault.py
class DocumentResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    current_version_id: Optional[uuid.UUID]
    bucket_id: Optional[uuid.UUID]
    status: DocumentStatus
    title: str
    doc_type_id: Optional[uuid.UUID]
    tags: List[str]
    is_editable: bool
    created_by: Optional[uuid.UUID]
    created_by_name: Optional[str] = None
    approver_id: Optional[uuid.UUID] = None
    approver_name: Optional[str] = None
    approval_requested_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approval_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    versions: List[DocumentVersionResponse] = []

    model_config = {"from_attributes": True}


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    status: Optional[DocumentStatus] = None
    bucket_id: Optional[uuid.UUID] = None
    tags: Optional[List[str]] = None
    is_editable: Optional[bool] = None
    approver_id: Optional[uuid.UUID] = None
    approval_notes: Optional[str] = Field(None, max_length=1000)
```

- [ ] **Step 5: Create and run Alembic migration `e9f0a1b2c3d4_docvault_approval_system.py`**

```python
"""docvault approval system

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-28 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, None] = 'd8e9f0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('documents', sa.Column('approver_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('documents', sa.Column('approval_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('approval_notes', sa.String(length=1000), nullable=True))
    op.create_foreign_key('fk_documents_approver_id', 'documents', 'company_users', ['approver_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_documents_approver_id', 'documents', ['approver_id'])
    op.create_index('ix_documents_company_approver_status', 'documents', ['company_id', 'approver_id', 'status'])

def downgrade() -> None:
    op.drop_index('ix_documents_company_approver_status', table_name='documents')
    op.drop_index('ix_documents_approver_id', table_name='documents')
    op.drop_constraint('fk_documents_approver_id', 'documents', type_='foreignkey')
    op.drop_column('documents', 'approval_notes')
    op.drop_column('documents', 'approved_at')
    op.drop_column('documents', 'approval_requested_at')
    op.drop_column('documents', 'approver_id')
```

Run: `uv run alembic upgrade head`

- [ ] **Step 6: Run tests to verify model passes**

Run: `uv run pytest tests/test_docvault_approvals.py -k test_document_model_has_approval_fields -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/e9f0a1b2c3d4_docvault_approval_system.py app/models/docvault.py app/schemas/docvault.py tests/test_docvault_approvals.py
git commit -m "feat(docvault): add approver and approval fields to document model and schema"
```

---

### Task 2: Backend Router Security Guardrails, Approver Validation & Notifications

**Files:**
- Modify: `app/routers/docvault.py`
- Test: `tests/test_docvault_approvals.py`

**Interfaces:**
- Consumes: `app.models.notification.Notification`, `app.models.company.CompanyUser`
- Produces: Guarded `POST /documents`, `PATCH /documents/{id}`, `POST /documents/{id}/versions`, `GET /documents`

- [ ] **Step 1: Write failing tests covering standard flow & security exploits**

```python
# In tests/test_docvault_approvals.py
# Test 1: Upload with approval request sets pending_approval and creates approver notification
# Test 2: Ineligible approver (wrong company / no docvault access / deleted) returns 400
# Test 3: Non-approver, non-admin PATCH status while pending_approval returns 403
# Test 4: Assigned approver PATCH status to verified sets approved_at, notes, and notifies uploader
# Test 5: Admin override PATCH status succeeds
# Test 6: Non-approver content edits while pending_approval returns 409
# Test 7: Restricted bucket approver access validation (returns 400 if approver cannot access bucket)
# Test 8: Final lock (is_editable=False) blocks version uploads and edits (returns 409)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_docvault_approvals.py -v`
Expected: FAIL

- [ ] **Step 3: Implement validation & notification logic in `app/routers/docvault.py`**

1. Update `_attach_uploader_names`:
```python
async def _attach_uploader_names(db: AsyncSession, docs: List[Document]) -> List[Document]:
    ids = {d.created_by for d in docs if d.created_by}
    ids |= {d.approver_id for d in docs if d.approver_id}
    ids |= {v.uploaded_by for d in docs for v in d.versions if v.uploaded_by}
    names: dict[uuid.UUID, str] = {}
    if ids:
        rows = await db.execute(
            select(CompanyUser.id, CompanyUser.full_name).where(CompanyUser.id.in_(ids))
        )
        names = {row.id: row.full_name for row in rows}
    for d in docs:
        d.created_by_name = names.get(d.created_by)
        d.approver_name = names.get(d.approver_id)
        for v in d.versions:
            v.uploaded_by_name = names.get(v.uploaded_by)
    return docs
```

2. Update `upload_document` endpoint:
- Add `needs_approval: Annotated[bool, Form()] = False` and `approver_id: Annotated[Optional[uuid.UUID], Form()] = None`.
- Validate approver:
  - If `needs_approval`: ensure `approver_id` is provided.
  - Query user: must have `id == approver_id`, `company_id == current_user.company_id`, `deleted_at.is_(None)`, `is_active == True`.
  - Ensure user has access to docvault (`role == UserRole.admin or 'docvault' in (user.accessible_modules or [])`).
  - If `bucket_id`: ensure approver can access that bucket (`await can_access_bucket(db, approver_user, bucket_id)`).
  - Set `status = DocumentStatus.pending_approval`, `approver_id = approver_id`, `approval_requested_at = datetime.now(timezone.utc)`.
  - Create `Notification(recipient_type=RecipientType.company_user, recipient_id=approver_id, type="docvault.approval_requested", payload={...})`.

3. Update `update_document` endpoint:
- Check if document is currently in `DocumentStatus.pending_approval`:
  - If status change or `approval_notes` requested:
    - Must be `current_user.id == doc.approver_id` or `current_user.role == UserRole.admin`. If not, raise `HTTPException(403, "Only the assigned approver or an admin can review this document")`.
    - If status changed away from `pending_approval`: record `doc.approved_at = datetime.now(timezone.utc)`, `doc.approval_notes = updates.approval_notes`.
    - If doc was created by a user, send `Notification(recipient_type=RecipientType.company_user, recipient_id=doc.created_by, type="docvault.approval_resolved", payload={...})`.
  - If content/metadata edit attempted by non-approver/non-admin while `pending_approval`, raise `HTTPException(409, "Document is pending approval and cannot be modified")`.

4. Update `upload_document_version` endpoint:
- If `doc.status == DocumentStatus.pending_approval` and `current_user.id != doc.approver_id` and `current_user.role != UserRole.admin`:
  - Raise `HTTPException(409, "Document is pending approval; new versions cannot be uploaded")`.

5. Update `list_documents` endpoint:
- Add `pending_my_approval: Optional[bool] = None` and `approver_id: Optional[uuid.UUID] = None`.
- If `pending_my_approval`: `query = query.where(Document.status == DocumentStatus.pending_approval, Document.approver_id == current_user.id)`.
- If `approver_id`: `query = query.where(Document.approver_id == approver_id)`.

- [ ] **Step 4: Run tests to verify all pass**

Run: `uv run pytest tests/test_docvault_approvals.py tests/test_docvault.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/docvault.py tests/test_docvault_approvals.py
git commit -m "feat(docvault): add approval validation, permission guardrails and notifications"
```

---

### Task 3: Frontend API & Types Alignment

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/endpoints/docvault.ts`
- Modify: `frontend/src/api/hooks/docvault.ts`

**Interfaces:**
- Consumes: Backend `/api/v1/docvault` endpoints
- Produces: `DocumentResponse` TypeScript types and React Query hooks (`usePendingApprovals()`, updated `useUploadDocument`, `useUpdateDocument`)

- [ ] **Step 1: Update `frontend/src/api/types.ts`**

Add fields to `DocumentResponse`:
```typescript
export interface DocumentResponse {
  id: string
  company_id: string
  current_version_id: string | null
  bucket_id: string | null
  status: DocumentStatus
  title: string
  doc_type_id: string | null
  tags: string[]
  is_editable: boolean
  created_by: string | null
  created_by_name?: string | null
  approver_id?: string | null
  approver_name?: string | null
  approval_requested_at?: string | null
  approved_at?: string | null
  approval_notes?: string | null
  created_at: string
  updated_at: string
  versions: DocumentVersionResponse[]
}

export interface DocumentUpdate {
  title?: string
  status?: DocumentStatus
  bucket_id?: string | null
  tags?: string[]
  is_editable?: boolean
  approver_id?: string | null
  approval_notes?: string | null
}
```

- [ ] **Step 2: Update `frontend/src/api/endpoints/docvault.ts` & `frontend/src/api/hooks/docvault.ts`**

Add query params support for `pending_my_approval` and hook `usePendingApprovals()`.

- [ ] **Step 3: Run TypeScript compiler check**

Run: `cd frontend && npm run build -- --noEmit || npx tsc --noEmit`
Expected: PASS with 0 errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/endpoints/docvault.ts frontend/src/api/hooks/docvault.ts
git commit -m "feat(frontend): update docvault types and hooks for approval workflow"
```

---

### Task 4: Searchable Approver Combobox & "Final" Indicator UI Components

**Files:**
- Create: `frontend/src/pages/company/docvault/ApproverPicker.tsx`
- Create: `frontend/src/components/ui/FinalBadge.tsx`
- Modify: `frontend/src/pages/company/docvault/UploadDocumentModal.tsx`

**Interfaces:**
- Produces: `<ApproverPicker value={approverId} onChange={setApproverId} bucketId={bucketId} />`
- Produces: `<FinalBadge />` component with green dot indicator

- [ ] **Step 1: Create `FinalBadge.tsx`**

```tsx
// frontend/src/components/ui/FinalBadge.tsx
import { cn } from '@/lib/cn'

export function FinalBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-400',
        className,
      )}
      title="This document is Final (locked from edits and new versions)"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.7)]" />
      Final
    </span>
  )
}
```

- [ ] **Step 2: Create `ApproverPicker.tsx`**

Implement searchable combobox displaying user avatars, full name, email, department, with live search filtering, auto-focus, and restricted bucket access checks.

- [ ] **Step 3: Update `UploadDocumentModal.tsx`**

Integrate:
- Toggle: *"Lock document (Mark as Final — prevent further edits and new versions)"*.
- Toggle: *"Request approval"*.
- When "Request approval" is checked, render `<ApproverPicker />`.
- Append `needs_approval` and `approver_id` to `FormData` on submit.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/FinalBadge.tsx frontend/src/pages/company/docvault/ApproverPicker.tsx frontend/src/pages/company/docvault/UploadDocumentModal.tsx
git commit -m "feat(ui): add ApproverPicker, FinalBadge and upload modal approval controls"
```

---

### Task 5: DocVault Table Hover Quick Action & Document Drawer Approval Panel

**Files:**
- Modify: `frontend/src/pages/company/docvault/DocVaultPage.tsx`
- Modify: `frontend/src/pages/company/docvault/DocumentDrawer.tsx`

**Interfaces:**
- Consumes: `useCompanyAuth()`, `FinalBadge`, `DocumentDrawer`
- Produces: Row hover trigger "Review & Approve" and rich approval review action panel in `DocumentDrawer`

- [ ] **Step 1: Update `DocVaultPage.tsx`**

- In Title column: If `!d.is_editable`, render `<FinalBadge />` beside title.
- If `d.status === 'pending_approval'`:
  - Show "Pending Approval" status badge.
  - If current user is approver or admin:
    - Display amber tag `"Needs your review"`.
    - In row actions: On hover (or always visible on mobile/desktop hover), render `<Button size="sm" variant="secondary" onClick={() => setSelectedId(d.id)}>Review & Approve</Button>`.

- [ ] **Step 2: Update `DocumentDrawer.tsx`**

- Render `<FinalBadge />` in header when `!document.is_editable`.
- If `document.status === 'pending_approval'`:
  - If current user is approver or admin:
    - Render prominent **Review Action Box**:
      - Banner with uploader name and request date.
      - Textarea for optional/required `approval_notes`.
      - **"Approve Document"** button (sets `status='verified'`).
      - **"Request Changes"** button (sets `status='action_required'`).
      - Direct status selector for other options (`submitted`, etc.).
  - If current user is non-approver:
    - Render locked informational banner: *"Awaiting approval by {document.approver_name}. Content is locked until review completes."*
    - Disable editing fields, tags, and new version uploads.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/company/docvault/DocVaultPage.tsx frontend/src/pages/company/docvault/DocumentDrawer.tsx
git commit -m "feat(docvault): add hover quick review action and drawer approval panel"
```

---

### Task 6: Company Dashboard "Pending Approvals" Widget & Notifications Integration

**Files:**
- Modify: `frontend/src/pages/company/Dashboard.tsx`
- Modify: `frontend/src/pages/company/notifications/NotificationsPage.tsx`

**Interfaces:**
- Consumes: `useDocuments({ pending_my_approval: true })`, `useCompanyAuth()`
- Produces: "Pending Approvals" card on Dashboard and 1-click navigation from Notifications

- [ ] **Step 1: Update `frontend/src/pages/company/Dashboard.tsx`**

- Fetch documents requiring current user's approval.
- If pending documents exist:
  - Render a top-level **"Pending Approvals"** Card:
    - Header with amber indicator and count badge.
    - List of pending documents (title, bucket, uploader name, requested relative date).
    - **"Review"** button that navigates directly to `/app/docvault` with `?doc={id}` (opening the drawer automatically).

- [ ] **Step 2: Update `NotificationsPage.tsx`**

- For notification payloads containing `document_id`:
  - Render an interactive click handler or "Open Document" action navigating to `/app/docvault` with that document open.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/company/Dashboard.tsx frontend/src/pages/company/notifications/NotificationsPage.tsx
git commit -m "feat(dashboard): add Pending Approvals widget and notification review navigation"
```

---

### Task 7: Automated Tests & Verification

**Files:**
- Create: `frontend/src/pages/company/docvault/docvault_approvals.test.tsx`
- Modify: `frontend/src/pages/company/docvault/docvault.test.tsx`
- Run: Pytest & Vitest test suites

- [ ] **Step 1: Write frontend unit tests in `docvault_approvals.test.tsx`**

- Test ApproverPicker filters only eligible users.
- Test FinalBadge renders when `is_editable=false`.
- Test Review & Approve hover trigger appears for approver.
- Test DocumentDrawer renders review actions for approver.

- [ ] **Step 2: Run all frontend tests**

Run: `cd frontend && npm run test`
Expected: ALL PASS

- [ ] **Step 3: Run all backend tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/company/docvault/docvault_approvals.test.tsx
git commit -m "test: add frontend and backend test suites for DocVault approval system"
```
