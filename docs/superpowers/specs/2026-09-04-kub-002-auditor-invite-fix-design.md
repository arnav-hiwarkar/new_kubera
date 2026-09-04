# Design Specification: KUB-002 Auditor Invitation Account Takeover Fix

**Status:** Approved  
**Author:** AI Pair Programmer & System Architect  
**Date:** 2026-09-04  
**Target Release:** Immediate Security Hardening  
**Issue Reference:** KUB-002 (Critical)

---

## 1. Context & Problem Statement

### 1.1 Root Cause
In `app/routers/auth.py` (`auditor_register`), `POST /api/v1/auth/auditor/register` performs an unauthenticated conversion of all `PendingAuditorInvite` rows matching the submitted email address:

```python
pend_res = await db.execute(
    select(PendingAuditorInvite).where(
        func.lower(PendingAuditorInvite.email) == body.email.strip().lower()
    )
)
pendings = pend_res.scalars().all()
for pend in pendings:
    db.add(AuditorEngagementGrant(
        auditor_id=auditor_obj.id,
        engagement_id=pend.engagement_id,
        status=GrantStatus.invited,
    ))
    await db.delete(pend)
```

Because the endpoint performs no secret verification or proof-of-mailbox possession:
1. An attacker who knows or guesses a target auditor's email address (such as a publicly listed CA firm address) registers the account first.
2. The attacker inherits all pending engagement grants with `GrantStatus.invited`.
3. The legitimate auditor receives `409 Conflict` on attempting to register and is completely locked out.
4. Because `GrantStatus.invited` currently confers read and write access across workspace resources (`_require_auditor_access` and `document_access.py`), the attacker immediately accesses client trial balances, requirements, queries, and confidential files before any verification or acceptance occurs.

### 1.2 Compounding Gaps
- **Dead `token` column:** `PendingAuditorInvite.token` (UUID) exists in the database model and schema, but is never populated explicitly, read, indexed, or included in invitation emails.
- **Dead `__pending__` takeover branch:** `app/routers/auth.py:530-537` checks `auditor_obj.hashed_password == "__pending__"` and allows resetting password on registration. Grep confirms that nothing in the codebase ever creates an `Auditor` with `__pending__` (this convention exists solely for `CompanyUser`). It represents an unneeded attack surface.
- **Missing `area_permissions` in `PendingAuditorInvite`:** When an unregistered auditor is invited with customized area permissions (e.g. requirements only), `PendingAuditorInvite` drops those permissions. Upon registration, the grant defaults to full access (`FULL_AREA_PERMISSIONS`), breaking least-privilege constraints.
- **Case-sensitivity discrepancies:** `Auditor.email` has a standard case-sensitive unique constraint (`auditors_email_key`), and `auditor_register` checks exact casing (`Auditor.email == body.email`), whereas `invite_auditor` looks up `func.lower(Auditor.email) == email`.
- **Premature Data Access:** Engagement data reads and document downloads are granted to `GrantStatus.invited` rather than gated on `GrantStatus.accepted`.

---

## 2. Design Decisions & Architectural Pattern

### 2.1 Invite-Only Auditor Registration
Auditor registration is strictly invite-only. Open self-registration without a valid invite token is disallowed.
- If an unauthenticated user visits `/auditor/register` without a token, the frontend presents an "Invitation Code" input with clear guidance: *"Auditor registration is by invitation only. If you received an invite email, paste your code or click the button in your email."*
- Registration requires `invite_token: str`.
- Eliminates email pre-squatting (preventing attackers from claiming CA firm emails before invitations are issued).

### 2.2 Token Generation, Hashing, and Storage
- **Generation:** Uses `secrets.token_urlsafe(32)` (~256 bits of entropy), yielding a 43-character URL-safe string.
- **Hashing at Rest:** Following the company activation key precedent (`app/routers/auth.py:67-74`), the database stores `token_hash = hash_password(token)` (bcrypt). Plaintext tokens are never stored.
- **Expiration (TTL):** Invites expire after 7 days (`expires_at = datetime.now(timezone.utc) + timedelta(days=7)`).
- **Auto-Refresh on Re-Invite:** If a company re-invites an already-pending email (whether expired or unexpired), the system updates the existing `PendingAuditorInvite` row with a freshly minted token, fresh bcrypt hash, fresh 7-day expiry, and updated `area_permissions`, then dispatches a new email.

### 2.3 Registration Verification & Multi-Invite Conversion
- The caller submits `{ name, email, password, invite_token }`.
- Lookups match against `PendingAuditorInvite` where `func.lower(email) == clean_email` and `expires_at > now`.
- Constant-time verification evaluates `verify_password(body.invite_token, pend.token_hash)`.
- If valid, proving possession of a token sent to that mailbox proves mailbox ownership:
  - The `Auditor` account is created with `email = clean_email`.
  - **All active pending invites** for that email are converted to `AuditorEngagementGrant(status=GrantStatus.invited, area_permissions=pend.area_permissions)`.
  - Consumed pending invites are deleted.

### 2.4 Uniform Anti-Enumeration Error Handling
If an invite is missing, expired, mismatched, or if the token is invalid:
- Return `HTTP 400 Bad Request` with detail: `"Invalid or expired invitation details"`.
- Never reveal whether the email exists in pending invites or why verification failed.
- If the email is already registered in `Auditor`, return `HTTP 409 Conflict: "Email already registered"`.

### 2.5 Access Control & Grant Acceptance Gating
- Data and document access across AuditEase workspaces is restricted strictly to `GrantStatus.accepted`.
- An auditor with `GrantStatus.invited` can only view the engagement card in `/auditor/app` and call `POST /api/v1/auditor/engagements/{engagement_id}/accept`.
- Calling `accept` flips status to `accepted`, sets `accepted_at = now`, logs the activity, and unlocks workspace data.

---

## 3. Database Schema & Migration Specification

### 3.1 Migration File: `alembic/versions/<rev>_auditor_invite_token_and_email_hardening.py`

#### Changes to `pending_auditor_invites`:
1. `op.drop_column('pending_auditor_invites', 'token')`
2. `op.add_column('pending_auditor_invites', sa.Column('token_hash', sa.String(255), nullable=False))`
3. `op.add_column('pending_auditor_invites', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))`
4. `op.add_column('pending_auditor_invites', sa.Column('area_permissions', JSONB(), nullable=False, server_default=sa.text(_FULL_PERMS)))`
5. `op.create_index('ix_pending_auditor_invites_email_lower_expires', 'pending_auditor_invites', [sa.text('lower(email)'), 'expires_at'])`
6. `op.create_unique_constraint('uq_pending_invite_engagement_email_lower', 'pending_auditor_invites', ['engagement_id', sa.text('lower(email)')])`

*Rollout / Existing Rows Handling:* If any legacy `pending_auditor_invites` rows exist during migration, backfill `expires_at = now() - interval '1 second'`, `token_hash = '__expired__'`, ensuring unemailed tokens cannot be redeemed and prompting clean re-invitation.

#### Changes to `auditors`:
1. Normalize existing data: `op.execute("UPDATE auditors SET email = lower(email)")`
2. `op.drop_constraint('auditors_email_key', 'auditors', type_='unique')`
3. `op.create_index('uq_auditors_email_lower', 'auditors', [sa.text('lower(email)')], unique=True)`

---

## 4. Endpoint Contract Changes

### 4.1 `POST /api/v1/auditease/engagements/{engagement_id}/auditors/invite`

- **Request Body (`AuditorInviteCreate`):**
  ```json
  {
    "email": "auditor@firm.com",
    "area_permissions": {
      "trial_balance": true,
      "entries": true,
      "requirements": true,
      "queries": true,
      "documents": true
    }
  }
  ```
- **Behavior:**
  - If auditor exists: creates/resurrects `AuditorEngagementGrant`, emails action link to `{base_url}/auditor/login`.
  - If auditor does not exist:
    - Mints `token = secrets.token_urlsafe(32)`.
    - Upserts `PendingAuditorInvite(engagement_id, email=email.lower(), token_hash=hash_password(token), expires_at=now+7d, area_permissions=perms)`.
    - Emails action link to `{base_url}/auditor/register?email={encoded_email}&token={token}`.
- **Response:** `200 OK` with updated `AuditEngagementResponse` (status of unregistered auditor in list: `"pending"`).

### 4.2 `POST /api/v1/auth/auditor/register`

- **Request Body (`AuditorRegister`):**
  ```json
  {
    "name": "Jane Doe",
    "email": "auditor@firm.com",
    "password": "SecurePassword123!",
    "invite_token": "43-character-urlsafe-token"
  }
  ```
- **Responses:**
  - `201 Created`: Returns `AuditorOut(id, email, name)`.
  - `400 Bad Request`: `{"detail": "Invalid or expired invitation details"}` (missing/mismatched/expired token).
  - `409 Conflict`: `{"detail": "Email already registered"}`.
  - `422 Unprocessable Entity`: Validation errors (e.g. missing required `invite_token`, weak password).
  - `429 Too Many Requests`: Standard rate limiting.

### 4.3 `_require_auditor_access` & `document_access.py`

- Grants with `status == GrantStatus.invited` receive `403 Forbidden` on:
  - `GET/POST /auditor/engagements/{id}/trial-balance*`
  - `GET/POST /auditor/engagements/{id}/entries*`
  - `GET/POST /auditor/engagements/{id}/requirements*`
  - `GET/POST /auditor/engagements/{id}/queries*`
  - Requirement document downloads and query attachment downloads.
- Grants with `status == GrantStatus.invited` can access:
  - `GET /api/v1/auditor/engagements` (engagement list displaying period label and company name).
  - `POST /api/v1/auditor/engagements/{id}/accept` (activates grant to `GrantStatus.accepted`).

---

## 5. Frontend Architecture & UX

### 5.1 Component: `frontend/src/pages/auditor/AuditorRegister.tsx`
- **URL Parameter Binding:**
  - Extracts `email` and `token` from `useSearchParams()`.
  - `initialEmail = searchParams.get('email') ?? ''`
  - `initialToken = searchParams.get('token') ?? ''`
- **Form UI:**
  - Name input (required).
  - Email input (required, prefilled with `initialEmail`).
  - Invitation Code input (required, prefilled with `initialToken`).
    - Placeholder: `"Paste your invite code"`.
    - Helper text: *"Auditor registration is by invitation only. If you received an invitation email, click the link in your email or paste your invite code."*
  - Password input with password strength rules.
- **Client Submission:**
  - Invokes `auditorAuth.register({ name, email, password, invite_token })`.
  - Upon success: executes `signIn({ email, password })`, toasts `"Account created"`, and navigates to `/auditor/app`.
  - Upon error: displays clear error banner matching `CompanyActivate.tsx` pattern.

---

## 6. Comprehensive Verification & Test Strategy

### 6.1 Security & Exploit Anti-Tests (`tests/test_auditor_security_kub002.py`)
1. **Takeover Rejection without Token:**
   - Pre-condition: Company invites `auditor@firm.com`.
   - Action: Attacker attempts registration with `auditor@firm.com` and no `invite_token` (or empty string).
   - Assertion: HTTP 422 or 400; no `Auditor` record is created; `PendingAuditorInvite` is intact.
2. **Takeover Rejection with Guessed/Wrong Token:**
   - Pre-condition: Company invites `auditor@firm.com`.
   - Action: Attacker attempts registration with `auditor@firm.com` and `fake-token-12345`.
   - Assertion: HTTP 400 `"Invalid or expired invitation details"`; no `Auditor` created.
3. **Dead Takeover Branch Neutralization:**
   - Action: Attempt to register an existing auditor email.
   - Assertion: Unconditionally returns 409 Conflict; no password reset or takeover possible.
4. **Cross-Account Token Replay/Theft:**
   - Pre-condition: Alice is invited with Token A; Bob is invited with Token B.
   - Action: Attacker tries to register `bob@firm.com` using Alice's Token A.
   - Assertion: HTTP 400 `"Invalid or expired invitation details"`.
5. **Token Single-Use / Consume Test:**
   - Pre-condition: Alice registers with Token A.
   - Action: Attacker tries to register or reuse Token A.
   - Assertion: HTTP 409 (if Alice's email) or 400 (if any other email).
6. **Expired Token Rejection:**
   - Pre-condition: Invite created with `expires_at = now - 1 second`.
   - Action: Registration attempt with the expired token.
   - Assertion: HTTP 400 `"Invalid or expired invitation details"`.
7. **Anti-Enumeration Uniformity:**
   - Compare response status code and JSON body between: (a) non-existent email + token, (b) invited email + wrong token, (c) expired invite + token.
   - Assertion: All return identical HTTP 400 with `"Invalid or expired invitation details"`.

### 6.2 Business Logic & Functional Tests
1. **Full Registration & Multi-Invite Conversion:**
   - Pre-condition: Company 1 invites `aud@test.com` to Eng 1 (Token 1); Company 2 invites `aud@test.com` to Eng 2 (Token 2).
   - Action: Auditor registers with `aud@test.com` and Token 1.
   - Assertion: Auditor created; both Eng 1 and Eng 2 convert to grants; both pending invites are deleted.
2. **Preservation of Customized Area Permissions:**
   - Pre-condition: Company invites unregistered auditor with `area_permissions={"trial_balance": True, "entries": False, "requirements": False, "queries": False, "documents": False}`.
   - Action: Auditor registers.
   - Assertion: `AuditorEngagementGrant.area_permissions` precisely matches the customized permissions.
3. **Email Normalization & Case-Insensitive Uniqueness:**
   - Invite sent to `Test.Auditor@Firm.COM`.
   - Registration with `test.auditor@firm.com` succeeds. Account email is stored in lowercase.
   - Attempt to register `TEST.AUDITOR@FIRM.COM` returns 409 Conflict.
4. **Token Refresh on Re-Invite:**
   - Invite sent to `test@firm.com` (Token 1).
   - Re-invite sent to `test@firm.com` before expiry.
   - Assertion: Returns 200 OK (no 409). Database row updated with fresh `token_hash` and `expires_at`.
   - Registering with Token 1 fails (400); registering with Token 2 succeeds (201).

### 6.3 Authorization & Data Isolation Tests
1. **Unaccepted Grant Isolation:**
   - Auditor has `GrantStatus.invited`.
   - Assert `GET /trial-balance`, `GET /requirements`, `GET /queries`, and document downloads all return 403 Forbidden.
2. **Explicit Acceptance Unlocks Access:**
   - Auditor calls `POST /engagements/{id}/accept`.
   - Status transitions to `accepted`.
   - Assert `GET /trial-balance`, `GET /requirements`, `GET /queries`, and document downloads now succeed.

### 6.4 Frontend Tests (`frontend/src/pages/auditor/AuditorRegister.test.tsx`)
1. Renders URL query params (`email` and `token`) into form inputs.
2. Direct navigation without token renders the invitation code input and guidance text.
3. Client validation prevents submission when `invite_token` is empty.
4. Submits `invite_token` in registration payload.
5. Error handling tests: displays server error messages for 400, 409, and 429.
