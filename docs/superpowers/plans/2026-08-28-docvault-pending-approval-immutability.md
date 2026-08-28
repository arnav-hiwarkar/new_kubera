# DocVault Pending Approval Strict Immutability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strictly lock all metadata, properties (`is_editable`, `title`, `tags`, `bucket_id`, `approver_id`), new version uploads, and deletions on documents in `pending_approval` state against anyone other than the assigned approver and company admins.

**Architecture:** Backend route guardrails in `app/routers/docvault.py` enforce total immutability on `PATCH`, `POST /versions`, and `DELETE` endpoints with `HTTP 403 Forbidden`. Frontend `DocumentDrawer.tsx` dynamically disables all interactive form controls for non-approvers.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, React 18, TanStack Query v5, Vitest, Pytest.

## Global Constraints
- When `doc.status == DocumentStatus.pending_approval`, only the assigned approver (`current_user.id == doc.approver_id`) and company admins (`role == 'admin'`) can modify ANY property, upload new versions, or archive/delete the document.
- All unauthorized mutation attempts by creators or peer employees MUST return `HTTP 403 Forbidden`.

---

### Task 1: Backend Router Enforcement & Pytest Suite

**Files:**
- Modify: `app/routers/docvault.py:475-768`
- Test: `tests/test_docvault_approvals.py`

**Interfaces:**
- Produces:
  - Strict 403 checks in `update_document`, `upload_document_version`, and `delete_document`.

- [ ] **Step 1: Write failing backend test cases in `tests/test_docvault_approvals.py`**

Add tests:
- `test_pending_approval_creator_cannot_edit_properties` (tests `title`, `tags`, `bucket_id`, `is_editable`, `approver_id` return 403)
- `test_pending_approval_creator_cannot_upload_version_or_delete` (tests `POST /versions` and `DELETE` return 403)
- `test_pending_approval_peer_cannot_modify_or_delete` (tests other employee returns 403)
- `test_pending_approval_approver_and_admin_can_modify_and_resolve` (tests approver & admin return 200)

- [ ] **Step 2: Run pytest to verify tests fail**

Run: `.venv/bin/pytest tests/test_docvault_approvals.py -k test_pending_approval_creator`
Expected: FAIL (creator was able to modify `is_editable` or delete)

- [ ] **Step 3: Update `app/routers/docvault.py` route handlers**

In `app/routers/docvault.py`:
1. In `upload_document_version`:
```python
    is_approver_or_admin = (current_user.id == doc.approver_id or is_company_admin(current_user))
    if doc.status == DocumentStatus.pending_approval and not is_approver_or_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot upload new versions while document is pending approval",
        )
```
2. In `update_document`:
```python
    is_approver_or_admin = (current_user.id == doc.approver_id or is_company_admin(current_user))
    if doc.status == DocumentStatus.pending_approval and not is_approver_or_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned approver or an admin can modify, edit, or review this document while approval is pending",
        )
```
3. In `delete_document`:
```python
    is_approver_or_admin = (current_user.id == doc.approver_id or is_company_admin(current_user))
    if doc.status == DocumentStatus.pending_approval and not is_approver_or_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot archive or delete a document while approval is pending",
        )
```

- [ ] **Step 4: Run pytest to verify all tests pass**

Run: `.venv/bin/pytest tests/test_docvault_approvals.py`
Expected: PASS all tests

- [ ] **Step 5: Commit backend changes**

```bash
git add app/routers/docvault.py tests/test_docvault_approvals.py
git commit -m "feat(docvault): enforce strict immutability on documents pending approval"
```

---

### Task 2: Frontend UI Lockout in `DocumentDrawer.tsx`

**Files:**
- Modify: `frontend/src/pages/company/docvault/DocumentDrawer.tsx`

**Interfaces:**
- Produces:
  - Disabled `is_editable` switch and hint when `isPendingApproval && !canReview`.

- [ ] **Step 1: Update `DocumentDrawer.tsx` controls**

In `frontend/src/pages/company/docvault/DocumentDrawer.tsx`:
- Ensure `changeEditable` switch is disabled:
  `disabled={isArchived || update.isPending || (isPendingApproval && !canReview)}`
- Display appropriate hint when pending review:
  `hint={isPendingApproval && !canReview ? 'Locked while pending approval. Only the assigned approver or admin can adjust.' : 'When off, the file is Final: no new versions, renaming, tags or bucket changes.'}`

- [ ] **Step 2: Check TypeScript compile check**

Run: `npx tsc -b` in `frontend`
Expected: PASS with 0 errors

- [ ] **Step 3: Commit frontend UI changes**

```bash
git add frontend/src/pages/company/docvault/DocumentDrawer.tsx
git commit -m "feat(docvault): disable is_editable toggle for non-approvers on pending documents"
```

---

### Task 3: Frontend Tests & Full Verification

**Files:**
- Modify: `frontend/src/pages/company/docvault/docvault_approvals.test.tsx`

- [ ] **Step 1: Add test for non-approver drawer view in `docvault_approvals.test.tsx`**

Verify that for a document in `pending_approval` when the logged-in user is not the approver/admin:
- `Editable` switch is disabled.
- `Upload new version` dropzone is replaced with pending approval notice.

- [ ] **Step 2: Run frontend test suite**

Run: `npm run test` in `frontend`
Expected: PASS (all tests green)

- [ ] **Step 3: Run backend test suite**

Run: `.venv/bin/pytest tests/test_docvault_approvals.py tests/test_docvault.py tests/test_docvault_bucket_rbac.py`
Expected: PASS (all tests green)

- [ ] **Step 4: Run production build check**

Run: `npm run build` in `frontend`
Expected: PASS with exit code 0

- [ ] **Step 5: Commit test updates**

```bash
git add frontend/src/pages/company/docvault/docvault_approvals.test.tsx
git commit -m "test(docvault): add frontend tests for pending approval drawer locks"
```
