# Post-Merge Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement zero-trust security hardening across DocVault, Financial Years, and Outbound SMTP: restore document lifecycle, admin-only document unlocking, admin-only financial year creation with audit logging, save-time SMTP egress validation, and SSRF/DNS-rebind protection.

**Architecture:** Enforce function-level and object-level access controls at the API gateway layer and Pydantic validation boundaries. Replace broken mass-assignment calls with dedicated lifecycle endpoints. Introduce save-time DNS egress validation and IP pinning in SMTP handling, with non-retryable worker defense.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, PostgreSQL, Celery, React 18, TanStack Query v5, Vitest, Pytest.

## Global Constraints

- Do not relax any existing security checks or authorization requirements.
- Follow existing patterns in `app/routers/` and `frontend/src/api/`.
- All database mutations must be committed with activity logging where audited.
- Sensitive credentials must never be returned in API response models or leaked in audit logs.
- Port numbers for outbound SMTP must strictly be within `frozenset({25, 465, 587, 2525})`.

---

### Task 1: Financial Year Admin Gate & Audit Provenance (Backend)

**Files:**
- Modify: `app/routers/financial_years.py:38-76`
- Test: `tests/test_financial_years.py`

**Interfaces:**
- Consumes: `require_admin` from `app.auth`, `log_activity` from `app.services.activity`.
- Produces: `POST /api/v1/financial-years` enforcing admin role and writing `"financial_year.created"` activity log.

- [ ] **Step 1: Write the failing test**

Add tests to `tests/test_financial_years.py`:
```python
@pytest.mark.asyncio
async def test_employee_cannot_create_financial_year(client: AsyncClient):
    email = "admin_fy_create_gate@testco.com"
    emp_email = "emp_fy_create_gate@testco.com"
    await create_test_company(client, name="FY Create Gate Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_emp_res = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": emp_email,
            "password": "Valid1!Pass",
            "full_name": "Assets Employee",
            "role": "employee",
            "accessible_modules": ["assets"],
        },
    )
    assert create_emp_res.status_code == 201

    emp_token = await get_company_token(client, email=emp_email, password="Valid1!Pass")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Non-admin employee attempts to create FY -> must be 403
    res = await client.post(
        "/api/v1/financial-years",
        json={
            "label": "2026-27",
            "start_date": "2026-04-01",
            "end_date": "2027-03-31",
        },
        headers=emp_headers,
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_create_financial_year_logs_activity(client: AsyncClient):
    email = "admin_fy_audit@testco.com"
    await create_test_company(client, name="FY Audit Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res = await client.post(
        "/api/v1/financial-years",
        json={
            "label": "2027-28",
            "start_date": "2027-04-01",
            "end_date": "2028-03-31",
        },
        headers=admin_headers,
    )
    assert res.status_code == 201
    fy_id = res.json()["id"]

    log_res = await client.get(
        "/api/v1/activity-log",
        params={"entity_type": "financial_year", "entity_id": fy_id},
        headers=admin_headers,
    )
    assert log_res.status_code == 200
    logs = log_res.json()
    create_log = next((l for l in logs if l["action"] == "financial_year.created"), None)
    assert create_log is not None
    assert create_log["metadata_"]["label"] == "2027-28"
    assert create_log["metadata_"]["start_date"] == "2027-04-01"
    assert create_log["metadata_"]["end_date"] == "2028-03-31"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `KUBERA_TEST_DB=kubera_test_fy .venv/bin/pytest tests/test_financial_years.py::test_employee_cannot_create_financial_year -v`
Expected: FAIL with `assert 201 == 403`

- [ ] **Step 3: Modify `create_financial_year` in `app/routers/financial_years.py`**

Replace line 41:
```python
@router.post("", response_model=FinancialYearResponse, status_code=status.HTTP_201_CREATED)
async def create_financial_year(
    body: FinancialYearCreate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
```
And add activity logging after `db.add(fy)` and `await db.flush()`:
```python
    db.add(fy)
    await db.flush()
    await log_activity(
        db, current_user.company_id, current_user.id,
        "financial_year.created", "financial_year", fy.id,
        {"label": fy.label, "start_date": str(fy.start_date), "end_date": str(fy.end_date)}
    )
    await db.commit()
    await db.refresh(fy)
    return fy
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `KUBERA_TEST_DB=kubera_test_fy .venv/bin/pytest tests/test_financial_years.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/financial_years.py tests/test_financial_years.py
git commit -m "feat(finance): gate create_financial_year on require_admin and log activity"
```

---

### Task 2: SMTP Port Whitelist, Save-Time Egress Guard & Celery Retries (Backend)

**Files:**
- Modify: `app/schemas/company_smtp.py`
- Modify: `app/routers/company_smtp.py:56-115`
- Modify: `app/services/email/tasks.py:117-135`
- Test: `tests/test_company_smtp_api.py`

**Interfaces:**
- Consumes: `resolve_public_smtp_target`, `BlockedSmtpTarget`, `ALLOWED_PORTS` from `app.services.email.net_guard`.
- Produces: Strict port schema validation on PUT/POST and runtime SSRF blocking on save.

- [ ] **Step 1: Write the failing tests**

Add tests to `tests/test_company_smtp_api.py`:
```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "postgres",
        "redis",
        "169.254.169.254",
        "10.0.0.5",
        "[::1]",
        "100.64.0.1",
    ],
)
async def test_save_smtp_config_refuses_internal_targets(client: AsyncClient, host: str):
    email = f"admin-save-ssrf-{abs(hash(host)) % 100000}@ssrf.com"
    await create_test_company(client, name="Co Save SSRF", email=email)
    token = await get_company_token(client, email=email)

    payload = {
        "host": host,
        "port": 587,
        "user": "audit@conf.com",
        "password": "Password123!",
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    r = await client.put("/api/v1/company/smtp", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Could not connect to that mail server. Check the host, port and credentials."


@pytest.mark.asyncio
@pytest.mark.parametrize("port", [21, 22, 80, 443, 3306, 5432, 6379, 8080, 0, 70000])
async def test_save_smtp_config_refuses_non_permitted_ports(client: AsyncClient, port: int):
    email = f"admin-save-port-{port}@ports.com"
    await create_test_company(client, name=f"Co Save Port {port}", email=email)
    token = await get_company_token(client, email=email)

    payload = {
        "host": "smtp.example.com",
        "port": port,
        "user": "audit@conf.com",
        "password": "Password123!",
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    r = await client.put("/api/v1/company/smtp", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `KUBERA_TEST_DB=kubera_test_fy .venv/bin/pytest tests/test_company_smtp_api.py::test_save_smtp_config_refuses_internal_targets -v`
Expected: FAIL with `assert 200 == 400`

- [ ] **Step 3: Update `app/schemas/company_smtp.py`**

Import `ALLOWED_PORTS` from `app.services.email.net_guard` and add `@field_validator("port")`:
```python
from app.services.email.net_guard import ALLOWED_PORTS
from pydantic import BaseModel, EmailStr, Field, field_validator

class CompanySmtpConfigUpdate(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=587)
    user: str = Field(min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=1)
    use_tls: bool = True
    use_ssl: bool = False
    from_email: EmailStr
    from_name: str = Field(min_length=1, max_length=255)
    is_active: bool = True

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v not in ALLOWED_PORTS:
            raise ValueError(f"Port {v} is not a permitted SMTP port ({', '.join(str(p) for p in sorted(ALLOWED_PORTS))})")
        return v


class CompanySmtpVerifyRequest(BaseModel):
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None
    from_email: Optional[EmailStr] = None
    from_name: Optional[str] = None

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in ALLOWED_PORTS:
            raise ValueError(f"Port {v} is not a permitted SMTP port ({', '.join(str(p) for p in sorted(ALLOWED_PORTS))})")
        return v
```

- [ ] **Step 4: Update `update_smtp_config` in `app/routers/company_smtp.py`**

Import `resolve_public_smtp_target` and `BlockedSmtpTarget` from `app.services.email.net_guard`:
```python
from app.services.email.net_guard import resolve_public_smtp_target, BlockedSmtpTarget
```
At start of `update_smtp_config`:
```python
    try:
        resolve_public_smtp_target(body.host, body.port)
    except BlockedSmtpTarget as e:
        logger.warning("Rejecting SMTP config save for company %s: %s", user.company_id, e)
        raise HTTPException(
            status_code=400,
            detail="Could not connect to that mail server. Check the host, port and credentials.",
        )
```

- [ ] **Step 5: Update `send_email_async` in `app/services/email/tasks.py`**

In `app/services/email/tasks.py`:
```python
from app.services.email.net_guard import BlockedSmtpTarget
```
Inside `try: result = service.send(message)` `except EmailDeliveryError as e:`:
```python
    except EmailDeliveryError as e:
        err_str = str(e)
        logger.error(f"Email delivery failed: {err_str}")
        is_blocked = isinstance(e.__cause__, BlockedSmtpTarget) or any(
            kw in err_str.lower() for kw in ("not permitted", "non-public address", "blocked")
        )
        if is_blocked:
            if log_id:
                _update_email_log(log_id, status="failed", error_message="Delivery aborted: mail server destination is not permitted")
            return {"success": False, "error": "Blocked destination"}

        if log_id:
            _update_email_log(log_id, status="failed", error_message=err_str)

        # Permanent non-retryable errors
        if any(kw in err_str.lower() for kw in ("not configured", "authentication failed", "template")):
            return {"success": False, "error": err_str}

        # Transient errors raise for Celery retry
        raise smtplib.SMTPException(err_str) from e
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `KUBERA_TEST_DB=kubera_test_fy .venv/bin/pytest tests/test_company_smtp_api.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add app/schemas/company_smtp.py app/routers/company_smtp.py app/services/email/tasks.py tests/test_company_smtp_api.py
git commit -m "fix(smtp): enforce port allowlist and validate egress guard on config save"
```

---

### Task 3: DNS Rebind E2E & IP Pinning Verification Test (Backend Test)

**Files:**
- Modify: `tests/test_net_guard.py`

**Interfaces:**
- Consumes: `EmailService` from `app.services.email.client`.
- Produces: Verification of IP pinning preventing TOCTOU DNS rebind attacks.

- [ ] **Step 1: Write E2E test verifying IP pinning prevents second DNS lookup**

In `tests/test_net_guard.py`:
```python
from unittest.mock import MagicMock, patch
from app.services.email.client import EmailService
from app.services.email.schemas import EmailConfig

def test_email_service_pins_ip_and_avoids_rebind(monkeypatch):
    """Test that EmailService resolves DNS once and connects strictly to the safe IP literal."""
    dns_call_count = 0
    resolved_ip = "93.184.216.34"

    def mock_getaddrinfo(host, port, proto=0):
        nonlocal dns_call_count
        dns_call_count += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, proto, "", (resolved_ip, port))]

    monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)

    connected_ip = None
    connected_port = None

    class MockSMTP:
        def __init__(self, timeout=None):
            self._host = None
        def connect(self, host, port):
            nonlocal connected_ip, connected_port
            connected_ip = host
            connected_port = port
            return (220, b"Ready")
        def starttls(self, context=None):
            pass
        def login(self, user, pwd):
            pass
        def close(self):
            pass

    monkeypatch.setattr("smtplib.SMTP", MockSMTP)

    config = EmailConfig(
        host="rebind.attacker.com",
        port=587,
        user="test",
        password="pwd",
        use_tls=False,
        use_ssl=False,
    )
    service = EmailService(config=config)
    server = service._get_connection()
    server.close()

    assert dns_call_count == 1
    assert connected_ip == "93.184.216.34"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `KUBERA_TEST_DB=kubera_test_fy .venv/bin/pytest tests/test_net_guard.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_net_guard.py
git commit -m "test(smtp): add end-to-end IP pinning verification for DNS rebind mitigation"
```

---

### Task 4: DocVault Restore Endpoint & Admin-Only Unlock Guard (Backend)

**Files:**
- Modify: `app/routers/docvault.py`
- Test: `tests/test_docvault_approvals.py`

**Interfaces:**
- Consumes: `require_admin`, `is_company_admin`, `can_access_bucket`, `log_activity`.
- Produces: `POST /api/v1/docvault/documents/{document_id}/restore` and locked document unlock restriction.

- [ ] **Step 1: Write the failing tests**

In `tests/test_docvault_approvals.py`:
```python
@pytest.mark.asyncio
async def test_admin_can_restore_archived_document(client: AsyncClient):
    email = "admin_restore@testco.com"
    await create_test_company(client, name="Restore Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Upload document
    files = {"file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")}
    upload_res = await client.post("/api/v1/docvault/documents", files=files, data={"title": "Doc to Archive"}, headers=admin_headers)
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["id"]

    # Archive document via DELETE
    del_res = await client.delete(f"/api/v1/docvault/documents/{doc_id}", headers=admin_headers)
    assert del_res.status_code == 204

    # Verify status is archived
    get_res = await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=admin_headers)
    assert get_res.json()["status"] == "archived"
    assert get_res.json()["is_editable"] is False

    # Admin calls restore
    restore_res = await client.post(f"/api/v1/docvault/documents/{doc_id}/restore", headers=admin_headers)
    assert restore_res.status_code == 200
    data = restore_res.json()
    assert data["status"] == "uploaded"
    assert data["is_editable"] is True
    assert data["approved_by"] is None
    assert data["approved_at"] is None

    # Verify activity log
    log_res = await client.get("/api/v1/activity-log", params={"entity_type": "document", "entity_id": doc_id}, headers=admin_headers)
    assert log_res.status_code == 200
    logs = log_res.json()
    restore_log = next((l for l in logs if l["action"] == "document.restored"), None)
    assert restore_log is not None


@pytest.mark.asyncio
async def test_employee_cannot_restore_archived_document(client: AsyncClient):
    email = "admin_emp_restore@testco.com"
    emp_email = "emp_restore@testco.com"
    await create_test_company(client, name="Emp Restore Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_emp_res = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": emp_email,
            "password": "Valid1!Pass",
            "full_name": "Doc Employee",
            "role": "employee",
            "accessible_modules": ["docvault"],
        },
    )
    assert create_emp_res.status_code == 201
    emp_token = await get_company_token(client, email=emp_email, password="Valid1!Pass")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Employee uploads document
    files = {"file": ("emp.pdf", b"%PDF-1.4 employee doc", "application/pdf")}
    upload_res = await client.post("/api/v1/docvault/documents", files=files, data={"title": "Emp Doc"}, headers=emp_headers)
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["id"]

    # Archive document
    await client.delete(f"/api/v1/docvault/documents/{doc_id}", headers=emp_headers)

    # Employee attempts restore -> 403
    restore_res = await client.post(f"/api/v1/docvault/documents/{doc_id}/restore", headers=emp_headers)
    assert restore_res.status_code == 403


@pytest.mark.asyncio
async def test_restore_non_archived_document_returns_409(client: AsyncClient):
    email = "admin_non_archived@testco.com"
    await create_test_company(client, name="Non Archived Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    files = {"file": ("test.pdf", b"%PDF-1.4 active doc", "application/pdf")}
    upload_res = await client.post("/api/v1/docvault/documents", files=files, data={"title": "Active Doc"}, headers=admin_headers)
    doc_id = upload_res.json()["id"]

    # Call restore on active doc -> 409 Conflict
    restore_res = await client.post(f"/api/v1/docvault/documents/{doc_id}/restore", headers=admin_headers)
    assert restore_res.status_code == 409


@pytest.mark.asyncio
async def test_creator_employee_cannot_unlock_locked_document(client: AsyncClient):
    email = "admin_unlock_gate@testco.com"
    emp_email = "emp_unlock_gate@testco.com"
    await create_test_company(client, name="Unlock Gate Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_emp_res = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": emp_email,
            "password": "Valid1!Pass",
            "full_name": "Unlock Employee",
            "role": "employee",
            "accessible_modules": ["docvault"],
        },
    )
    assert create_emp_res.status_code == 201
    emp_token = await get_company_token(client, email=emp_email, password="Valid1!Pass")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Employee uploads document
    files = {"file": ("emp.pdf", b"%PDF-1.4 doc", "application/pdf")}
    upload_res = await client.post("/api/v1/docvault/documents", files=files, data={"title": "Lockable Doc"}, headers=emp_headers)
    doc_id = upload_res.json()["id"]

    # Employee locks document (marks final) -> allowed
    lock_res = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"is_editable": False}, headers=emp_headers)
    assert lock_res.status_code == 200
    assert lock_res.json()["is_editable"] is False

    # Employee attempts to unlock document -> 403 Forbidden
    unlock_res = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"is_editable": True}, headers=emp_headers)
    assert unlock_res.status_code == 403
    assert "Only administrators can unlock a finalized document" in unlock_res.json()["detail"]

    # Admin unlocks document -> 200 OK
    admin_unlock_res = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"is_editable": True}, headers=admin_headers)
    assert admin_unlock_res.status_code == 200
    assert admin_unlock_res.json()["is_editable"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `KUBERA_TEST_DB=kubera_test_fy .venv/bin/pytest tests/test_docvault_approvals.py::test_admin_can_restore_archived_document -v`
Expected: FAIL with `404 Not Found` (endpoint doesn't exist yet)

- [ ] **Step 3: Implement unlock check and restore endpoint in `app/routers/docvault.py`**

1. In `update_document` (`PATCH /api/v1/docvault/documents/{document_id}`), replace line 700:
```python
    if doc.is_editable is False and update_data.get("is_editable") is True:
        if not is_company_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can unlock a finalized document",
            )
```

2. Add `POST /api/v1/docvault/documents/{document_id}/restore`:
```python
@router.post("/documents/{document_id}/restore", response_model=DocumentResponse)
async def restore_document(
    document_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(and_(Document.id == document_id, Document.company_id == current_user.company_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await can_access_bucket(db, current_user, doc.bucket_id):
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status != DocumentStatus.archived:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot restore document in '{doc.status.value}' status. Only archived documents can be restored.",
        )

    doc.status = DocumentStatus.uploaded
    doc.is_editable = True
    doc.approver_id = None
    doc.approved_by = None
    doc.approved_at = None
    doc.approval_requested_at = None
    doc.approval_notes = None

    await log_activity(db, current_user.company_id, current_user.id, "document.restored", "document", doc.id)
    await db.commit()

    result = await db.execute(
        select(Document).options(selectinload(Document.versions)).where(Document.id == doc.id)
    )
    return (await _attach_uploader_names(db, [result.scalar_one()]))[0]
```

- [ ] **Step 4: Update any existing tests affected by the new unlock policy**

Update `test_only_creator_or_admin_can_unlock` in `tests/test_docvault_approvals.py` to reflect that only admins can unlock.

- [ ] **Step 5: Run tests to verify they pass**

Run: `KUBERA_TEST_DB=kubera_test_fy .venv/bin/pytest tests/test_docvault_approvals.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/docvault.py tests/test_docvault_approvals.py
git commit -m "feat(docvault): add dedicated restore endpoint and restrict document unlocking to admin"
```

---

### Task 5: DocVault Frontend Restore Action & Unlock UI Guards (Frontend)

**Files:**
- Modify: `frontend/src/api/endpoints/docvault.ts`
- Modify: `frontend/src/api/hooks/docvault.ts`
- Modify: `frontend/src/pages/company/docvault/DocumentDrawer.tsx`
- Test: `frontend/src/pages/company/docvault/docvault.test.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/docvault/documents/{id}/restore` via `docvaultApi.restoreDocument`.
- Produces: Correctly wired Restore button and disabled unlock switch for non-admins on finalized documents.

- [ ] **Step 1: Update `frontend/src/api/endpoints/docvault.ts`**

Add `restoreDocument`:
```ts
  restoreDocument: (id: string) =>
    companyClient.post<DocumentResponse>(`/api/v1/docvault/documents/${id}/restore`),
```

- [ ] **Step 2: Update `frontend/src/api/hooks/docvault.ts`**

Add `useRestoreDocument`:
```ts
export function useRestoreDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: (id: string) => docvaultApi.restoreDocument(id),
    onSuccess: invalidate,
  })
}
```

- [ ] **Step 3: Update `frontend/src/pages/company/docvault/DocumentDrawer.tsx`**

1. Import `useRestoreDocument`:
```ts
import {
  ...
  useRestoreDocument,
} from '@/api/hooks/docvault'
```
2. Initialize mutation hook:
```ts
const restoreMutation = useRestoreDocument()
```
3. Update `restore` function:
```ts
  const restore = () =>
    wrap(
      restoreMutation.mutateAsync(document.id),
      'Document restored',
    )
```
4. Gate restore button in footer:
```tsx
        footer={
          isArchived ? (
            <Button
              variant="secondary"
              onClick={restore}
              loading={restoreMutation.isPending}
              disabled={!isAdmin}
              title={!isAdmin ? 'Only administrators can restore archived documents' : undefined}
            >
              Restore document
            </Button>
          ) : (
            <Button
              variant="danger"
              onClick={() => setConfirmArchive(true)}
              disabled={isPendingApproval && !canReview}
              title={isPendingApproval && !canReview ? 'Cannot archive while pending approval' : undefined}
            >
              Archive
            </Button>
          )
        }
```
5. Update `is_editable` switch hint and disabled state:
```tsx
          <Field
            label="Editable"
            hint={
              isPendingApproval && !canReview
                ? 'Locked while pending approval. Only the assigned approver or admin can adjust.'
                : !document.is_editable && !isAdmin
                ? 'Finalized (Locked). Only an administrator can unlock this document.'
                : 'When off, the file is Final: no new versions, renaming, tags or bucket changes.'
            }
          >
            <Switch
              checked={document.is_editable}
              onChange={changeEditable}
              disabled={isArchived || update.isPending || (isPendingApproval && !canReview) || (!document.is_editable && !isAdmin)}
              label={document.is_editable ? 'Editable' : 'Final (Locked)'}
            />
          </Field>
```

- [ ] **Step 4: Run frontend tests to verify they pass**

Run: `npm run test -- --run` (in `frontend/`)
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/endpoints/docvault.ts frontend/src/api/hooks/docvault.ts frontend/src/pages/company/docvault/DocumentDrawer.tsx
git commit -m "fix(frontend): wire restore document endpoint and enforce admin unlock guard in drawer"
```

---

### Task 6: Full Regression Verification

**Files:**
- Test all touched areas

- [ ] **Step 1: Run full backend integration test suite**
Run: `KUBERA_TEST_DB=kubera_test_fy .venv/bin/pytest tests/test_financial_years.py tests/test_depreciation_api.py tests/test_company_smtp_api.py tests/test_net_guard.py tests/test_docvault_approvals.py tests/test_docvault.py -v`
Expected: 100% PASS

- [ ] **Step 2: Run full frontend test suite**
Run: `npm run test -- --run` (in `frontend/`)
Expected: 100% PASS
