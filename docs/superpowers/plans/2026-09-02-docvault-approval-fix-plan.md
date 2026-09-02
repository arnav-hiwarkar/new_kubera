# DocVault Approval Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the KUB-007 vulnerability by separating the document approval lifecycle transition from metadata editing, and explicitly tracking the approver.

**Architecture:** We will add an `approved_by` column via Alembic migration with a log-based backfill. We will remove approval-related fields from the generic `PATCH` schema and create a dedicated `POST /review` endpoint with strict access controls. The `PATCH` endpoint will also receive ownership-based access controls for metadata editing.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pytest

## Global Constraints

- No changes to unrelated endpoints.
- Preserve all existing comments and docstrings unrelated to code changes.

---

### Task 1: Database Schema and Migration

**Files:**
- Modify: `app/models/docvault.py`
- Create: `alembic/versions/20260902_docvault_approved_by.py` (exact path will depend on alembic revision output)

**Interfaces:**
- Produces: `Document.approved_by` (UUID, nullable, FK to `CompanyUser.id`)

- [ ] **Step 1: Update the Document Model**

```python
# app/models/docvault.py
# Add to Document class:
approved_by = Column(UUID(as_uuid=True), ForeignKey("company_users.id"), nullable=True)
```

- [ ] **Step 2: Generate the Alembic Migration**

Run: `alembic revision --autogenerate -m "Add approved_by to Document"`

- [ ] **Step 3: Add Backfill Logic to Migration**

```python
# Edit the generated alembic file:
from sqlalchemy import text
import json

def upgrade():
    # ... existing add_column ...
    
    # Backfill logic
    conn = op.get_bind()
    conn.execute(text("""
        UPDATE docvault_documents d
        SET approved_by = sub.actor_id
        FROM (
            SELECT entity_id, actor_id,
                   ROW_NUMBER() OVER(PARTITION BY entity_id ORDER BY created_at DESC) as rn
            FROM activity_logs
            WHERE action = 'document.updated'
              AND metadata_->'updated_fields' ? 'status'
        ) sub
        WHERE d.id = sub.entity_id
          AND d.status = 'verified'
          AND sub.rn = 1;
    """))

def downgrade():
    # ... existing drop_column ...
```

- [ ] **Step 4: Run the Migration**

Run: `alembic upgrade head`
Expected: Succeeds without errors.

- [ ] **Step 5: Commit**

```bash
git add app/models/docvault.py alembic/versions/
git commit -m "feat: add approved_by column to Document with backfill"
```

### Task 2: API Schemas Update

**Files:**
- Modify: `app/schemas/docvault.py`
- Modify: `tests/test_docvault_approvals.py`

**Interfaces:**
- Consumes: None
- Produces: `DocumentReviewRequest` schema, updated `DocumentUpdate` schema.

- [ ] **Step 1: Write Schema Tests**

Add to `tests/test_docvault_approvals.py`:
```python
from app.schemas.docvault import DocumentUpdate, DocumentReviewRequest
from pydantic import ValidationError

def test_document_update_schema_removed_status():
    try:
        DocumentUpdate(title="Test", status="verified")
        assert False, "Should raise ValidationError"
    except ValidationError:
        pass

def test_document_review_request_schema():
    req = DocumentReviewRequest(decision="verified", approval_notes="Looks good")
    assert req.decision == "verified"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_docvault_approvals.py::test_document_update_schema_removed_status -v`
Expected: FAIL because status is still in DocumentUpdate.

- [ ] **Step 3: Update Schemas**

Modify `app/schemas/docvault.py`:
Remove `status` and `approval_notes` from `DocumentUpdate`.
Add `DocumentReviewRequest`:
```python
from typing import Literal

class DocumentReviewRequest(BaseModel):
    decision: Literal["verified", "action_required"]
    approval_notes: Optional[str] = Field(None, max_length=1000)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_docvault_approvals.py::test_document_update_schema_removed_status -v`
Run: `pytest tests/test_docvault_approvals.py::test_document_review_request_schema -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/docvault.py tests/test_docvault_approvals.py
git commit -m "refactor: update schemas for docvault approval fix"
```

### Task 3: Router Update - New Review Endpoint

**Files:**
- Modify: `app/routers/docvault.py`
- Modify: `tests/test_docvault_approvals.py`

**Interfaces:**
- Consumes: `DocumentReviewRequest`, `Document.approved_by`
- Produces: `POST /api/v1/docvault/documents/{id}/review` endpoint

- [ ] **Step 1: Write failing tests for Review Endpoint**

Add to `tests/test_docvault_approvals.py` (pseudocode for test structure):
```python
# Add test: test_review_requires_pending_state
# Add test: test_review_rejects_non_approver
# Add test: test_uploader_cannot_approve_own_document
# Update existing test `test_upload_with_approval_request_and_notification` to use POST /review instead of PATCH for status changes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_docvault_approvals.py -v`
Expected: Multiple FAILs due to missing endpoint.

- [ ] **Step 3: Implement POST /review endpoint**

Modify `app/routers/docvault.py` to add `review_document` POST endpoint. It should:
1. Verify document exists and user has bucket access.
2. Verify document status is `pending_approval`.
3. Verify user is `approver_id` or admin.
4. Verify user is NOT `created_by` (unless admin).
5. Update `status` = `decision`, `approval_notes` = `notes`, `approved_by` = `current_user.id`, `approved_at` = `datetime.now`.
6. Log `document.reviewed` activity.
7. Return document response.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_docvault_approvals.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/docvault.py tests/test_docvault_approvals.py
git commit -m "feat: add document review POST endpoint"
```

### Task 4: Router Update - Modify PATCH Endpoint

**Files:**
- Modify: `app/routers/docvault.py`
- Modify: `tests/test_docvault_approvals.py`

**Interfaces:**
- Consumes: Updated `DocumentUpdate` schema
- Produces: Secured `PATCH /api/v1/docvault/documents/{id}` endpoint

- [ ] **Step 1: Write failing tests for PATCH Endpoint Constraints**

Add to `tests/test_docvault_approvals.py`:
```python
# Add test: test_unrelated_user_cannot_edit_document_metadata
# Add test: test_employee_cannot_self_verify (try patching status, should 422)
# Add test: test_only_creator_or_admin_can_unlock (setting is_editable=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_docvault_approvals.py -v`
Expected: FAIL due to missing constraints on PATCH endpoint.

- [ ] **Step 3: Implement PATCH constraints**

Modify `app/routers/docvault.py`:
- Add `_may_edit_document` function (checks if admin, creator, or approver).
- In `update_document` PATCH endpoint:
  - Remove logic related to `status` changes and notification (moved to review endpoint).
  - Check `_may_edit_document`. Raise 403 if false.
  - Check `is_editable` re-enablement logic (only creator or admin). Raise 403 if false.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_docvault_approvals.py -v`
Run: `pytest tests/ -v` (run all tests to ensure no regressions in other areas calling PATCH)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/docvault.py tests/test_docvault_approvals.py
git commit -m "fix: secure docvault PATCH endpoint metadata edits"
```
