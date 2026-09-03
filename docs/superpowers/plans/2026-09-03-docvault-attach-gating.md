# DocVault Attach Gating (Assets, AuditEase, Requirements) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap where attaching an *existing* DocVault document to an asset, an AuditEase query message, or an AuditEase requirement response only checked tenant ownership (`company_id`), not the caller's `docvault` module grant or bucket-level access — and add the missing Assets "attach existing document" UI and the missing AuditEase dedicated download endpoints needed to keep downloads working for module-scoped users who lack DocVault access.

**Architecture:** A single shared backend check, `assert_document_attachable(db, user, document_id)`, is added to a new `app/services/bucket_access.py` (which also hosts the `accessible_bucket_ids`/`can_access_bucket` helpers moved out of `app/routers/docvault.py`) and called from all three attach call sites. Downloads are deliberately NOT gated the same way: Assets already has its own permissive `stream_document` endpoint, and AuditEase gets two new dedicated endpoints (mirroring the existing auditor-side pattern) so a module-scoped company user can read an attachment that's part of their own engagement's record, independent of their personal DocVault/bucket grants. On the frontend, the existing `DocVaultPickerModal` is relocated to a shared location and reused for a new "attach existing document" flow in Assets, and the "Select from DocVault" affordance in both Assets and AuditEase is hidden unless the user has DocVault module access.

**Tech Stack:** FastAPI + SQLAlchemy (async) backend, pytest + httpx `AsyncClient` tests; React + TanStack Query frontend, vitest tests.

## Global Constraints

- Reference spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md` — every task below implements a section of it.
- Downloads of an already-attached document are NOT re-gated on the attacher's or viewer's own DocVault/bucket access — only the *attach* step is gated. This is intentional (confirmed with the user) and must not regress.
- No changes to the compliance/ROC/Secretarial router, the asset `dispose` endpoint, activity log scoping, or the custom-fields router — out of scope.
- Follow existing code style: routers do inline lazy imports for cross-module helpers to avoid import cycles (see `app/routers/asset_documents.py`'s `from app.routers.docvault import handle_file_upload` inside a function body) — new cross-router imports in this plan follow the same pattern.
- Test commands in this plan assume the Docker Compose stack (Postgres + Redis) is already running (`docker compose up -d postgres redis`) and `.venv/bin/python` is the project's Python. Per project convention, run only the specific test files touched by each task — do not run the full backend suite.

---

### Task 1: Extract `app/services/bucket_access.py` and add `assert_document_attachable`

**Files:**
- Create: `app/services/bucket_access.py`
- Modify: `app/routers/docvault.py:81-129` (remove the three function bodies, replace with an import)
- Modify: `app/auth.py:139-157` (extract `user_has_module`)
- Test: `tests/test_document_attach_gating.py` (new file, this task adds the first test class to it)

**Interfaces:**
- Produces (used by Tasks 2, 3, 4):
  - `app/auth.py::user_has_module(user: CompanyUser, module_id: str) -> bool`
  - `app/services/bucket_access.py::accessible_bucket_ids(db: AsyncSession, user: CompanyUser) -> Optional[set[uuid.UUID]]` (moved verbatim from docvault.py)
  - `app/services/bucket_access.py::can_access_bucket(db: AsyncSession, user: CompanyUser, bucket_id: Optional[uuid.UUID]) -> bool` (moved verbatim from docvault.py)
  - `app/services/bucket_access.py::_document_bucket_filter(accessible: Optional[set[uuid.UUID]])` (moved verbatim from docvault.py)
  - `app/services/bucket_access.py::assert_document_attachable(db: AsyncSession, user: CompanyUser, document_id: uuid.UUID) -> Document` — raises `HTTPException(403, "No access to the docvault module")`, `HTTPException(404, "Document not found")`, or `HTTPException(403, "You don't have access to this document")`; returns the `Document` row on success.

- [ ] **Step 1: Extract `user_has_module` in `app/auth.py`**

Replace the body of `require_module` (lines 139-157) with:

```python
def user_has_module(user, module_id: str) -> bool:
    """True if `user` may use `module_id` — admins always pass."""
    from app.models.company import UserRole

    if user.role == UserRole.admin:
        return True
    return module_id in (user.accessible_modules or [])


def require_module(module_id: str):
    """Dependency factory: 403 unless the user has this module granted.

    `accessible_modules` was historically enforced only in the browser
    (ModuleGuard.tsx), which made it a UX affordance rather than a boundary.
    Endpoints that rely on it for authorization must use this. Admins always pass.
    """
    from app.models.company import CompanyUser

    async def checker(user: CompanyUser = Depends(get_current_company_user)):
        if not user_has_module(user, module_id):
            raise HTTPException(
                status_code=403, detail=f"No access to the {module_id} module"
            )
        return user

    return checker
```

- [ ] **Step 2: Run the existing module-enforcement suite to confirm no regression**

Run: `.venv/bin/python -m pytest tests/test_module_enforcement.py -q`
Expected: PASS (12 passed) — `require_module`'s observable behavior is unchanged.

- [ ] **Step 3: Create `app/services/bucket_access.py`**

```python
"""Bucket-level access checks shared across DocVault and every other router that
attaches an existing DocVault document (Assets, AuditEase). See
docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md."""
import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import user_has_module
from app.models.company import CompanyUser, UserRole
from app.models.docvault import Bucket, BucketAccessGrant, BucketVisibility, Document


async def accessible_bucket_ids(db: AsyncSession, user: CompanyUser) -> Optional[set[uuid.UUID]]:
    """Bucket ids the user may see within their company.

    Returns None for admins (unrestricted — no filtering should be applied).
    For non-admins, returns the set of bucket ids that are either visible to
    everyone or explicitly granted to the user. A restricted bucket is visible
    strictly to admins + the users on its access list — creating a bucket does
    not, on its own, grant continued access once it is restricted.
    """
    if user.role == UserRole.admin:
        return None
    result = await db.execute(
        select(Bucket.id)
        .outerjoin(
            BucketAccessGrant,
            and_(
                BucketAccessGrant.bucket_id == Bucket.id,
                BucketAccessGrant.company_user_id == user.id,
            ),
        )
        .where(
            and_(
                Bucket.company_id == user.company_id,
                or_(
                    Bucket.visibility == BucketVisibility.everyone,
                    BucketAccessGrant.id.isnot(None),
                ),
            )
        )
    )
    return set(result.scalars().all())


def _document_bucket_filter(accessible: Optional[set[uuid.UUID]]):
    """SQL predicate limiting documents to accessible buckets. Uncategorized
    documents (no bucket) are visible to everyone. None => no restriction."""
    if accessible is None:
        return None
    return or_(Document.bucket_id.is_(None), Document.bucket_id.in_(accessible))


async def can_access_bucket(db: AsyncSession, user: CompanyUser, bucket_id: Optional[uuid.UUID]) -> bool:
    """Whether the user may use `bucket_id` (None = uncategorized, always allowed)."""
    if bucket_id is None:
        return True
    accessible = await accessible_bucket_ids(db, user)
    if accessible is None:
        return True
    return bucket_id in accessible


async def assert_document_attachable(
    db: AsyncSession, user: CompanyUser, document_id: uuid.UUID
) -> Document:
    """Raise 403/404 unless `user` may attach `document_id` to something outside
    DocVault (an asset, an AuditEase query, a requirement response). Admins
    bypass both the module and bucket checks."""
    if not user_has_module(user, "docvault"):
        raise HTTPException(status_code=403, detail="No access to the docvault module")
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.company_id == user.company_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await can_access_bucket(db, user, doc.bucket_id):
        raise HTTPException(status_code=403, detail="You don't have access to this document")
    return doc
```

- [ ] **Step 4: Point `app/routers/docvault.py` at the shared module**

Replace lines 81-129 of `app/routers/docvault.py` (the three function definitions) with:

```python
from app.services.bucket_access import accessible_bucket_ids, can_access_bucket, _document_bucket_filter
```

Place this import with the other local imports near the top of the file (alongside the existing `from app.auth import ...` line, `app/routers/docvault.py:13`) rather than inline where the functions used to live — the ~15 call sites later in the file (`accessible_bucket_ids(...)`, `can_access_bucket(...)`, `_document_bucket_filter(...)`) are unchanged since the names now resolve via import instead of local definition.

- [ ] **Step 5: Run the full DocVault test suite to confirm no regression**

Run: `.venv/bin/python -m pytest tests/test_docvault.py -q`
Expected: PASS, same pass count as before this change (run `git stash` + rerun beforehand if you need a baseline count).

- [ ] **Step 6: Write the failing unit tests for `assert_document_attachable`**

Create `tests/test_document_attach_gating.py`:

```python
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.company import CompanyUser
from app.models.docvault import Bucket, BucketAccessGrant, BucketVisibility, Document
from app.services.bucket_access import assert_document_attachable
from tests.conftest import create_test_company, get_company_token


async def _make_employee(client: AsyncClient, admin_headers: dict, email: str, modules: list[str]) -> dict:
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": email,
            "password": "Valid1!Pass",
            "full_name": email.split("@")[0],
            "role": "employee",
            "accessible_modules": modules,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _user_by_email(db, email: str) -> CompanyUser:
    result = await db.execute(select(CompanyUser).where(CompanyUser.email == email))
    return result.scalar_one()


async def _login_headers(client: AsyncClient, email: str, password: str = "Valid1!Pass") -> dict:
    resp = await client.post("/api/v1/auth/company/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_assert_document_attachable_matrix(client: AsyncClient, db):
    """admin bypass; no docvault module -> 403; docvault but wrong bucket -> 403;
    docvault + bucket access -> returns the document."""
    await create_test_company(client, email="attach-admin@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='attach-admin@testco.com')}"}

    await _make_employee(client, admin_headers, "no-docvault@testco.com", ["assets"])
    await _make_employee(client, admin_headers, "with-docvault@testco.com", ["assets", "docvault"])

    admin = await _user_by_email(db, "attach-admin@testco.com")
    no_docvault_user = await _user_by_email(db, "no-docvault@testco.com")
    with_docvault_user = await _user_by_email(db, "with-docvault@testco.com")

    bucket = Bucket(
        company_id=admin.company_id,
        name="Restricted Bucket",
        visibility=BucketVisibility.restricted,
        created_by=admin.id,
    )
    db.add(bucket)
    await db.flush()

    document = Document(
        company_id=admin.company_id,
        bucket_id=bucket.id,
        title="Secret",
        created_by=admin.id,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # No docvault module at all.
    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, no_docvault_user, document.id)
    assert exc_info.value.status_code == 403
    assert "docvault module" in exc_info.value.detail

    # Has docvault module, but the bucket is restricted and ungranted.
    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, with_docvault_user, document.id)
    assert exc_info.value.status_code == 403
    assert "access to this document" in exc_info.value.detail

    # Admin bypasses both checks regardless of grants.
    result = await assert_document_attachable(db, admin, document.id)
    assert result.id == document.id

    # Grant bucket access -> now succeeds for the non-admin too.
    db.add(BucketAccessGrant(bucket_id=bucket.id, company_user_id=with_docvault_user.id))
    await db.commit()
    result = await assert_document_attachable(db, with_docvault_user, document.id)
    assert result.id == document.id


@pytest.mark.asyncio
async def test_assert_document_attachable_wrong_company_404(client: AsyncClient, db):
    """A document belonging to a different company must 404, not leak existence."""
    await create_test_company(client, email="companyA@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='companyA@testco.com')}"}
    employee = await _make_employee(client, admin_headers, "userA@testco.com", ["docvault"])
    user_a = await _user_by_email(db, "userA@testco.com")

    await create_test_company(client, name="OtherCo", email="admin@otherco.com")
    other_admin = await _user_by_email(db, "admin@otherco.com")
    other_doc = Document(company_id=other_admin.company_id, title="Not yours", created_by=other_admin.id)
    db.add(other_doc)
    await db.commit()
    await db.refresh(other_doc)

    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, user_a, other_doc.id)
    assert exc_info.value.status_code == 404
```

- [ ] **Step 7: Run the new tests to verify they fail before the helper existed... then pass now that it does**

Run: `.venv/bin/python -m pytest tests/test_document_attach_gating.py -q`
Expected: PASS (2 passed) — the helper was written in Step 3, so this confirms it behaves correctly end-to-end against a real database rather than verifying a red-then-green cycle (the function already exists by the time this test file is authored in a working tree; this is the acceptance check for Task 1).

- [ ] **Step 8: Commit**

```bash
git add app/services/bucket_access.py app/auth.py app/routers/docvault.py tests/test_document_attach_gating.py
git commit -m "feat(docvault): extract shared bucket-access helper and assert_document_attachable"
```

---

### Task 2: Gate Assets' existing-document attach endpoints

**Files:**
- Modify: `app/routers/asset_documents.py:106-111` (remove `_verify_document`), `:207-226`, `:258-276` (use the new helper)
- Test: `tests/test_document_attach_gating.py` (append)

**Interfaces:**
- Consumes: `app.services.bucket_access.assert_document_attachable(db, user, document_id) -> Document` (Task 1)
- No new interfaces produced.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_document_attach_gating.py`:

```python
async def _leaf_category(client: AsyncClient, admin_headers: dict) -> dict:
    resp = await client.post(
        "/api/v1/asset-masters/categories", json={"name": "Plant & Machinery"}, headers=admin_headers
    )
    assert resp.status_code == 201, resp.text
    parent = resp.json()
    sub_resp = await client.post(
        "/api/v1/asset-masters/categories",
        json={"name": "Machines", "parent_id": parent["id"]},
        headers=admin_headers,
    )
    assert sub_resp.status_code == 201, sub_resp.text
    return sub_resp.json()


async def _upload_docvault_document(
    client: AsyncClient, headers: dict, title: str, bucket_id: str | None = None
) -> str:
    data = {"title": title}
    if bucket_id:
        data["bucket_id"] = bucket_id
    files = {"file": (f"{title}.txt", b"contents", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data=data, files=files, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _restrict_bucket(client: AsyncClient, admin_headers: dict, name: str, allowed_user_ids: list[str]) -> str:
    resp = await client.post("/api/v1/docvault/buckets", json={"name": name}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    bucket_id = resp.json()["id"]
    patch = await client.patch(
        f"/api/v1/docvault/buckets/{bucket_id}/access",
        json={"visibility": "restricted", "user_ids": allowed_user_ids},
        headers=admin_headers,
    )
    assert patch.status_code == 200, patch.text
    return bucket_id


@pytest.mark.asyncio
async def test_attach_asset_document_requires_docvault_module(client: AsyncClient):
    await create_test_company(client, email="asset-admin@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='asset-admin@testco.com')}"}
    category = await _leaf_category(client, admin_headers)
    document_id = await _upload_docvault_document(client, admin_headers, "Invoice")

    quick_add = await client.post(
        "/api/v1/assets/quick-add",
        json={"asset_name": "Laptop", "category_id": category["id"], "quantity": 1},
        headers=admin_headers,
    )
    assert quick_add.status_code == 201, quick_add.text
    asset_id = quick_add.json()["first_asset_id"]

    await _make_employee(client, admin_headers, "assets-only@testco.com", ["assets"])
    assets_only_headers = await _login_headers(client, "assets-only@testco.com")

    resp = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": document_id, "doc_role": "asset_photo"},
        headers=assets_only_headers,
    )
    assert resp.status_code == 403, resp.text
    assert "docvault module" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_attach_asset_document_requires_bucket_access(client: AsyncClient):
    await create_test_company(client, email="asset-admin2@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='asset-admin2@testco.com')}"}
    category = await _leaf_category(client, admin_headers)

    quick_add = await client.post(
        "/api/v1/assets/quick-add",
        json={"asset_name": "Laptop", "category_id": category["id"], "quantity": 1},
        headers=admin_headers,
    )
    asset_id = quick_add.json()["first_asset_id"]

    scoped = await _make_employee(client, admin_headers, "scoped@testco.com", ["assets", "docvault"])
    scoped_headers = await _login_headers(client, "scoped@testco.com")

    restricted_bucket_id = await _restrict_bucket(client, admin_headers, "Admin Only", [])
    document_id = await _upload_docvault_document(client, admin_headers, "Confidential", restricted_bucket_id)

    denied = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": document_id, "doc_role": "asset_photo"},
        headers=scoped_headers,
    )
    assert denied.status_code == 403, denied.text
    assert "access to this document" in denied.json()["detail"]

    # Grant bucket access -> attach now succeeds.
    scoped_user_id = scoped["id"]
    grant = await client.patch(
        f"/api/v1/docvault/buckets/{restricted_bucket_id}/access",
        json={"visibility": "restricted", "user_ids": [scoped_user_id]},
        headers=admin_headers,
    )
    assert grant.status_code == 200, grant.text

    allowed = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": document_id, "doc_role": "asset_photo"},
        headers=scoped_headers,
    )
    assert allowed.status_code == 201, allowed.text
    link_id = allowed.json()["id"]

    # Regression: the assets-only download endpoint stays permissive -- an
    # assets-only user with no docvault access at all can still stream the file.
    await _make_employee(client, admin_headers, "download-only@testco.com", ["assets"])
    download_only_headers = await _login_headers(client, "download-only@testco.com")
    stream = await client.get(f"/api/v1/asset-documents/{link_id}/thumbnail", headers=download_only_headers)
    assert stream.status_code == 200, stream.text
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "attach_asset_document" -v`
Expected: FAIL — `attach_asset_document` still uses `_verify_document`, which only checks `company_id`, so `test_attach_asset_document_requires_docvault_module` gets 201 instead of the expected 403.

- [ ] **Step 3: Update `app/routers/asset_documents.py`**

Add the import near the top of the file (with the other `app.*` imports around line 23):

```python
from app.services.bucket_access import assert_document_attachable
```

Delete the `_verify_document` function (lines 106-111).

In `attach_asset_document` (around line 207-226), replace:

```python
    await _verify_document(db, body.document_id, current_user.company_id)
```

with:

```python
    await assert_document_attachable(db, current_user, body.document_id)
```

Make the identical replacement in `attach_acquisition_document` (around line 258-276).

Leave `upload_asset_document`, `upload_acquisition_document`, and `stream_document` untouched — they don't select an existing document by id, so this check does not apply.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "attach_asset_document" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full asset_documents-adjacent suite for regressions**

Run: `.venv/bin/python -m pytest tests/test_assets.py tests/test_document_attach_gating.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/asset_documents.py tests/test_document_attach_gating.py
git commit -m "fix(assets): gate existing-document attach on docvault module and bucket access"
```

---

### Task 3: Gate AuditEase's query-message attach and add dedicated download endpoints

**Files:**
- Modify: `app/routers/auditease.py` (imports near top; `add_query_message` at ~1441-1487; two new endpoints)
- Modify: `app/services/document_access.py` (append `company_user_can_access_engagement_document`)
- Test: `tests/test_document_attach_gating.py` (append)

**Interfaces:**
- Consumes: `assert_document_attachable` (Task 1)
- Produces (used by Task 5, frontend): `GET /api/v1/auditease/documents/{document_id}` (response model `DocumentResponse` from `app.schemas.docvault`), `GET /api/v1/auditease/documents/{document_id}/download` (raw file response)
- Produces (service function): `app/services/document_access.py::company_user_can_access_engagement_document(db: AsyncSession, company_id: uuid.UUID, document_id: uuid.UUID) -> Optional[Document]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_document_attach_gating.py`:

```python
async def _create_engagement_with_accepted_auditor(client: AsyncClient, co_headers: dict, aud_email: str) -> tuple[str, dict]:
    from tests.conftest import create_test_auditor, get_auditor_token

    eng_resp = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co_headers)
    assert eng_resp.status_code == 201, eng_resp.text
    engagement_id = eng_resp.json()["id"]

    await create_test_auditor(client, email=aud_email, password="Valid1!Pass")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email=aud_email, password='Valid1!Pass')}"}

    invite = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/auditors/invite",
        json={"email": aud_email},
        headers=co_headers,
    )
    assert invite.status_code in (200, 201), invite.text
    accept = await client.post(f"/api/v1/auditor/engagements/{engagement_id}/accept", headers=aud_headers)
    assert accept.status_code == 200, accept.text
    return engagement_id, aud_headers


@pytest.mark.asyncio
async def test_add_query_message_attach_requires_docvault_module(client: AsyncClient):
    await create_test_company(client, email="ae-admin@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='ae-admin@testco.com')}"}
    engagement_id, aud_headers = await _create_engagement_with_accepted_auditor(
        client, admin_headers, "ae-auditor@aud.com"
    )
    query_resp = await client.post(
        f"/api/v1/auditor/engagements/{engagement_id}/queries",
        data={"initial_message": "Please clarify"},
        headers=aud_headers,
    )
    assert query_resp.status_code == 201, query_resp.text
    query_id = query_resp.json()["id"]

    document_id = await _upload_docvault_document(client, admin_headers, "Report")

    await _make_employee(client, admin_headers, "ae-only@testco.com", ["auditease"])
    auditease_only_headers = await _login_headers(client, "ae-only@testco.com")

    resp = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/queries/{query_id}/messages",
        data={"text": "See attached", "attached_document_id": document_id},
        headers=auditease_only_headers,
    )
    assert resp.status_code == 403, resp.text
    assert "docvault module" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_query_attachment_download_permissive_for_module_scoped_user(client: AsyncClient):
    """Once attached (by someone with proper docvault+bucket access), any
    auditease-scoped company user can download it via the new endpoint even
    with zero docvault access -- and the generic docvault route still 403s them."""
    await create_test_company(client, email="ae-admin2@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='ae-admin2@testco.com')}"}
    engagement_id, aud_headers = await _create_engagement_with_accepted_auditor(
        client, admin_headers, "ae-auditor2@aud.com"
    )
    query_resp = await client.post(
        f"/api/v1/auditor/engagements/{engagement_id}/queries",
        data={"initial_message": "Please clarify"},
        headers=aud_headers,
    )
    query_id = query_resp.json()["id"]
    document_id = await _upload_docvault_document(client, admin_headers, "Report2")

    attach = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/queries/{query_id}/messages",
        data={"text": "See attached", "attached_document_id": document_id},
        headers=admin_headers,
    )
    assert attach.status_code == 200, attach.text

    await _make_employee(client, admin_headers, "ae-viewer@testco.com", ["auditease"])
    auditease_only_headers = await _login_headers(client, "ae-viewer@testco.com")

    new_route = await client.get(f"/api/v1/auditease/documents/{document_id}/download", headers=auditease_only_headers)
    assert new_route.status_code == 200, new_route.text

    generic_route = await client.get(f"/api/v1/docvault/documents/{document_id}/download", headers=auditease_only_headers)
    assert generic_route.status_code == 403, generic_route.text
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "query_message or query_attachment" -v`
Expected: FAIL — attach isn't gated yet, and `/api/v1/auditease/documents/...` doesn't exist yet (404 on route, not 200).

- [ ] **Step 3: Add `company_user_can_access_engagement_document` to `app/services/document_access.py`**

Append at the end of the file:

```python
async def company_user_can_access_engagement_document(
    db: AsyncSession, company_id: uuid.UUID, document_id: uuid.UUID
) -> Optional[Document]:
    """A document any company user may read via AuditEase, because it is
    attached to a query message or a requirement-response submission belonging
    to an engagement of this company -- independent of the caller's own
    DocVault module or bucket access. Mirrors auditor_can_access_document: once
    a document is attached to a query or requirement, it becomes part of that
    record for everyone with legitimate access to the engagement."""
    res = await db.execute(select(Document).where(Document.id == document_id, Document.company_id == company_id))
    doc = res.scalar_one_or_none()
    if doc is None:
        return None

    res_req = await db.execute(
        select(RequirementResponseDocument.id)
        .join(RequirementResponse, RequirementResponse.id == RequirementResponseDocument.response_id)
        .join(RequirementRequest, RequirementRequest.id == RequirementResponse.requirement_id)
        .join(AuditEngagement, AuditEngagement.id == RequirementRequest.engagement_id)
        .where(
            RequirementResponseDocument.document_id == document_id,
            AuditEngagement.company_id == company_id,
        )
        .limit(1)
    )
    if res_req.first():
        return doc

    res_q = await db.execute(
        select(QueryMessage.id)
        .join(Query, Query.id == QueryMessage.query_id)
        .join(AuditEngagement, AuditEngagement.id == Query.engagement_id)
        .where(
            QueryMessage.attached_document_id == document_id,
            AuditEngagement.company_id == company_id,
        )
        .limit(1)
    )
    if res_q.first():
        return doc

    return None
```

This needs `RequirementResponse`, `RequirementRequest`, `RequirementResponseDocument` imported at the top of `app/services/document_access.py` — add them to the existing `from app.models.auditease import (...)` block (which already imports `AuditEngagement, AuditorEngagementGrant, GrantStatus, EngagementStatus, RequirementRequest, RequirementResponse, RequirementResponseDocument, Query, QueryMessage` per the current file — verify and add any missing name; `RequirementRequest`, `RequirementResponse`, `RequirementResponseDocument`, `Query`, `QueryMessage` are already imported).

- [ ] **Step 4: Gate `add_query_message` in `app/routers/auditease.py`**

In the imports block near the top of the file, add:

```python
from app.services.bucket_access import assert_document_attachable
```

Also hoist the currently-inline `from app.services import document_access as doc_access` (line 1461) to a top-level import, since it will now be used by three endpoints in this file:

```python
from app.services import document_access as doc_access
```

In `add_query_message`, replace:

```python
    if attached_document_id:
        from app.models.docvault import Document
        doc_res = await db.execute(select(Document).where(and_(Document.id == attached_document_id, Document.company_id == current_user.company_id)))
        if not doc_res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Document not found")

        await doc_access.grant_document_access_to_auditors(db, engagement_id, attached_document_id)
        final_attached_document_id = attached_document_id
```

with:

```python
    if attached_document_id:
        await assert_document_attachable(db, current_user, attached_document_id)
        await doc_access.grant_document_access_to_auditors(db, engagement_id, attached_document_id)
        final_attached_document_id = attached_document_id
```

- [ ] **Step 5: Add the two new download endpoints to `app/routers/auditease.py`**

Add module-level imports (alongside the existing top-of-file imports):

```python
from fastapi import Response  # add Response to the existing fastapi import line
from sqlalchemy.orm import selectinload  # already imported, no change needed
from app.models.docvault import Document, DocumentVersion
from app.schemas.docvault import DocumentResponse
from app.encryption import decrypt_dek, decrypt_file_data
```

Add the two endpoints (near `add_query_message`, since they serve the same document-attachment concern):

```python
@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_engagement_document(
    document_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Metadata for a document attached to one of this company's AuditEase
    queries or requirement submissions -- independent of the caller's own
    DocVault access. Mirrors GET /api/v1/auditor/documents/{id}."""
    doc = await doc_access.company_user_can_access_engagement_document(
        db, current_user.company_id, document_id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await db.execute(
        select(Document).options(selectinload(Document.versions)).where(Document.id == document_id)
    )
    return result.scalar_one()


@router.get("/documents/{document_id}/download")
async def download_engagement_document(
    document_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Decrypt and stream a document attached to one of this company's AuditEase
    queries or requirement submissions. Mirrors GET /api/v1/auditor/documents/{id}/download."""
    import aiofiles

    from app.routers.docvault import get_company_kek

    doc = await doc_access.company_user_can_access_engagement_document(
        db, current_user.company_id, document_id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await db.execute(
        select(Document).options(selectinload(Document.versions)).where(Document.id == document_id)
    )
    doc_full = result.scalar_one()
    if not doc_full.current_version_id:
        raise HTTPException(status_code=404, detail="No versions available")
    version = next((v for v in doc_full.versions if v.id == doc_full.current_version_id), None)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")

    company_kek = await get_company_kek(db, doc_full.company_id)
    raw_dek = decrypt_dek(version.encrypted_dek, version.dek_nonce, company_kek)
    async with aiofiles.open(version.storage_path, "rb") as f:
        blob = await f.read()
    plaintext = decrypt_file_data(blob[12:], blob[:12], raw_dek)
    return Response(
        content=plaintext,
        media_type=version.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{version.original_filename}"'},
    )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "query_message or query_attachment" -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Run the full AuditEase suite for regressions**

Run: `.venv/bin/python -m pytest tests/test_auditease.py tests/test_document_attach_gating.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/routers/auditease.py app/services/document_access.py tests/test_document_attach_gating.py
git commit -m "feat(auditease): gate query-message attach and add dedicated document download endpoints"
```

---

### Task 4: Gate requirement-response document submission

**Files:**
- Modify: `app/services/requirements.py:45-63` (`validate_document_ids`), `:66-85` (`create_submission`)
- Modify: `app/routers/auditease.py:1408-1410` (`respond_requirement` call site)
- Test: `tests/test_document_attach_gating.py` (append)

**Interfaces:**
- Consumes: `assert_document_attachable` (Task 1)
- Modifies existing interface: `validate_document_ids(db, company_id, document_ids)` becomes `validate_document_ids(db, company_id, document_ids, user)`; `create_submission(...)` gains no new parameter (it already receives everything needed via its existing `user_id` param — see Step 2, it needs the full `CompanyUser`, not just the id, so it gains a `user: CompanyUser` keyword argument).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_document_attach_gating.py`:

```python
@pytest.mark.asyncio
async def test_respond_requirement_document_ids_requires_docvault_module(client: AsyncClient):
    await create_test_company(client, email="req-admin@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='req-admin@testco.com')}"}
    engagement_id, aud_headers = await _create_engagement_with_accepted_auditor(
        client, admin_headers, "req-auditor@aud.com"
    )
    req_resp = await client.post(
        f"/api/v1/auditor/engagements/{engagement_id}/requirement-requests",
        json={"description": "Please upload bank reconciliation"},
        headers=aud_headers,
    )
    assert req_resp.status_code == 201, req_resp.text
    req_id = req_resp.json()["id"]

    document_id = await _upload_docvault_document(client, admin_headers, "BankRecon")

    await _make_employee(client, admin_headers, "req-only@testco.com", ["auditease"])
    auditease_only_headers = await _login_headers(client, "req-only@testco.com")

    resp = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Attached", "document_ids": [document_id]},
        headers=auditease_only_headers,
    )
    assert resp.status_code == 403, resp.text
    assert "docvault module" in resp.json()["detail"]
```

- [ ] **Step 2: Run to verify the test fails**

Run: `.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "respond_requirement_document_ids" -v`
Expected: FAIL — currently 200, since `validate_document_ids` only checks `company_id`.

- [ ] **Step 3: Update `app/services/requirements.py`**

Add the import at the top of the file:

```python
from app.models.company import CompanyUser
from app.services.bucket_access import assert_document_attachable
```

(`CompanyUser` is likely already imported — check the existing `from app.models.company import CompanyUser` line at the top of the file before adding a duplicate.)

Replace `validate_document_ids`:

```python
async def validate_document_ids(
    db: AsyncSession, company_id: uuid.UUID, document_ids: Sequence[uuid.UUID], user: CompanyUser
) -> None:
    """Raise HTTPException unless EVERY id is a document of `company_id` that
    `user` may attach (has the docvault module and bucket access to it).
    All-or-nothing: one bad id rejects the whole submission."""
    if not document_ids:
        return
    unique_ids = list(set(document_ids))
    for document_id in unique_ids:
        await assert_document_attachable(db, user, document_id)
```

Update `create_submission`'s signature to accept `user: CompanyUser` and pass it through:

```python
async def create_submission(
    db: AsyncSession,
    *,
    req: RequirementRequest,
    engagement_id: uuid.UUID,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    user: CompanyUser,
    text_answer: Optional[str],
    files: Sequence[UploadFile],
    document_ids: Sequence[uuid.UUID],
) -> RequirementResponse:
```

and change the call inside it:

```python
    if document_ids:
        await validate_document_ids(db, company_id, document_ids, user)
```

- [ ] **Step 4: Update the call site in `app/routers/auditease.py`**

In `respond_requirement`, change the `create_submission(...)` call to also pass `user=current_user`:

```python
    submission = await create_submission(
        db, req=req, engagement_id=engagement_id, company_id=current_user.company_id,
        user_id=current_user.id, user=current_user, text_answer=text, files=ups, document_ids=docs)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "respond_requirement_document_ids" -v`
Expected: PASS

- [ ] **Step 6: Run the requirement-submission and auditease suites for regressions**

Run: `.venv/bin/python -m pytest tests/test_requirement_submissions.py tests/test_auditease.py tests/test_document_attach_gating.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/requirements.py app/routers/auditease.py tests/test_document_attach_gating.py
git commit -m "fix(auditease): gate requirement-response document_ids on docvault module and bucket access"
```

---

### Task 5: Relocate and generalize `DocVaultPickerModal`

**Files:**
- Create: `frontend/src/components/docvault/DocVaultPickerModal.tsx` (moved + generalized)
- Delete: `frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx`
- Modify: `frontend/src/components/auditease/requirements/RespondPanel.tsx:20` (import path only)
- Modify: `frontend/src/pages/company/auditease/QueriesTab.tsx:8` (import path only)
- Test: none new (existing manual/behavioral coverage is unchanged; this is a pure relocation + additive props)

**Interfaces:**
- Produces (used by Task 7): `DocVaultPickerModal` now accepts two additional optional props: `title?: string` (default `"Select Documents from DocVault"`) and `confirmLabel?: string` (default `"Attach Selected"` — used in the footer button, which currently reads `Attach Selected ({selectedCount})`).

- [ ] **Step 1: Create the new file with generalized props**

Read the current file at `frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx` (628 lines) and write it to `frontend/src/components/docvault/DocVaultPickerModal.tsx` with these changes only:

1. Extend the props interface (currently at lines 24-30):

```tsx
interface DocVaultPickerModalProps {
  open: boolean
  onClose: () => void
  selectedDocIds: string[]
  onConfirm: (selectedIds: string[]) => void
  multiple?: boolean
  title?: string
  confirmLabel?: string
}
```

2. Destructure the new props with defaults in the component signature (currently lines 32-38):

```tsx
export const DocVaultPickerModal: React.FC<DocVaultPickerModalProps> = ({
  open,
  onClose,
  selectedDocIds: initialSelected,
  onConfirm,
  multiple = true,
  title = 'Select Documents from DocVault',
  confirmLabel = 'Attach Selected',
}) => {
```

3. Use `title` where the literal was hardcoded (currently line 189):

```tsx
      title={title}
```

4. Use `confirmLabel` where the literal was hardcoded (currently line 621):

```tsx
              <span>{confirmLabel} ({selectedCount})</span>
```

Every other line is copied verbatim — no other behavior change.

- [ ] **Step 2: Delete the old file**

```bash
git rm frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx
```

- [ ] **Step 3: Update the two existing import sites**

In `frontend/src/components/auditease/requirements/RespondPanel.tsx:20`, change:

```tsx
import { DocVaultPickerModal } from './DocVaultPickerModal'
```

to:

```tsx
import { DocVaultPickerModal } from '@/components/docvault/DocVaultPickerModal'
```

In `frontend/src/pages/company/auditease/QueriesTab.tsx:8`, change:

```tsx
import { DocVaultPickerModal } from '@/components/auditease/requirements/DocVaultPickerModal'
```

to:

```tsx
import { DocVaultPickerModal } from '@/components/docvault/DocVaultPickerModal'
```

- [ ] **Step 4: Type-check and run existing vitest suites touching these files**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

Run: `cd frontend && npx vitest run src/components/auditease src/pages/company/auditease 2>&1 | tail -40` (adjust path if these directories have no existing spec files — if so, this step just confirms no import errors surface at build time via the tsc check above)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/docvault/DocVaultPickerModal.tsx frontend/src/components/auditease/requirements/RespondPanel.tsx frontend/src/pages/company/auditease/QueriesTab.tsx
git commit -m "refactor(frontend): relocate DocVaultPickerModal to a shared location"
```

---

### Task 6: Gate the "Select from DocVault" option in AuditEase on DocVault access

**Files:**
- Modify: `frontend/src/components/auditease/requirements/RespondPanel.tsx`
- Modify: `frontend/src/pages/company/auditease/QueriesTab.tsx`
- Test: Create `frontend/src/components/auditease/requirements/RespondPanel.docvault-gate.test.tsx`, Create `frontend/src/pages/company/auditease/QueriesTab.docvault-gate.test.tsx`

**Interfaces:**
- Consumes: `hasModuleAccess(profile, moduleId)` from `@/auth/company/modules.ts`, `useCompanyAuth()` from `@/auth/company` (returns `{ profile, ... }`, `profile.accessible_modules: string[]`, `profile.role: string`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/auditease/requirements/RespondPanel.docvault-gate.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RespondPanel } from './RespondPanel'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: (globalThis as any).__testProfile }),
}))

vi.mock('@/api/hooks/docvault', () => ({
  useDocuments: () => ({ data: [] }),
}))

vi.mock('@/api/hooks/auditease', () => ({
  useRespondToRequirement: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

const baseReq = {
  id: 'req-1',
  status: 'open',
  requirement_id_str: 'REQ-001',
  submission_count: 0,
} as any

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient()
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('RespondPanel DocVault picker gate', () => {
  it('hides "Select from DocVault" when the user lacks docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['auditease'] }
    renderWithProviders(<RespondPanel engagementId="eng-1" req={baseReq} />)
    expect(screen.queryByText('Select from DocVault')).not.toBeInTheDocument()
  })

  it('shows "Select from DocVault" when the user has docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['auditease', 'docvault'] }
    renderWithProviders(<RespondPanel engagementId="eng-1" req={baseReq} />)
    expect(screen.getByText('Select from DocVault')).toBeInTheDocument()
  })
})
```

Create `frontend/src/pages/company/auditease/QueriesTab.docvault-gate.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { QueriesTab } from './QueriesTab'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: (globalThis as any).__testProfile }),
}))

vi.mock('@/api/hooks/docvault', () => ({
  useDocuments: () => ({ data: [] }),
  useDownloadDocument: () => ({ mutateAsync: vi.fn() }),
}))

vi.mock('@/api/hooks/auditease', () => ({
  useListQueries: () => ({
    data: [
      {
        id: 'q-1',
        status: 'open',
        requirement_id: null,
        created_at: new Date().toISOString(),
        messages: [{ id: 'm-1', sender_type: 'company_user', text: 'hi', created_at: new Date().toISOString() }],
      },
    ],
    isLoading: false,
  }),
  useAddQueryMessage: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient()
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('QueriesTab DocVault picker gate', () => {
  it('hides "Select from DocVault" when the user lacks docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['auditease'] }
    renderWithProviders(<QueriesTab engagementId="eng-1" />)
    fireEvent.click(screen.getByText(/No messages|hi/))
    expect(screen.queryByText('Select from DocVault')).not.toBeInTheDocument()
  })

  it('shows "Select from DocVault" when the user has docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['auditease', 'docvault'] }
    renderWithProviders(<QueriesTab engagementId="eng-1" />)
    fireEvent.click(screen.getByText(/No messages|hi/))
    expect(screen.getByText('Select from DocVault')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify the tests fail**

Run: `cd frontend && npx vitest run RespondPanel.docvault-gate QueriesTab.docvault-gate`
Expected: FAIL — the button currently renders unconditionally regardless of `accessible_modules`.

- [ ] **Step 3: Gate the button in `RespondPanel.tsx`**

Add the import:

```tsx
import { useCompanyAuth } from '@/auth/company'
import { hasModuleAccess } from '@/auth/company/modules'
```

Inside the component body, after the existing `useDocuments()` call:

```tsx
  const { profile } = useCompanyAuth()
  const canBrowseDocVault = hasModuleAccess(profile, 'docvault')
```

Wrap the "Select from DocVault" button (currently lines 250-259):

```tsx
            {canBrowseDocVault && (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setShowVaultPickerModal(true)}
                className="gap-1.5 text-xs h-8 shadow-xs"
              >
                <FolderPlus className="w-3.5 h-3.5 text-accent" />
                <span>Select from DocVault</span>
              </Button>
            )}
```

- [ ] **Step 4: Gate the button in `QueriesTab.tsx`**

Add the import:

```tsx
import { useCompanyAuth } from '@/auth/company'
import { hasModuleAccess } from '@/auth/company/modules'
```

Inside the component body:

```tsx
  const { profile } = useCompanyAuth()
  const canBrowseDocVault = hasModuleAccess(profile, 'docvault')
```

Wrap the "Select from DocVault" button (currently lines 185-193):

```tsx
                    {canBrowseDocVault && (
                      <button
                        type="button"
                        onClick={() => setShowPickerModal(true)}
                        disabled={addMsg.isPending}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded border border-border bg-bg-surface hover:bg-bg-raised text-xs text-text-primary transition-colors"
                      >
                        <FolderPlus className="w-3.5 h-3.5 text-zinc-500" />
                        <span>{replyDocId ? 'Change DocVault Document' : 'Select from DocVault'}</span>
                      </button>
                    )}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run RespondPanel.docvault-gate QueriesTab.docvault-gate`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/auditease/requirements/RespondPanel.tsx frontend/src/pages/company/auditease/QueriesTab.tsx frontend/src/components/auditease/requirements/RespondPanel.docvault-gate.test.tsx frontend/src/pages/company/auditease/QueriesTab.docvault-gate.test.tsx
git commit -m "fix(auditease): hide DocVault picker option when the user lacks docvault access"
```

---

### Task 7: Rewire AuditEase downloads to the new dedicated endpoints

**Files:**
- Modify: `frontend/src/api/endpoints/auditease.ts` (add two methods)
- Modify: `frontend/src/pages/company/auditease/QueriesTab.tsx` (`handleDownload`)
- Modify: `frontend/src/pages/company/auditease/RequirementsTab.tsx` (`handleDownload`)
- Test: extend `frontend/src/pages/company/auditease/QueriesTab.docvault-gate.test.tsx` is NOT reused here — add download-specific assertions inline in this task's own test file to keep concerns separate.
- Test: Create `frontend/src/pages/company/auditease/downloadHandlers.test.tsx`

**Interfaces:**
- Consumes: Task 3's new backend routes `GET /api/v1/auditease/documents/{id}` and `GET /api/v1/auditease/documents/{id}/download`; `saveBlob(blob, filename)` from `@/lib/download`.
- Produces: `auditeaseCompanyApi.getDocument(id: string) -> Promise<DocumentResponse>`, `auditeaseCompanyApi.downloadDocument(id: string) -> Promise<Blob>`.

- [ ] **Step 1: Add the two API client methods**

In `frontend/src/api/endpoints/auditease.ts`, add to the `auditeaseCompanyApi` object (near the other query/requirement methods):

```ts
  getDocument: (documentId: string) =>
    companyClient.get<DocumentResponse>(`/api/v1/auditease/documents/${documentId}`),
  downloadDocument: (documentId: string) =>
    companyClient.get<Blob>(`/api/v1/auditease/documents/${documentId}/download`, {
      responseType: 'blob',
    }),
```

Add `DocumentResponse` to the file's type imports if not already present (check the top of the file — it likely already imports several types from `@/api/types`; add `DocumentResponse` to that import list).

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/pages/company/auditease/downloadHandlers.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import { saveBlob } from '@/lib/download'
import { QueriesTab } from './QueriesTab'
import { RequirementsTab } from './RequirementsTab'

vi.mock('@/lib/download', () => ({ saveBlob: vi.fn() }))
vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: { role: 'employee', accessible_modules: ['auditease', 'docvault'] } }),
}))
vi.mock('@/api/hooks/docvault', () => ({ useDocuments: () => ({ data: [] }) }))

vi.mock('@/api/endpoints/auditease', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints/auditease')>()
  return {
    ...actual,
    auditeaseCompanyApi: {
      ...actual.auditeaseCompanyApi,
      getDocument: vi.fn().mockResolvedValue({
        id: 'doc-1',
        current_version_id: 'v-1',
        versions: [{ id: 'v-1', original_filename: 'report.pdf' }],
      }),
      downloadDocument: vi.fn().mockResolvedValue(new Blob(['x'])),
    },
  }
})

vi.mock('@/api/hooks/auditease', () => ({
  useListQueries: () => ({
    data: [
      {
        id: 'q-1',
        status: 'open',
        requirement_id: null,
        created_at: new Date().toISOString(),
        messages: [
          {
            id: 'm-1',
            sender_type: 'auditor',
            text: 'see attached',
            attached_document_id: 'doc-1',
            created_at: new Date().toISOString(),
          },
        ],
      },
    ],
    isLoading: false,
  }),
  useAddQueryMessage: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useListRequirements: () => ({
    data: [
      {
        id: 'req-1',
        requirement_id_str: 'REQ-001',
        status: 'open',
        submissions: [
          { id: 'sub-1', documents: [{ document_id: 'doc-1', filename: 'report.pdf' }] },
        ],
      },
    ],
    isLoading: false,
  }),
}))

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient()
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('AuditEase download handlers use the dedicated endpoints', () => {
  it('QueriesTab downloads via getDocument + downloadDocument, not the docvault route', async () => {
    renderWithProviders(<QueriesTab engagementId="eng-1" />)
    fireEvent.click(screen.getByText('see attached'))
    fireEvent.click(screen.getByText('Download Attachment'))
    await waitFor(() => expect(auditeaseCompanyApi.downloadDocument).toHaveBeenCalledWith('doc-1'))
    expect(auditeaseCompanyApi.getDocument).toHaveBeenCalledWith('doc-1')
    expect(saveBlob).toHaveBeenCalledWith(expect.any(Blob), 'report.pdf')
  })

  it('RequirementsTab downloads via downloadDocument using the already-known filename', async () => {
    renderWithProviders(<RequirementsTab engagementId="eng-1" />)
    fireEvent.click(screen.getByText('report.pdf'))
    await waitFor(() => expect(auditeaseCompanyApi.downloadDocument).toHaveBeenCalledWith('doc-1'))
    expect(saveBlob).toHaveBeenCalledWith(expect.any(Blob), 'report.pdf')
  })
})
```

Adjust the exact click targets (`'see attached'`, `'Download Attachment'`, `'report.pdf'`) after Step 2's first run if the real component markup exposes different accessible text — inspect `QueriesTab.tsx`'s message-rendering block and `DocumentChip.tsx`'s render output to match real button/text content before finalizing selectors.

- [ ] **Step 3: Run to verify the tests fail**

Run: `cd frontend && npx vitest run downloadHandlers`
Expected: FAIL — `handleDownload` in both files still calls the old `useDownloadDocument`/docvault path, not `auditeaseCompanyApi`.

- [ ] **Step 4: Update `QueriesTab.tsx`'s `handleDownload`**

Remove the `useDownloadDocument` import and `const downloadDoc = useDownloadDocument()` line. Add:

```tsx
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import { saveBlob } from '@/lib/download'
```

Replace `handleDownload` (currently lines 55-68):

```tsx
  const handleDownload = async (docId: string) => {
    try {
      const doc = await auditeaseCompanyApi.getDocument(docId)
      const blob = await auditeaseCompanyApi.downloadDocument(docId)
      const version = doc.versions?.find((v) => v.id === doc.current_version_id)
      saveBlob(blob, version?.original_filename || 'document')
    } catch (err) {
      toast.error('Failed to download document')
    }
  }
```

Leave the `useDocuments()` call and its use in the reply-picker's staged-document label (line 197) untouched — it's still needed there.

- [ ] **Step 5: Update `RequirementsTab.tsx`'s `handleDownload`**

Remove the `useDownloadDocument` import/usage. Add the same two imports as Step 4. Replace `handleDownload` (currently lines 31-40):

```tsx
  const handleDownload = async (docId: string, filename: string) => {
    try {
      const blob = await auditeaseCompanyApi.downloadDocument(docId)
      saveBlob(blob, filename || 'document')
    } catch {
      toast.error('Failed to download document')
    }
  }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run downloadHandlers`
Expected: PASS (2 passed)

- [ ] **Step 7: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/endpoints/auditease.ts frontend/src/pages/company/auditease/QueriesTab.tsx frontend/src/pages/company/auditease/RequirementsTab.tsx frontend/src/pages/company/auditease/downloadHandlers.test.tsx
git commit -m "fix(auditease): download attachments via dedicated endpoints instead of the docvault-gated route"
```

---

### Task 8: Assets — attach an existing DocVault document

**Files:**
- Modify: `frontend/src/api/hooks/assets.ts` (add `useAttachAssetDocument`)
- Modify: `frontend/src/pages/company/assets/tabs/DocumentsTab.tsx` (new button + picker wiring)
- Test: Create `frontend/src/pages/company/assets/tabs/DocumentsTab.attach.test.tsx`

**Interfaces:**
- Consumes: `assetsApi.attachDocument(assetId, body: AssetDocumentAttach)` (already defined, currently unused), `DocVaultPickerModal` (Task 5), `hasModuleAccess`/`useCompanyAuth` (Task 6 pattern), `ACQUISITION_DOC_ROLES` (already exported from `@/api/endpoints/assets`).
- Produces: `useAttachAssetDocument()` hook, same shape as `useUploadAssetDocument`.

- [ ] **Step 1: Add `useAttachAssetDocument` to `frontend/src/api/hooks/assets.ts`**

Add near `useUploadAssetDocument` (after line 176):

```ts
export function useAttachAssetDocument() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: ({ assetId, body }: { assetId: string; body: AssetDocumentAttach }) =>
      assetsApi.attachDocument(assetId, body),
    onSuccess: invalidate,
  })
}
```

Confirm `AssetDocumentAttach` is already imported at the top of this file (it's used by `assetsApi.attachDocument`'s own type signature in `endpoints/assets.ts`, but this hooks file may need its own import — add `import type { AssetDocumentAttach } from '@/api/types'` if not already present).

- [ ] **Step 2: Write the failing test**

Create `frontend/src/pages/company/assets/tabs/DocumentsTab.attach.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DocumentsTab } from './DocumentsTab'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: (globalThis as any).__testProfile }),
}))

vi.mock('@/api/hooks/assets', () => ({
  useUploadAssetDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDetachAssetDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAttachAssetDocument: () => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }),
}))

const baseDetail = {
  asset: { id: 'asset-1', acquisition_id: null },
  documents: [],
} as any

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient()
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('DocumentsTab attach-from-DocVault gate', () => {
  it('hides "Attach from DocVault" when the user lacks docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['assets'] }
    renderWithProviders(<DocumentsTab detail={baseDetail} />)
    expect(screen.queryByText('Attach from DocVault')).not.toBeInTheDocument()
  })

  it('shows "Attach from DocVault" when the user has docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['assets', 'docvault'] }
    renderWithProviders(<DocumentsTab detail={baseDetail} />)
    expect(screen.getByText('Attach from DocVault')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run to verify the tests fail**

Run: `cd frontend && npx vitest run DocumentsTab.attach`
Expected: FAIL — the button doesn't exist yet.

- [ ] **Step 4: Add the button and picker wiring to `DocumentsTab.tsx`**

Add imports:

```tsx
import { useState } from 'react'
import { useCompanyAuth } from '@/auth/company'
import { hasModuleAccess } from '@/auth/company/modules'
import { DocVaultPickerModal } from '@/components/docvault/DocVaultPickerModal'
import { useAttachAssetDocument } from '@/api/hooks/assets'
```

(Note `useState` is already imported at the top per the existing file — merge into the existing import rather than duplicating.)

Inside the component, alongside the existing `upload`/`detach` hooks:

```tsx
  const attach = useAttachAssetDocument()
  const { profile } = useCompanyAuth()
  const canBrowseDocVault = hasModuleAccess(profile, 'docvault')
  const [showPicker, setShowPicker] = useState(false)

  const handleAttachExisting = async (documentIds: string[]) => {
    const documentId = documentIds[0]
    if (!documentId) return
    if (isAcquisitionRole && !asset.acquisition_id) {
      toast.error('This asset has no acquisition batch to attach shared paperwork to')
      return
    }
    try {
      await attach.mutateAsync({
        assetId: asset.id,
        body: { document_id: documentId, doc_role: role },
      })
      toast.success(`${DOC_ROLE_LABEL[role]} attached`)
    } catch (e) {
      toast.error(
        e instanceof ApiError && typeof e.detail === 'string'
          ? e.detail
          : e instanceof Error
            ? e.message
            : 'Attach failed',
      )
    }
  }
```

Note: `attach.mutateAsync` always posts to `POST /assets/{asset_id}/documents` here, matching `attachDocument`'s signature from `endpoints/assets.ts` — that endpoint is asset-scoped only (the acquisition-level attach endpoint, `POST /asset-acquisitions/{acq_id}/documents`, is a separate `assetsApi` call not yet wired to a hook). Since this plan's scope is the unit-level `DocumentsTab`, restrict the "Attach from DocVault" button to non-acquisition roles for this task — add `disabled={isAcquisitionRole}` with a hint, rather than introducing a second attach path. (If acquisition-level attach-from-DocVault is wanted later, it needs its own `useAttachAcquisitionDocument` hook mirroring `useUploadAssetDocument`'s acquisitionId branch — out of scope here since the design spec didn't call for it and `handleUpload` already handles that branch for uploads only.)

Add the button next to the existing dropzone (inside the `<Card>` block, after the `FileUploadDropzone`):

```tsx
            {canBrowseDocVault && (
              <div className="flex justify-end">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={isAcquisitionRole}
                  onClick={() => setShowPicker(true)}
                >
                  Attach from DocVault
                </Button>
              </div>
            )}
```

Add the modal at the end of the component's returned JSX (as a sibling to the outermost `<SectionShell>` content, before its closing tag):

```tsx
      {showPicker && (
        <DocVaultPickerModal
          open={showPicker}
          multiple={false}
          selectedDocIds={[]}
          title="Select a document from DocVault"
          confirmLabel="Attach"
          onClose={() => setShowPicker(false)}
          onConfirm={(ids) => {
            setShowPicker(false)
            handleAttachExisting(ids)
          }}
        />
      )}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run DocumentsTab.attach`
Expected: PASS (2 passed)

- [ ] **Step 6: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/hooks/assets.ts frontend/src/pages/company/assets/tabs/DocumentsTab.tsx frontend/src/pages/company/assets/tabs/DocumentsTab.attach.test.tsx
git commit -m "feat(assets): add attach-existing-document flow gated on docvault access"
```

---

### Task 9: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run every backend test file touched or exercised by this plan**

Run:
```bash
.venv/bin/python -m pytest \
  tests/test_module_enforcement.py \
  tests/test_docvault.py \
  tests/test_document_attach_gating.py \
  tests/test_assets.py \
  tests/test_auditease.py \
  tests/test_requirement_submissions.py \
  -q
```
Expected: all PASS. Per project convention, do not run the full backend suite beyond these affected modules.

- [ ] **Step 2: Run the full frontend vitest suite**

Run: `cd frontend && npx vitest run`
Expected: all PASS (frontend suite is fast enough to run in full per project convention).

- [ ] **Step 3: Type-check the whole frontend once more**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual smoke test (UI)**

Start the dev stack and, in a browser:
1. As admin, create an employee with `accessible_modules: ["assets"]` (no docvault) and one with `["assets", "docvault"]`.
2. As the docvault-less employee, open an asset's Documents tab — confirm no "Attach from DocVault" button appears.
3. As the docvault-scoped employee, open the same asset, click "Attach from DocVault", pick a document, confirm it attaches and appears in the list.
4. As the docvault-less employee, open the same asset and confirm they can still view/download the attached document (Assets download stays permissive).
5. Repeat the analogous check in AuditEase: an `auditease`-only user should not see "Select from DocVault" in a query reply or requirement response, but should still be able to download a document already attached to a query/requirement by someone else.

This step cannot be executed by an autonomous coding agent without a running browser session — flag it explicitly as pending manual verification if running unattended.
