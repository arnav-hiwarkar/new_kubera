# KUB-002 Auditor Invitation Account Takeover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate KUB-002 (Critical account takeover in auditor registration) by making auditor registration strictly invite-only with high-entropy bcrypt-hashed tokens, case-insensitive email normalization, explicit grant acceptance data isolation, and comprehensive exploit anti-tests.

**Architecture:**
- Model `PendingAuditorInvite` updated: dead `token` UUID dropped; `token_hash` (bcrypt), `expires_at` (7d TTL), and `area_permissions` (JSONB) added.
- `invite_auditor` endpoint generates `secrets.token_urlsafe(32)`, stores bcrypt hash, and sends `/auditor/register?email=...&token=...`. Re-invites refresh token and expiry.
- `auditor_register` strictly requires `invite_token`, verifies in constant time against active pending invites for the lowercase email, deletes the dead `__pending__` branch, creates the auditor, and converts all active pending invites for that email to grants.
- `_require_auditor_access` and `document_access.py` gate engagement workspace data and documents strictly on `GrantStatus.accepted`.
- Frontend `AuditorRegister.tsx` extracts `email` and `token` from `useSearchParams()`, provides prefill and copy-paste fallback, and submits `invite_token`.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async), PostgreSQL (Alembic), Pydantic v2, Passlib (bcrypt), React 18, React Hook Form, React Router 6, Vitest, Pytest.

## Global Constraints
- Token generation: `secrets.token_urlsafe(32)`
- Token storage: `hash_password(token)` (bcrypt hash, String(255))
- Token expiration: 7 days (`timedelta(days=7)`)
- Case-insensitivity: lowercase comparison and `lower(email)` unique index on `auditors`
- Generic error on failed invite verification: HTTP 400 `"Invalid or expired invitation details"`
- Access gating: workspace data & documents strictly require `GrantStatus.accepted`

---

### Task 1: Database Models & Alembic Migration

**Files:**
- Modify: `app/models/auditease.py:201-211`
- Modify: `app/models/auditor.py:9-18`
- Create: `alembic/versions/f5a1b2c3d4e5_auditor_invite_token_and_email_hardening.py`
- Test: `tests/test_auditor_model_and_migration.py`

**Interfaces:**
- Consumes: `app.models.base.Base`, `app.models.auditease.FULL_AREA_PERMISSIONS`, `app.core.security.hash_password`
- Produces: Updated schema for `pending_auditor_invites` with `token_hash`, `expires_at`, `area_permissions`, and functional index `uq_auditors_email_lower` on `auditors`.

- [ ] **Step 1: Write the failing test for model attributes and constraints**

```python
# tests/test_auditor_model_and_migration.py
import pytest
from datetime import datetime, timezone, timedelta
from app.models.auditease import PendingAuditorInvite, FULL_AREA_PERMISSIONS
from app.models.auditor import Auditor
import uuid

def test_pending_auditor_invite_model_has_required_columns():
    invite = PendingAuditorInvite(
        engagement_id=uuid.uuid4(),
        email="auditor@firm.com",
        token_hash="fake_hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        area_permissions=dict(FULL_AREA_PERMISSIONS),
    )
    assert hasattr(invite, "token_hash")
    assert hasattr(invite, "expires_at")
    assert hasattr(invite, "area_permissions")
    assert not hasattr(invite, "token")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auditor_model_and_migration.py -v`  
Expected: FAIL with `TypeError: 'token_hash' is an invalid keyword argument for PendingAuditorInvite` or `assert not hasattr(invite, 'token')` failure.

- [ ] **Step 3: Update models and write Alembic migration**

In `app/models/auditease.py`:
```python
class PendingAuditorInvite(Base):
    """An invite to an email that has no auditor account yet. Converted to an
    AuditorEngagementGrant automatically when an auditor registers with this email and valid token."""
    __tablename__ = "pending_auditor_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    area_permissions: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text('\'{"trial_balance": true, "entries": true, "requirements": true, "queries": true, "documents": true}\'::jsonb'),
        default=lambda: dict(FULL_AREA_PERMISSIONS),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
```

In `app/models/auditor.py`:
```python
class Auditor(Base, TimestampMixin):
    __tablename__ = "auditors"
    __table_args__ = (
        Index("uq_auditors_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
```

Create migration `alembic/versions/f5a1b2c3d4e5_auditor_invite_token_and_email_hardening.py` with `down_revision = '23625093f55a'`:
- Backfills `auditors.email = lower(email)`
- Drops `auditors_email_key`, creates `uq_auditors_email_lower`
- Alters `pending_auditor_invites`: drops `token`, adds `token_hash`, `expires_at`, `area_permissions`
- Creates index `ix_pending_auditor_invites_email_lower_expires` on `(lower(email), expires_at)`

- [ ] **Step 4: Run test and run migration to verify they pass**

Run:
`uv run pytest tests/test_auditor_model_and_migration.py -v`  
`uv run alembic upgrade head`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models/auditease.py app/models/auditor.py alembic/versions/f5a1b2c3d4e5_auditor_invite_token_and_email_hardening.py tests/test_auditor_model_and_migration.py
git commit -m "feat(auth): update PendingAuditorInvite and Auditor models for token hardening and case-insensitivity"
```

---

### Task 2: Backend Invite Endpoint (`invite_auditor`) Hardening

**Files:**
- Modify: `app/routers/auditease.py:1034-1170`
- Modify: `tests/test_auditor_invite_email.py`
- Modify: `tests/test_auditease_multi_auditor.py`

**Interfaces:**
- Consumes: `secrets.token_urlsafe`, `app.core.security.hash_password`
- Produces: Refreshed token-based invite URLs `action_url = f"{base_url}/auditor/register?email={encoded_email}&token={urllib.parse.quote(token)}"`

- [ ] **Step 1: Write test for invite token generation and token refresh**

In `tests/test_auditor_invite_email.py`:
```python
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_invite_unregistered_auditor_includes_token_and_refreshes_on_reinvite(
    mock_send_task, client: AsyncClient
):
    # Setup company and engagement ...
    # 1. First invite
    res = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "new_auditor@test.com"})
    assert res.status_code == 200
    msg = mock_send_task.call_args[0][0]
    url = msg["template_context"]["action_button"]["url"]
    assert "token=" in url
    assert "email=new_auditor%40test.com" in url
    
    # 2. Re-invite before expiry succeeds with 200 and refreshes token
    res2 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "new_auditor@test.com"})
    assert res2.status_code == 200
    msg2 = mock_send_task.call_args[0][0]
    url2 = msg2["template_context"]["action_button"]["url"]
    assert url != url2  # Fresh token minted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auditor_invite_email.py -k test_invite_unregistered_auditor_includes_token_and_refreshes_on_reinvite -v`  
Expected: FAIL (token missing or 409 conflict on reinvite).

- [ ] **Step 3: Implement token minting, upsert, and action URL in `invite_auditor`**

In `app/routers/auditease.py`:
```python
    import secrets
    from datetime import datetime, timezone, timedelta
    from app.core.security import hash_password

    # Unregistered email path
    token = secrets.token_urlsafe(32)
    token_hash = hash_password(token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    pend_res = await db.execute(
        select(PendingAuditorInvite).where(
            and_(
                PendingAuditorInvite.engagement_id == engagement_id,
                func.lower(PendingAuditorInvite.email) == email,
            )
        )
    )
    existing_pend = pend_res.scalar_one_or_none()
    if existing_pend:
        existing_pend.token_hash = token_hash
        existing_pend.expires_at = expires_at
        existing_pend.area_permissions = perms
    else:
        db.add(PendingAuditorInvite(
            engagement_id=engagement_id,
            email=email,
            token_hash=token_hash,
            expires_at=expires_at,
            area_permissions=perms,
        ))
```
Update action URL:
```python
    action_url = f"{base_url}/auditor/register?email={encoded_email}&token={urllib.parse.quote(token)}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auditor_invite_email.py tests/test_auditease_multi_auditor.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/auditease.py tests/test_auditor_invite_email.py tests/test_auditease_multi_auditor.py
git commit -m "feat(auditease): mint secure tokens, refresh on re-invite, and embed token in invite link"
```

---

### Task 3: Backend Registration Endpoint (`auditor_register`) Hardening

**Files:**
- Modify: `app/schemas/auth.py:90-95`
- Modify: `app/routers/auth.py:503-570`
- Modify: `tests/conftest.py:210-230` (helper for creating test auditors with invites)
- Modify: existing tests registering auditors directly (`tests/test_auditease.py`, `tests/test_auditease_multi_auditor.py`, `tests/test_auth.py`, `tests/test_rate_limits.py`)

**Interfaces:**
- Consumes: `AuditorRegister(name, email, password, invite_token)`
- Produces: Constant-time verified `auditor_register` returning `AuditorOut` and converting all active pending invites.

- [ ] **Step 1: Write failing test for registration token requirement and dead code removal**

In `tests/test_auth.py`:
```python
@pytest.mark.asyncio
async def test_register_auditor_without_token_fails(client: AsyncClient):
    res = await client.post("/api/v1/auth/auditor/register", json={
        "email": "uninvited@firm.com",
        "password": "Valid1!Pass",
        "name": "Uninvited",
    })
    assert res.status_code == 422  # missing invite_token
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth.py -k test_register_auditor_without_token_fails -v`  
Expected: FAIL (status code is 201 because `invite_token` is not yet required).

- [ ] **Step 3: Update `AuditorRegister` schema and `auditor_register` handler**

In `app/schemas/auth.py`:
```python
class AuditorRegister(BaseModel):
    email: EmailStr
    password: Password
    name: str = Field(min_length=1, max_length=255)
    invite_token: str = Field(min_length=1, max_length=255)
```

In `app/routers/auth.py`:
```python
@router.post(
    "/auditor/register",
    response_model=AuditorOut,
    status_code=status.HTTP_201_CREATED,
)
async def auditor_register(
    request: Request,
    body: AuditorRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    settings = get_settings()
    await enforce_rate_limit(
        request,
        "auditor_register",
        body.email,
        limit=settings.REGISTER_RATE_LIMIT,
        window_seconds=settings.REGISTER_RATE_WINDOW,
        ip_limit=settings.REGISTER_RATE_LIMIT,
        ip_window=settings.REGISTER_RATE_WINDOW,
    )
    clean_email = body.email.strip().lower()

    # Case-insensitive duplicate check
    existing = await db.execute(
        select(Auditor).where(func.lower(Auditor.email) == clean_email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    generic_error = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired invitation details",
    )

    from app.models.auditease import PendingAuditorInvite, AuditorEngagementGrant, GrantStatus
    now = datetime.now(timezone.utc)
    pend_res = await db.execute(
        select(PendingAuditorInvite).where(
            func.lower(PendingAuditorInvite.email) == clean_email,
            PendingAuditorInvite.expires_at > now,
        )
    )
    pendings = pend_res.scalars().all()
    if not pendings:
        raise generic_error

    # Constant-time token verification
    token_valid = any(verify_password(body.invite_token, p.token_hash) for p in pendings)
    if not token_valid:
        raise generic_error

    auditor_obj = Auditor(
        email=clean_email,
        hashed_password=hash_password(body.password),
        name=body.name.strip(),
    )
    db.add(auditor_obj)
    await db.flush()

    for pend in pendings:
        db.add(AuditorEngagementGrant(
            auditor_id=auditor_obj.id,
            engagement_id=pend.engagement_id,
            status=GrantStatus.invited,
            area_permissions=pend.area_permissions,
        ))
        await db.delete(pend)

    await db.commit()
    await db.refresh(auditor_obj)
    return AuditorOut.model_validate(auditor_obj)
```

Update test fixture `create_test_auditor` in `tests/conftest.py` to mint an invite first (or pass valid invite token) so tests registering auditors succeed seamlessly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auth.py tests/test_auditease.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/auth.py app/routers/auth.py tests/conftest.py tests/test_auth.py tests/test_auditease.py
git commit -m "feat(auth): require valid invite token, delete dead __pending__ branch, and harden auditor registration"
```

---

### Task 4: Engagement Workspace & Document Access Gating

**Files:**
- Modify: `app/routers/auditor_engagements.py:50-68`
- Modify: `app/services/document_access.py:140-220`
- Test: `tests/test_auditor_access_gating.py`

**Interfaces:**
- Consumes: `GrantStatus.accepted`
- Produces: Enforced boundary where `GrantStatus.invited` has zero access to engagement data until `POST /accept` is called.

- [ ] **Step 1: Write failing test asserting unaccepted grants are blocked from workspace & documents**

```python
# tests/test_auditor_access_gating.py
@pytest.mark.asyncio
async def test_invited_auditor_cannot_access_workspace_before_acceptance(client: AsyncClient):
    # Setup company, engagement, invite auditor, register auditor ...
    # Before calling /accept:
    tb_res = await client.get(f"/api/v1/auditor/engagements/{eng_id}/trial-balance", headers=aud_headers)
    assert tb_res.status_code == 403
    
    # After calling /accept:
    acc_res = await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    assert acc_res.status_code == 200
    
    tb_res2 = await client.get(f"/api/v1/auditor/engagements/{eng_id}/trial-balance", headers=aud_headers)
    assert tb_res2.status_code != 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auditor_access_gating.py -v`  
Expected: FAIL (returns 200 on `tb_res` before acceptance because `in_([invited, accepted])` permitted access).

- [ ] **Step 3: Restrict access checks to `GrantStatus.accepted`**

In `app/routers/auditor_engagements.py`:
Change line 53 from:
`AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted])`
to:
`AuditorEngagementGrant.status == GrantStatus.accepted`

In `app/services/document_access.py`:
Change lines 143, 162, 188, 210 from:
`AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted])`
to:
`AuditorEngagementGrant.status == GrantStatus.accepted`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auditor_access_gating.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/auditor_engagements.py app/services/document_access.py tests/test_auditor_access_gating.py
git commit -m "fix(security): gate auditor workspace data and document downloads strictly on GrantStatus.accepted"
```

---

### Task 5: Frontend Registration Page & API Client

**Files:**
- Modify: `frontend/src/api/endpoints/auth.ts:29-36`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/auditor/AuditorRegister.tsx`
- Modify: `frontend/src/pages/auditor/AuditorRegister.test.tsx`

**Interfaces:**
- Consumes: URL query params `email` and `token`
- Produces: Interactive registration form prefilling invite params, offering copy-paste fallback, validating `invite_token`, and submitting to `auditorAuth.register`.

- [ ] **Step 1: Write frontend test asserting URL param parsing and token requirement**

In `frontend/src/pages/auditor/AuditorRegister.test.tsx`:
```tsx
it('pre-fills email and token from URL search params and submits them', async () => {
  renderApp('/auditor/register?email=invited%40firm.com&token=test_invite_token_123')
  expect(screen.getByLabelText(/Email/i)).toHaveValue('invited@firm.com')
  expect(screen.getByLabelText(/Invitation code/i)).toHaveValue('test_invite_token_123')
})

it('shows validation error when invitation code is missing', async () => {
  renderApp('/auditor/register')
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/Name/i), 'Auditor')
  await user.type(screen.getByLabelText(/Email/i), 'auditor@test.test')
  await user.type(screen.getByLabelText(/Password/i), 'Valid1!Pass')
  await user.click(screen.getByRole('button', { name: /Create account/i }))
  expect(await screen.findByText(/Invitation code is required/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test src/pages/auditor/AuditorRegister.test.tsx` in `frontend/`  
Expected: FAIL (no "Invitation code" label or input found).

- [ ] **Step 3: Update `AuditorRegister.tsx` and types**

In `frontend/src/pages/auditor/AuditorRegister.tsx`:
- Use `useSearchParams()` to extract `email` and `token`.
- Add `invite_token` field to `FormValues` and register with `{ required: 'Invitation code is required' }`.
- Default values: `{ email: searchParams.get('email') ?? '', invite_token: searchParams.get('token') ?? '' }`.
- Add helper text below invite code input.
- Pass `invite_token` in `auditorAuth.register({ name, email, password, invite_token })`.

- [ ] **Step 4: Run frontend tests to verify they pass**

Run: `npm test src/pages/auditor/AuditorRegister.test.tsx` in `frontend/`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/endpoints/auth.ts frontend/src/api/types.ts frontend/src/pages/auditor/AuditorRegister.tsx frontend/src/pages/auditor/AuditorRegister.test.tsx
git commit -m "feat(frontend): parse invite token from URL and support manual paste on auditor register"
```

---

### Task 6: Comprehensive Security & Anti-Exploit Test Suite

**Files:**
- Create: `tests/test_auditor_security_kub002.py`

**Interfaces:**
- Validates the entire end-to-end security boundary against all attack vectors identified in KUB-002.

- [ ] **Step 1: Write all 7 anti-tests and edge tests in `test_auditor_security_kub002.py`**
  1. `test_takeover_without_token_fails`: Exploit attempt without token returns 422/400 and creates no account.
  2. `test_takeover_with_invalid_token_fails`: Exploit attempt with bad token returns 400 "Invalid or expired invitation details".
  3. `test_dead_pending_branch_takeover_neutralized`: Attempt to claim existing auditor returns 409.
  4. `test_cross_account_token_theft_rejected`: Bob cannot register using Alice's invite token.
  5. `test_consumed_token_cannot_be_replayed`: Replaying a used token returns 409/400.
  6. `test_expired_token_rejected`: Token past 7-day TTL returns 400.
  7. `test_anti_enumeration_error_uniformity`: Mismatched token, non-existent email, and expired token return identical error payload.
  8. `test_multi_invite_conversion_on_registration`: Multiple engagements convert on single token registration.
  9. `test_restricted_area_permissions_preserved`: Area permissions configured on invite are preserved on grant.
  10. `test_case_insensitive_email_collision_prevented`: `lower(email)` enforced across registration and invites.

- [ ] **Step 2: Run test suite to verify all pass**

Run: `uv run pytest tests/test_auditor_security_kub002.py -v`  
Expected: 10 passed in ~5s.

- [ ] **Step 3: Run full backend regression sweep**

Run: `uv run pytest tests/test_auditease.py tests/test_auditease_multi_auditor.py tests/test_auth.py tests/test_auditor_invite_email.py tests/test_auditor_access_gating.py tests/test_auditor_security_kub002.py -v`  
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_auditor_security_kub002.py
git commit -m "test(security): add comprehensive anti-exploit and functional test suite for KUB-002"
```
