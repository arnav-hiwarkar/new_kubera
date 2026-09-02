# Post-Merge Security Hardening & Zero-Trust Verification Design

**Date**: 2026-09-02  
**Status**: Approved  
**Scope**: DocVault, Financial Years (Assets), Outbound Custom SMTP, Network Guard, Celery Worker

---

## 1. Problem Statement & Motivation

Following the merge of pull requests `#23` (docvault), `#24` (finance), and `#25` (smtp), four specific security, operational, and lifecycle gaps were identified:

1. **DocVault "Restore document" Broken**: To mitigate self-approval bypass (KUB-007), `DocumentUpdate` forbade extra attributes and removed `status`. The frontend drawer continued attempting to `PATCH` `{ status: "uploaded", is_editable: true }`, which fails with HTTP 422 Unprocessable Entity. No dedicated restore endpoint existed.
2. **DocVault Document Unlocking Policy**: Once a document is locked/finalized (`is_editable: false`), the original uploader could still toggle it back to `is_editable: true`. In enterprise statutory compliance, only a Company Administrator should have authority to unlock a finalized document.
3. **Financial Year Creation Access Control (BAC) & Audit Gap**: `POST /api/v1/financial-years` relied on `Depends(get_current_company_user)`, allowing any employee with the `assets` module to define statutory accounting periods, even though the frontend hid this button from non-admins. Additionally, creation lacked an audit log entry.
4. **SMTP Config-Save Egress Validation & Celery Retries**: `PUT /api/v1/company/smtp` did not validate target hostnames against `net_guard` or constrain ports to standard SMTP ports (`{25, 465, 587, 2525}`). Internal addresses (e.g. `127.0.0.1`, `redis:6379`) could be saved silently. Furthermore, when background workers encountered SSRF-blocked targets, Celery scheduled 3 unnecessary retries and leaked error text in email logs.

---

## 2. Architecture & Design Specification

### 2.1 DocVault: Restore Lifecycle & Admin-Only Unlock

#### 2.1.1 Dedicated Restore Endpoint
* **Endpoint**: `POST /api/v1/docvault/documents/{document_id}/restore`
* **Dependency**: `current_user: Annotated[CompanyUser, Depends(require_admin)]`
* **Preconditions**:
  * Document must exist in the caller's company (`Document.company_id == current_user.company_id`).
  * Caller must have bucket access via `can_access_bucket` (returns 404 on failure to prevent enumeration).
  * Document status must be `DocumentStatus.archived`. If not archived, raise `409 Conflict` (`"Only archived documents can be restored"`).
* **State Mutation**:
  * `doc.status = DocumentStatus.uploaded`
  * `doc.is_editable = True`
  * Approval sanitization: Reset `approver_id = None`, `approved_by = None`, `approved_at = None`, `approval_requested_at = None`, `approval_notes = None`.
* **Audit Trail**:
  * Record `ActivityLog(company_id=current_user.company_id, actor_type=ActorType.company_user, actor_id=current_user.id, action="document.restored", entity_type="document", entity_id=doc.id)`.
* **Response**: Return `DocumentResponse` with eager-loaded versions and resolved uploader/approver names.

#### 2.1.2 Admin-Only Unlock Guard
* In `PATCH /api/v1/docvault/documents/{document_id}` (`update_document` in `app/routers/docvault.py`):
  * Check:
    ```python
    if doc.is_editable is False and update_data.get("is_editable") is True:
        if not is_company_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can unlock a finalized document",
            )
    ```
  * Note: Non-admin creators may still lock an editable document (`is_editable: false`), but once locked, only an admin can unlock it.

#### 2.1.3 Frontend Integration
* In `frontend/src/api/endpoints/docvault.ts`:
  * Add `restoreDocument: (id: string) => companyClient.post<DocumentResponse>(`/api/v1/docvault/documents/${id}/restore`)`.
* In `frontend/src/api/hooks/docvault.ts`:
  * Add `useRestoreDocument()` hook invalidating query key `['docvault', 'documents']`.
* In `frontend/src/pages/company/docvault/DocumentDrawer.tsx`:
  * Use `useRestoreDocument()`.
  * In the drawer footer: show "Restore document" when `isArchived`, gated by `isAdmin` (or disabled for non-admins with clear tooltip).
  * Wire button to `restoreMutation.mutateAsync(document.id)`.
  * Disable the `Switch` for `is_editable` when `!document.is_editable && !isAdmin`, hinting that only admins may unlock finalized documents.

---

### 2.2 Finance: Financial Year Admin Gate & Audit Provenance

#### 2.2.1 Route Guarding
* In `app/routers/financial_years.py`:
  * Update `create_financial_year`:
    ```python
    @router.post("", response_model=FinancialYearResponse, status_code=status.HTTP_201_CREATED)
    async def create_financial_year(
        body: FinancialYearCreate,
        current_user: Annotated[CompanyUser, Depends(require_admin)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
    ```
* **Audit Trail**:
  * On creation, invoke:
    ```python
    await log_activity(
        db, current_user.company_id, current_user.id,
        "financial_year.created", "financial_year", fy.id,
        {"label": fy.label, "start_date": str(fy.start_date), "end_date": str(fy.end_date)}
    )
    ```

---

### 2.3 SMTP: Save-Time Egress Guard, Port Whitelisting & Celery Defense

#### 2.3.1 Pydantic Port Schema Restriction
* In `app/schemas/company_smtp.py`:
  * Define `ALLOWED_PORTS = frozenset({25, 465, 587, 2525})`.
  * Add a `@field_validator("port")` on both `CompanySmtpConfigUpdate` and `CompanySmtpVerifyRequest`:
    ```python
    @field_validator("port")
    @classmethod
    def validate_port(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in ALLOWED_PORTS:
            raise ValueError(f"Port {v} is not a permitted SMTP port ({sorted(ALLOWED_PORTS)})")
        return v
    ```

#### 2.3.2 Save-Time Egress Validation
* In `app/routers/company_smtp.py` (`update_smtp_config`):
  * Before adding/updating `CompanySmtpConfig` in the database, resolve target:
    ```python
    try:
        resolve_public_smtp_target(body.host, body.port)
    except BlockedSmtpTarget as e:
        logger.warning("Rejecting SMTP config save for company %s: %s", user.company_id, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not connect to that mail server. Check the host, port and credentials.",
        )
    ```

#### 2.3.3 Celery Worker Defense & Log Sanitization
* In `app/services/email/tasks.py` (`send_email_async`):
  * Catch `BlockedSmtpTarget` / `EmailDeliveryError` wrapping blocked targets.
  * Check if `isinstance(e, BlockedSmtpTarget)` or "not a permitted" / "non-public address" is present.
  * Do not re-raise `smtplib.SMTPException` on security policy blocks (no Celery retries).
  * Update `EmailLog` with sanitized message: `"Delivery aborted: mail server destination is not permitted"`.

---

## 3. Comprehensive Testing & Anti-Test Strategy

### 3.1 DocVault
* `test_admin_can_restore_archived_document`: Document transitions to `uploaded`, `is_editable=True`, approval metadata reset, audit log verified.
* `test_employee_cannot_restore_document`: Employee caller receives `403 Forbidden`.
* `test_restore_non_archived_document_rejected`: Attempting to restore an active document returns `409 Conflict`.
* `test_employee_cannot_unlock_locked_document`: Employee creator attempting to PATCH `is_editable: true` on locked document receives `403 Forbidden`.
* `test_admin_can_unlock_locked_document`: Admin can unlock locked document (`200 OK`).
* `test_creator_can_lock_editable_document`: Employee creator can lock their own editable document (`is_editable: false`).

### 3.2 Finance
* `test_employee_with_assets_module_cannot_create_financial_year`: Employee receives `403 Forbidden`.
* `test_admin_can_create_financial_year_with_audit_log`: Admin creates FY, returns `201`, activity log record confirmed.
* `test_financial_year_input_validation`: Inverted dates (`422`), whitespace label (`422`).

### 3.3 SMTP & SSRF
* `test_save_smtp_config_blocks_internal_and_private_targets`: Parametrized test asserting `PUT /api/v1/company/smtp` returns `400` with generic masked message on `127.0.0.1`, `localhost`, `postgres`, `redis`, `169.254.169.254`, `10.0.0.1`, `100.64.0.1`, `::1`.
* `test_save_smtp_config_blocks_non_smtp_ports`: Non-whitelisted ports (`6379`, `22`, `80`, `443`) return `422 Unprocessable Entity`.
* `test_dns_rebind_e2e_ip_pinning`: Verify that `EmailService` resolves the host once and connects to the pinned IP literal, eliminating TOCTOU DNS rebind attacks.
* `test_celery_task_does_not_retry_on_blocked_ssrf_target`: Verify zero retries and sanitized `EmailLog.error_message`.
