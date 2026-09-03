# DocVault Attach Gating: End-to-End Copy-Paste Execution Prompts

> **How to use this prompt guide:**
> - Each Phase corresponds to a single task from `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md`.
> - Copy the text inside the prompt fence block (` ```markdown ... ``` `) and send it directly to your agent.
> - **Every single prompt contains complete, production-ready code with all imports, test fixtures, security invariants, anti-tamper assertions, and exact commit commands.**
> - Do not advance to the next prompt until the current phase's tests pass and its atomic commit is created.

---

## Security Invariants Matrix

| # | Invariant | Verified In | Rule / Expected Result |
|---|---|---|---|
| 1 | **Attach is gated, download is NOT** | Phase 2, 3, 7 | Attaching existing doc requires `docvault` module + bucket access (403). Downloading already attached doc stays permissive for module user with 0 docvault access (200). Generic docvault download remains blocked (403). |
| 2 | **Admin bypass must never break** | Phase 1, 3 | Admins bypass module grants and bucket ACLs unconditionally. |
| 3 | **Tenant isolation (Strict 404)** | Phase 1, 2, 3, 4 | Cross-company document IDs must 404 (never 403, never 500). |
| 4 | **No endpoint reachable pre-auth** | Phase 3 | New `/auditease/documents/...` routes reject unauthenticated requests with 401. |
| 5 | **Anti-tamper / Fail closed** | Phase 2, 3, 4 | Non-existent UUIDs return 404; malformed UUIDs return 422; partial bad lists fail all-or-nothing. |
| 6 | **Auditor access non-regression** | Phase 3 | Auditor-side download (`/api/v1/auditor/documents/{id}/download`) remains 100% untouched. |

---

## Phase 0: Pre-Flight Environment & Sanity Check

```markdown
### PRE-FLIGHT ENVIRONMENT & SANITY CHECK

Before writing any code or tests for DocVault attach gating, verify the environment:

1. Ensure the Docker Compose stack (Postgres + Redis) is up and running:
   ```bash
   docker compose up -d postgres redis
   ```
2. Verify Python virtual environment and database connectivity:
   ```bash
   .venv/bin/python -m pytest tests/test_module_enforcement.py -q
   ```
3. Verify the frontend TypeScript compiles cleanly:
   ```bash
   cd frontend && npx tsc --noEmit
   ```
4. Confirm `git status` is clean.

Report back confirming:
- Docker containers status
- Pytest passing count
- TypeScript check result
- Confirmation that you are ready for Phase 1.
```

---

## Phase 1: Shared Backend Access Helper & Foundation (Task 1)

```markdown
### PHASE 1: Task 1 - Extract `app/services/bucket_access.py` and implement `assert_document_attachable`

**Reference Documents:**
- Plan: `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md` (Task 1)
- Spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md`

**Files to touch:**
- Create: `app/services/bucket_access.py`
- Modify: `app/auth.py`
- Modify: `app/routers/docvault.py`
- Create / Test: `tests/test_document_attach_gating.py`

**Security Invariants to Protect:**
- **Invariant 2 (Admin Bypass):** Admin users bypass both module check and bucket restrictions.
- **Invariant 3 (Tenant Isolation):** Calling `assert_document_attachable` on a document from another company must raise `HTTPException(404, "Document not found")` (never 403, never 500).

---

### Step 1: Refactor `app/auth.py` to extract `user_has_module`
In `app/auth.py`, replace lines 139-157 (the `require_module` definition) with:

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

Run regression check:
```bash
.venv/bin/python -m pytest tests/test_module_enforcement.py -q
```
Confirm: 12 passed.

---

### Step 2: Create `app/services/bucket_access.py`
Create `app/services/bucket_access.py` with this exact content:

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

---

### Step 3: Update `app/routers/docvault.py`
In `app/routers/docvault.py`:
1. Remove the local function definitions of `accessible_bucket_ids`, `_document_bucket_filter`, and `can_access_bucket` (lines 81–129).
2. Add the import near the top of the file (around line 14):
```python
from app.services.bucket_access import accessible_bucket_ids, can_access_bucket, _document_bucket_filter
```
3. Run regression check:
```bash
.venv/bin/python -m pytest tests/test_docvault.py -q
```
Confirm all tests pass without regressions.

---

### Step 4: Create `tests/test_document_attach_gating.py`
Create `tests/test_document_attach_gating.py` with the complete test code:

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

    # 1. No docvault module at all -> 403
    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, no_docvault_user, document.id)
    assert exc_info.value.status_code == 403
    assert "docvault module" in exc_info.value.detail

    # 2. Has docvault module, but the bucket is restricted and ungranted -> 403
    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, with_docvault_user, document.id)
    assert exc_info.value.status_code == 403
    assert "access to this document" in exc_info.value.detail

    # 3. Admin bypasses both checks regardless of grants -> success
    result = await assert_document_attachable(db, admin, document.id)
    assert result.id == document.id

    # 4. Grant bucket access -> now succeeds for non-admin employee
    db.add(BucketAccessGrant(bucket_id=bucket.id, company_user_id=with_docvault_user.id))
    await db.commit()
    result = await assert_document_attachable(db, with_docvault_user, document.id)
    assert result.id == document.id


@pytest.mark.asyncio
async def test_assert_document_attachable_wrong_company_404(client: AsyncClient, db):
    """Tenant isolation: A document belonging to a different company must 404, not leak existence."""
    await create_test_company(client, email="companyA@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='companyA@testco.com')}"}
    await _make_employee(client, admin_headers, "userA@testco.com", ["docvault"])
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

---

### Step 5: Run Tests & Commit
Run:
```bash
.venv/bin/python -m pytest tests/test_document_attach_gating.py -v
```
Confirm: 2 passed.

Commit:
```bash
git add app/services/bucket_access.py app/auth.py app/routers/docvault.py tests/test_document_attach_gating.py
git commit -m "feat(docvault): extract shared bucket-access helper and assert_document_attachable"
```

Report back with the pytest test output and git commit hash.
```

---

## Phase 2: Gate Assets Attach Endpoints (Task 2)

```markdown
### PHASE 2: Task 2 - Gate Assets Existing-Document Attach Endpoints

**Reference Documents:**
- Plan: `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md` (Task 2)
- Spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md`

**Files to touch:**
- Modify: `app/routers/asset_documents.py`
- Test: Append to `tests/test_document_attach_gating.py`

**Security Invariants to Protect:**
- **Invariant 1 (Attach gated, download permissive):** Attaching requires `docvault` module + bucket access (403 on denial). The existing download endpoint (`GET /api/v1/asset-documents/{link_id}/thumbnail`) MUST remain accessible (200) to an `assets`-only user with zero DocVault access.
- **Invariant 3 (Tenant Isolation):** Attaching a cross-company document ID returns 404.
- **Invariant 5 (Anti-Tamper):** Non-existent UUIDs return 404; malformed UUIDs return 422.

---

### Step 1: Append Failing Tests to `tests/test_document_attach_gating.py` (TDD - Red)
Append the following helpers and test cases:

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

    # Grant bucket access -> attach now succeeds
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

    # Invariant 1: Download stays permissive for assets-only user with 0 DocVault access
    await _make_employee(client, admin_headers, "download-only@testco.com", ["assets"])
    download_only_headers = await _login_headers(client, "download-only@testco.com")
    stream = await client.get(f"/api/v1/asset-documents/{link_id}/thumbnail", headers=download_only_headers)
    assert stream.status_code == 200, stream.text


@pytest.mark.asyncio
async def test_attach_asset_document_anti_tamper_and_tenant_isolation(client: AsyncClient, db):
    """Tampered request checks: non-existent UUID -> 404; cross-tenant doc -> 404; malformed UUID -> 422."""
    await create_test_company(client, email="tamper-admin@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='tamper-admin@testco.com')}"}
    category = await _leaf_category(client, admin_headers)
    quick_add = await client.post(
        "/api/v1/assets/quick-add",
        json={"asset_name": "Tamper Asset", "category_id": category["id"], "quantity": 1},
        headers=admin_headers,
    )
    asset_id = quick_add.json()["first_asset_id"]

    # 1. Non-existent UUID
    fake_id = str(uuid.uuid4())
    resp_fake = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": fake_id, "doc_role": "asset_photo"},
        headers=admin_headers,
    )
    assert resp_fake.status_code == 404

    # 2. Malformed UUID
    resp_malformed = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": "not-a-valid-uuid", "doc_role": "asset_photo"},
        headers=admin_headers,
    )
    assert resp_malformed.status_code == 422

    # 3. Cross-tenant document
    await create_test_company(client, name="OtherCo2", email="other2@testco.com")
    other_admin = await _user_by_email(db, "other2@testco.com")
    other_doc = Document(company_id=other_admin.company_id, title="OtherCo Doc", created_by=other_admin.id)
    db.add(other_doc)
    await db.commit()
    await db.refresh(other_doc)

    resp_cross = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": str(other_doc.id), "doc_role": "asset_photo"},
        headers=admin_headers,
    )
    assert resp_cross.status_code == 404
```

Run test and confirm expected failure:
```bash
.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "attach_asset_document" -v
```
Confirm: Fails with 201 instead of 403 on `test_attach_asset_document_requires_docvault_module`.

---

### Step 2: Implement Gating in `app/routers/asset_documents.py` (TDD - Green)
1. In `app/routers/asset_documents.py`, add import near top:
```python
from app.services.bucket_access import assert_document_attachable
```
2. Delete the `_verify_document` function definition (lines 106-111).
3. In `attach_asset_document` (around lines 207-226), replace:
```python
    await _verify_document(db, body.document_id, current_user.company_id)
```
with:
```python
    await assert_document_attachable(db, current_user, body.document_id)
```
4. In `attach_acquisition_document` (around lines 258-276), replace:
```python
    await _verify_document(db, body.document_id, current_user.company_id)
```
with:
```python
    await assert_document_attachable(db, current_user, body.document_id)
```
5. Leave `upload_asset_document`, `upload_acquisition_document`, and `stream_document` untouched.

---

### Step 3: Run Tests & Regressions
Run the new tests:
```bash
.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "attach_asset_document" -v
```
Confirm: 3 passed.

Run assets regression suite:
```bash
.venv/bin/python -m pytest tests/test_assets.py tests/test_document_attach_gating.py -q
```
Confirm all pass.

---

### Step 4: Commit
```bash
git add app/routers/asset_documents.py tests/test_document_attach_gating.py
git commit -m "fix(assets): gate existing-document attach on docvault module and bucket access"
```

Report back with test summary and commit hash.
```

---

## Phase 3: Gate AuditEase Query Attach & Dedicated Download Endpoints (Task 3)

```markdown
### PHASE 3: Task 3 - Gate AuditEase Query Attach & Add Dedicated Download Endpoints

**Reference Documents:**
- Plan: `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md` (Task 3)
- Spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md`

**Files to touch:**
- Modify: `app/services/document_access.py`
- Modify: `app/routers/auditease.py`
- Test: Append to `tests/test_document_attach_gating.py`

**Security Invariants to Protect:**
- **Invariant 1 (Attach gated, download permissive once attached):**
  - Attaching via `POST /api/v1/auditease/engagements/{id}/queries/{query_id}/messages` requires `docvault` module and bucket access (403 on denial).
  - Once attached, ANY company user on the engagement can download via `GET /api/v1/auditease/documents/{document_id}/download` even with ZERO `docvault` module access (200).
  - Generic `/api/v1/docvault/documents/{document_id}/download` still returns 403 to that user.
- **Invariant 3 (Tenant Isolation):** Cross-company documents return 404.
- **Invariant 4 (Pre-auth 401):** `GET /api/v1/auditease/documents/{id}` and `/download` return 401 when called without auth headers.
- **Invariant 6 (Auditor Access Non-Regression):** Auditor download path (`/api/v1/auditor/documents/{id}/download`) backed by `auditor_can_access_document` remains untouched.

---

### Step 1: Append Failing Tests to `tests/test_document_attach_gating.py` (TDD - Red)
Append:

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
    """Once attached, auditease-scoped company user can download via the dedicated endpoint
    with zero docvault access; generic docvault download endpoint continues to 403."""
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

    # Dedicated auditease download route succeeds
    new_route = await client.get(f"/api/v1/auditease/documents/{document_id}/download", headers=auditease_only_headers)
    assert new_route.status_code == 200, new_route.text

    # Metadata route succeeds
    meta_route = await client.get(f"/api/v1/auditease/documents/{document_id}", headers=auditease_only_headers)
    assert meta_route.status_code == 200, meta_route.text

    # Generic docvault route rejects
    generic_route = await client.get(f"/api/v1/docvault/documents/{document_id}/download", headers=auditease_only_headers)
    assert generic_route.status_code == 403, generic_route.text


@pytest.mark.asyncio
async def test_auditease_documents_unauthenticated_401(client: AsyncClient):
    """Invariant 4: Pre-auth requests reject with 401."""
    random_id = uuid.uuid4()
    resp1 = await client.get(f"/api/v1/auditease/documents/{random_id}")
    assert resp1.status_code == 401, resp1.text

    resp2 = await client.get(f"/api/v1/auditease/documents/{random_id}/download")
    assert resp2.status_code == 401, resp2.text


@pytest.mark.asyncio
async def test_auditease_documents_tenant_isolation_404(client: AsyncClient, db):
    """Invariant 3: Accessing another company's document via AuditEase returns 404."""
    await create_test_company(client, email="co1-admin@testco.com")
    co1_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co1-admin@testco.com')}"}

    await create_test_company(client, name="OtherCo3", email="co3-admin@testco.com")
    co3_admin = await _user_by_email(db, "co3-admin@testco.com")
    other_doc = Document(company_id=co3_admin.company_id, title="OtherCo Doc", created_by=co3_admin.id)
    db.add(other_doc)
    await db.commit()
    await db.refresh(other_doc)

    resp = await client.get(f"/api/v1/auditease/documents/{other_doc.id}", headers=co1_headers)
    assert resp.status_code == 404, resp.text

    resp_dl = await client.get(f"/api/v1/auditease/documents/{other_doc.id}/download", headers=co1_headers)
    assert resp_dl.status_code == 404, resp_dl.text
```

Run tests to confirm expected failure:
```bash
.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "query_message or query_attachment or auditease_documents" -v
```
Confirm: Fails as expected (endpoints don't exist yet, attach is not gated).

---

### Step 2: Implement in `app/services/document_access.py`
Append `company_user_can_access_engagement_document` at the end of `app/services/document_access.py`:

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
Confirm `RequirementRequest`, `RequirementResponse`, `RequirementResponseDocument`, `Query`, `QueryMessage` are imported at the top of the file.

---

### Step 3: Implement in `app/routers/auditease.py`
1. Add imports at the top of `app/routers/auditease.py`:
```python
from fastapi import Response  # add Response to existing 'from fastapi import ...' line
from app.services.bucket_access import assert_document_attachable
from app.services import document_access as doc_access
from app.models.docvault import Document, DocumentVersion
from app.schemas.docvault import DocumentResponse
from app.encryption import decrypt_dek, decrypt_file_data
```
2. In `add_query_message` (lines ~1462-1469), replace:
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
3. Add the two new company-user endpoints (place after `add_query_message`):
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

---

### Step 4: Run Tests & Regressions
Run the new tests:
```bash
.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "query_message or query_attachment or auditease_documents" -v
```
Confirm: 4 passed.

Run regression check on AuditEase (confirming auditor downloads remain unaffected):
```bash
.venv/bin/python -m pytest tests/test_auditease.py tests/test_document_attach_gating.py -q
```
Confirm all pass.

---

### Step 5: Commit
```bash
git add app/routers/auditease.py app/services/document_access.py tests/test_document_attach_gating.py
git commit -m "feat(auditease): gate query-message attach and add dedicated document download endpoints"
```

Report back with test output and commit hash.
```

---

## Phase 4: Gate Requirement Response Document Submissions (Task 4)

```markdown
### PHASE 4: Task 4 - Gate Requirement-Response Document Submissions

**Reference Documents:**
- Plan: `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md` (Task 4)
- Spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md`

**Files to touch:**
- Modify: `app/services/requirements.py`
- Modify: `app/routers/auditease.py`
- Test: Append to `tests/test_document_attach_gating.py`

**Security Invariants to Protect:**
- **Invariant 3 (Tenant Isolation):** If any ID in `document_ids` belongs to another company, fail with 404.
- **Invariant 5 (Anti-Tamper & All-or-Nothing validation):**
  - If a submission contains multiple documents and even ONE lacks docvault module or bucket access, the entire submission fails (all-or-nothing), and no response record is persisted.

---

### Step 1: Append Failing Tests to `tests/test_document_attach_gating.py` (TDD - Red)
Append:

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


@pytest.mark.asyncio
async def test_respond_requirement_all_or_nothing_and_tenant_isolation(client: AsyncClient, db):
    """Invariant 3 & 5: All-or-nothing gating and tenant isolation on requirement responses."""
    await create_test_company(client, email="req-admin2@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='req-admin2@testco.com')}"}
    engagement_id, aud_headers = await _create_engagement_with_accepted_auditor(
        client, admin_headers, "req-aud2@aud.com"
    )
    req_resp = await client.post(
        f"/api/v1/auditor/engagements/{engagement_id}/requirement-requests",
        json={"description": "Provide ledgers"},
        headers=aud_headers,
    )
    req_id = req_resp.json()["id"]

    # 1. Tenant isolation 404
    await create_test_company(client, name="OtherCo4", email="admin4@testco.com")
    other_admin = await _user_by_email(db, "admin4@testco.com")
    other_doc = Document(company_id=other_admin.company_id, title="Other Doc", created_by=other_admin.id)
    db.add(other_doc)
    await db.commit()
    await db.refresh(other_doc)

    resp_cross = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Cross tenant", "document_ids": [str(other_doc.id)]},
        headers=admin_headers,
    )
    assert resp_cross.status_code == 404

    # 2. All-or-nothing: Doc 1 allowed, Doc 2 in restricted bucket ungranted
    doc1 = await _upload_docvault_document(client, admin_headers, "Doc1")
    restricted_b = await _restrict_bucket(client, admin_headers, "Private", [])
    doc2 = await _upload_docvault_document(client, admin_headers, "Doc2", restricted_b)

    emp = await _make_employee(client, admin_headers, "req-emp@testco.com", ["auditease", "docvault"])
    emp_headers = await _login_headers(client, "req-emp@testco.com")

    resp_mixed = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Mixed", "document_ids": [doc1, doc2]},
        headers=emp_headers,
    )
    assert resp_mixed.status_code == 403
    assert "access to this document" in resp_mixed.json()["detail"]
```

Run tests to confirm failure:
```bash
.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "respond_requirement" -v
```
Confirm: Fails with 200 instead of 403 on `test_respond_requirement_document_ids_requires_docvault_module`.

---

### Step 2: Implement in `app/services/requirements.py` and `app/routers/auditease.py` (TDD - Green)
1. In `app/services/requirements.py`:
   - Add imports at top:
     ```python
     from app.models.company import CompanyUser
     from app.services.bucket_access import assert_document_attachable
     ```
   - Replace `validate_document_ids` (lines 45-64) with:
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
   - Update `create_submission` signature to accept `user: CompanyUser`:
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
   - In `create_submission`, change the validation call:
     ```python
         if document_ids:
             await validate_document_ids(db, company_id, document_ids, user)
     ```
2. In `app/routers/auditease.py`:
   - In `respond_requirement` (line ~1408), update `create_submission` call to pass `user=current_user`:
     ```python
         submission = await create_submission(
             db, req=req, engagement_id=engagement_id, company_id=current_user.company_id,
             user_id=current_user.id, user=current_user, text_answer=text, files=ups, document_ids=docs)
     ```

---

### Step 3: Run Tests & Regressions
Run the new tests:
```bash
.venv/bin/python -m pytest tests/test_document_attach_gating.py -k "respond_requirement" -v
```
Confirm: 2 passed.

Run full regression suite:
```bash
.venv/bin/python -m pytest tests/test_requirement_submissions.py tests/test_auditease.py tests/test_document_attach_gating.py -q
```
Confirm all pass.

---

### Step 4: Commit
```bash
git add app/services/requirements.py app/routers/auditease.py tests/test_document_attach_gating.py
git commit -m "fix(auditease): gate requirement-response document_ids on docvault module and bucket access"
```

Report back with test summary and commit hash.
```

---

## Phase 5: Relocate & Generalize `DocVaultPickerModal` (Task 5)

```markdown
### PHASE 5: Task 5 - Relocate and Generalize `DocVaultPickerModal`

**Reference Documents:**
- Plan: `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md` (Task 5)
- Spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md`

**Files to touch:**
- Create: `frontend/src/components/docvault/DocVaultPickerModal.tsx`
- Delete: `frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx`
- Modify: `frontend/src/components/auditease/requirements/RespondPanel.tsx` (import path only)
- Modify: `frontend/src/pages/company/auditease/QueriesTab.tsx` (import path only)

---

### Step 1: Copy and Generalize `DocVaultPickerModal.tsx`
Copy `frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx` to `frontend/src/components/docvault/DocVaultPickerModal.tsx` with these modifications:

1. Update `DocVaultPickerModalProps` interface:
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

2. Destructure the props with default values:
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

3. Replace the hardcoded modal title (around line 189):
```tsx
      title={title}
```

4. Replace the hardcoded button label (around line 621):
```tsx
              <span>{confirmLabel} ({selectedCount})</span>
```

5. Delete the old file:
```bash
git rm frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx
```

---

### Step 2: Update Import Sites
1. In `frontend/src/components/auditease/requirements/RespondPanel.tsx` (line 20):
Replace:
```tsx
import { DocVaultPickerModal } from './DocVaultPickerModal'
```
with:
```tsx
import { DocVaultPickerModal } from '@/components/docvault/DocVaultPickerModal'
```

2. In `frontend/src/pages/company/auditease/QueriesTab.tsx` (line 8):
Replace:
```tsx
import { DocVaultPickerModal } from '@/components/auditease/requirements/DocVaultPickerModal'
```
with:
```tsx
import { DocVaultPickerModal } from '@/components/docvault/DocVaultPickerModal'
```

---

### Step 3: Run TypeScript Check
Run:
```bash
cd frontend && npx tsc --noEmit
```
Confirm zero compile errors.

---

### Step 4: Commit
```bash
git add frontend/src/components/docvault/DocVaultPickerModal.tsx frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx frontend/src/components/auditease/requirements/RespondPanel.tsx frontend/src/pages/company/auditease/QueriesTab.tsx
git commit -m "refactor(frontend): relocate DocVaultPickerModal to a shared location"
```

Report back with `tsc --noEmit` output and commit hash.
```

---

## Phase 6: Gate AuditEase "Select from DocVault" Frontend Affordance (Task 6)

```markdown
### PHASE 6: Task 6 - Gate "Select from DocVault" in AuditEase on DocVault Access

**Reference Documents:**
- Plan: `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md` (Task 6)
- Spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md`

**Files to touch:**
- Modify: `frontend/src/components/auditease/requirements/RespondPanel.tsx`
- Modify: `frontend/src/pages/company/auditease/QueriesTab.tsx`
- Create Tests:
  - `frontend/src/components/auditease/requirements/RespondPanel.docvault-gate.test.tsx`
  - `frontend/src/pages/company/auditease/QueriesTab.docvault-gate.test.tsx`

---

### Step 1: Write Failing Tests (TDD - Red)
1. Create `frontend/src/components/auditease/requirements/RespondPanel.docvault-gate.test.tsx`:
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

2. Create `frontend/src/pages/company/auditease/QueriesTab.docvault-gate.test.tsx`:
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

Run tests to confirm failure:
```bash
cd frontend && npx vitest run RespondPanel.docvault-gate QueriesTab.docvault-gate
```
Confirm: Fails (buttons rendered unconditionally).

---

### Step 2: Implement Gating in Components (TDD - Green)
1. In `frontend/src/components/auditease/requirements/RespondPanel.tsx`:
   - Add imports:
     ```tsx
     import { useCompanyAuth } from '@/auth/company'
     import { hasModuleAccess } from '@/auth/company/modules'
     ```
   - Inside component body:
     ```tsx
     const { profile } = useCompanyAuth()
     const canBrowseDocVault = hasModuleAccess(profile, 'docvault')
     ```
   - Wrap the "Select from DocVault" button:
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

2. In `frontend/src/pages/company/auditease/QueriesTab.tsx`:
   - Add imports:
     ```tsx
     import { useCompanyAuth } from '@/auth/company'
     import { hasModuleAccess } from '@/auth/company/modules'
     ```
   - Inside component body:
     ```tsx
     const { profile } = useCompanyAuth()
     const canBrowseDocVault = hasModuleAccess(profile, 'docvault')
     ```
   - Wrap the "Select from DocVault" button:
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

---

### Step 3: Run Tests & Typecheck
```bash
cd frontend && npx vitest run RespondPanel.docvault-gate QueriesTab.docvault-gate
cd frontend && npx tsc --noEmit
```
Confirm: 4 passed, zero type errors.

---

### Step 4: Commit
```bash
git add frontend/src/components/auditease/requirements/RespondPanel.tsx frontend/src/pages/company/auditease/QueriesTab.tsx frontend/src/components/auditease/requirements/RespondPanel.docvault-gate.test.tsx frontend/src/pages/company/auditease/QueriesTab.docvault-gate.test.tsx
git commit -m "fix(auditease): hide DocVault picker option when the user lacks docvault access"
```

Report back with test output and commit hash.
```

---

## Phase 7: Rewire AuditEase Frontend Downloads (Task 7)

```markdown
### PHASE 7: Task 7 - Rewire AuditEase Downloads to Dedicated Endpoints

**Reference Documents:**
- Plan: `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md` (Task 7)
- Spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md`

**Files to touch:**
- Modify: `frontend/src/api/endpoints/auditease.ts`
- Modify: `frontend/src/pages/company/auditease/QueriesTab.tsx`
- Modify: `frontend/src/pages/company/auditease/RequirementsTab.tsx`
- Create Test: `frontend/src/pages/company/auditease/downloadHandlers.test.tsx`

---

### Step 1: Add API Methods in `frontend/src/api/endpoints/auditease.ts`
In `frontend/src/api/endpoints/auditease.ts`, import `DocumentResponse` from `@/api/types` and add to `auditeaseCompanyApi`:

```ts
  getDocument: (documentId: string) =>
    companyClient.get<DocumentResponse>(`/api/v1/auditease/documents/${documentId}`),
  downloadDocument: (documentId: string) =>
    companyClient.get<Blob>(`/api/v1/auditease/documents/${documentId}/download`, {
      responseType: 'blob',
    }),
```

---

### Step 2: Write Failing Tests in `downloadHandlers.test.tsx` (TDD - Red)
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

Run test to confirm failure:
```bash
cd frontend && npx vitest run downloadHandlers
```
Confirm: Fails (components still use `useDownloadDocument`).

---

### Step 3: Update `QueriesTab.tsx` and `RequirementsTab.tsx` (TDD - Green)
1. In `frontend/src/pages/company/auditease/QueriesTab.tsx`:
   - Remove `useDownloadDocument` import/call.
   - Add imports:
     ```tsx
     import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
     import { saveBlob } from '@/lib/download'
     ```
   - Replace `handleDownload` (lines 55-68):
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

2. In `frontend/src/pages/company/auditease/RequirementsTab.tsx`:
   - Remove `useDownloadDocument` import/call.
   - Add imports:
     ```tsx
     import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
     import { saveBlob } from '@/lib/download'
     ```
   - Replace `handleDownload` (lines 31-40):
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

---

### Step 4: Run Tests & Typecheck
```bash
cd frontend && npx vitest run downloadHandlers
cd frontend && npx tsc --noEmit
```
Confirm: 2 passed, zero compile errors.

---

### Step 5: Commit
```bash
git add frontend/src/api/endpoints/auditease.ts frontend/src/pages/company/auditease/QueriesTab.tsx frontend/src/pages/company/auditease/RequirementsTab.tsx frontend/src/pages/company/auditease/downloadHandlers.test.tsx
git commit -m "fix(auditease): download attachments via dedicated endpoints instead of the docvault-gated route"
```

Report back with test summary and commit hash.
```

---

## Phase 8: Assets — Attach Existing DocVault Document Flow (Task 8)

```markdown
### PHASE 8: Task 8 - Assets: Add Attach-Existing-Document Flow

**Reference Documents:**
- Plan: `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md` (Task 8)
- Spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md`

**Files to touch:**
- Modify: `frontend/src/api/hooks/assets.ts`
- Modify: `frontend/src/pages/company/assets/tabs/DocumentsTab.tsx`
- Create Test: `frontend/src/pages/company/assets/tabs/DocumentsTab.attach.test.tsx`

---

### Step 1: Add `useAttachAssetDocument` in `frontend/src/api/hooks/assets.ts`
In `frontend/src/api/hooks/assets.ts`, import `AssetDocumentAttach` from `@/api/types` if not present, and add:

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

---

### Step 2: Write Failing Tests (TDD - Red)
Create `frontend/src/pages/company/assets/tabs/DocumentsTab.attach.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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

Run test to confirm failure:
```bash
cd frontend && npx vitest run DocumentsTab.attach
```
Confirm: Fails (button does not exist).

---

### Step 3: Implement Flow in `DocumentsTab.tsx` (TDD - Green)
1. Add imports to `frontend/src/pages/company/assets/tabs/DocumentsTab.tsx`:
```tsx
import { useCompanyAuth } from '@/auth/company'
import { hasModuleAccess } from '@/auth/company/modules'
import { DocVaultPickerModal } from '@/components/docvault/DocVaultPickerModal'
import { useAttachAssetDocument } from '@/api/hooks/assets'
```
2. Inside `DocumentsTab` component body:
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
3. Render the "Attach from DocVault" button next to the dropzone (inside `<Card>`):
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
4. Render `DocVaultPickerModal` right before the closing `</SectionShell>` tag:
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

---

### Step 4: Run Tests & Typecheck
```bash
cd frontend && npx vitest run DocumentsTab.attach
cd frontend && npx tsc --noEmit
```
Confirm: 2 passed, zero type errors.

---

### Step 5: Commit
```bash
git add frontend/src/api/hooks/assets.ts frontend/src/pages/company/assets/tabs/DocumentsTab.tsx frontend/src/pages/company/assets/tabs/DocumentsTab.attach.test.tsx
git commit -m "feat(assets): add attach-existing-document flow gated on docvault access"
```

Report back with test summary and commit hash.
```

---

## Phase 9: Full Regression Pass & Invariant Verification (Task 9)

```markdown
### PHASE 9: Task 9 - Full Regression Pass & Security Invariant Audit

**Reference Documents:**
- Plan: `docs/superpowers/plans/2026-09-03-docvault-attach-gating.md` (Task 9)
- Spec: `docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md`

---

### Step 1: Run Backend Affected Regression Suites
```bash
.venv/bin/python -m pytest \
  tests/test_module_enforcement.py \
  tests/test_docvault.py \
  tests/test_document_attach_gating.py \
  tests/test_assets.py \
  tests/test_auditease.py \
  tests/test_requirement_submissions.py \
  -v
```
Confirm all tests pass without errors.

---

### Step 2: Run Full Frontend Vitest Suite
```bash
cd frontend && npx vitest run
```
Confirm all test suites pass.

---

### Step 3: Frontend TypeScript Check
```bash
cd frontend && npx tsc --noEmit
```
Confirm zero compile errors.

---

### Step 4: Deliver Security Invariant Audit Sign-Off
Report back with an explicit verification audit answering each checklist item:
- [ ] **Invariant 1 (Attach Gated, Download Permissive):**
  - Confirmed: Assets attach gated (403), thumbnail/stream download permissive (200).
  - Confirmed: AuditEase attach gated (403), dedicated download permissive (200), generic docvault download blocked (403).
- [ ] **Invariant 2 (Admin Bypass):**
  - Confirmed: Admin bypasses module and bucket ACLs unconditionally.
- [ ] **Invariant 3 (Tenant Isolation):**
  - Confirmed: All endpoints return 404 on cross-tenant document IDs.
- [ ] **Invariant 4 (Pre-Auth Rejection):**
  - Confirmed: Unauthenticated requests to new AuditEase document routes return 401.
- [ ] **Invariant 5 (Anti-Tamper):**
  - Confirmed: Non-existent IDs return 404, malformed UUIDs return 422, partial invalid lists fail all-or-nothing.
- [ ] **Invariant 6 (Auditor Access Non-Regression):**
  - Confirmed: `tests/test_auditease.py` passes; auditor routes untouched.
- [ ] **Drift & Deviations:**
  - List any discrepancies between the codebase and the plan, and describe how they were handled.
```
