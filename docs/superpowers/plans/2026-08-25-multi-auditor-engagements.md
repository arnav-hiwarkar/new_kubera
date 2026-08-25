# Multi-Auditor Engagements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multiple auditors per AuditEase engagement with per-area access control, a company-side Auditors tab (list, per-auditor activity log, PDF/Excel report, invite/remove/manage), and full workspace + access-event activity logging.

**Architecture:** Permissions live as a JSONB map on the existing `AuditorEngagementGrant` row (mirrors `CompanyUser.accessible_modules`). The single-auditor bulk-revoke in the invite endpoint is deleted; grants are added/resurrected instead. Activity logging reuses `ActivityLog` (+ new nullable `engagement_id` column) via the existing `log_activity` service. The activity report is a new neutral `ReportDocument` builder rendered through the existing xlsx/pdf pipeline.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + PostgreSQL; React 18 + TypeScript + TanStack Query; openpyxl/WeasyPrint reporting stack.

**Spec:** `docs/superpowers/specs/2026-08-25-multi-auditor-engagements-design.md`

## Global Constraints

- Areas are exactly: `trial_balance`, `entries`, `requirements`, `queries`, `documents`.
- Invite defaults to **full access** when no `area_permissions` given; an explicit payload sets listed areas and defaults unlisted ones to `false`.
- Company mutations (invite / edit permissions / remove) require role `admin` or `manager`; reads (list / activity / report export) any company user.
- Auditor endpoints enforce: grant live (`invited`|`accepted`) AND engagement `active` AND area enabled.
- Removing/closing never deletes auditor work; attribution (`created_by` etc.) is permanent.
- Re-invite after removal resurrects the same grant row (unique constraint `(auditor_id, engagement_id)` holds).
- Old endpoint `POST /engagements/{id}/invite-auditor` is removed; replacement `POST /engagements/{id}/auditors/invite`. Response singular fields `auditor_email`/`auditor_grant_status` replaced by `auditors: [...]`.
- Backend tests run with `pytest tests/... -v` from repo root; frontend unit tests with `npx vitest run <paths>` from `frontend/`.
- Frontend types are generated: run backend server, then `npm run gen:api` in `frontend/`.

---

### Task 1: Schema & migration — grant permissions + activity engagement link

**Files:**
- Modify: `app/models/auditease.py` (grant model, ~line 156)
- Modify: `app/models/activity_log.py`
- Modify: `app/services/activity.py`
- Create: `alembic/versions/b5d8f2a6c9e1_multi_auditor_grants.py`

**Interfaces:**
- Produces: `AuditorEngagementGrant.area_permissions` (JSONB dict), unique constraint `uq_grant_auditor_engagement`; `ActivityLog.engagement_id` (nullable UUID); `log_activity(..., engagement_id=None)` kwarg used by all later tasks.
- Produces constants consumed everywhere: `AUDITOR_AREAS`, `FULL_AREA_PERMISSIONS`, `AREA_LABELS` (defined in `app/models/auditease.py`).

- [ ] **Step 1: Confirm current Alembic head**

Run: `uv run alembic heads`
Expected: a single head revision id. If it is not `e2c4a6b8d0f1`, use the printed id as `down_revision` in Step 3.

- [ ] **Step 2: Add constants + columns to the models**

In `app/models/auditease.py`, add after `SenderType` (~line 66):

```python
class AuditorAccessArea(str, enum.Enum):
    """Workspace areas a company can toggle per auditor on a grant."""
    trial_balance = "trial_balance"
    entries = "entries"
    requirements = "requirements"
    queries = "queries"
    documents = "documents"


AUDITOR_AREAS: tuple[str, ...] = tuple(a.value for a in AuditorAccessArea)

FULL_AREA_PERMISSIONS: dict[str, bool] = {a: True for a in AUDITOR_AREAS}

AREA_LABELS: dict[str, str] = {
    "trial_balance": "Trial Balance",
    "entries": "Entries",
    "requirements": "Requirements",
    "queries": "Queries",
    "documents": "Documents",
}
```

Add imports at top of the file if missing: `from sqlalchemy import UniqueConstraint, text`.

Replace the `AuditorEngagementGrant` class body with:

```python
class AuditorEngagementGrant(Base):
    __tablename__ = "auditor_engagement_grants"
    __table_args__ = (
        UniqueConstraint("auditor_id", "engagement_id", name="uq_grant_auditor_engagement"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auditor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auditors.id", ondelete="CASCADE"), nullable=False, index=True)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[GrantStatus] = mapped_column(SAEnum(GrantStatus, name="grant_status"), default=GrantStatus.invited, nullable=False)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Which workspace areas this auditor may use. Missing/false = denied. The
    # server_default backfills pre-existing single-auditor rows to full access,
    # preserving today's behavior exactly.
    area_permissions: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text('\'{"trial_balance": true, "entries": true, "requirements": true, "queries": true, "documents": true}\'::jsonb'),
        default=lambda: dict(FULL_AREA_PERMISSIONS),
    )
```

In `app/models/activity_log.py`, add after `entity_id` (no FK on purpose: the log is
append-only history and must survive engagement hard-deletes):

```python
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
```

In `app/services/activity.py`, extend the signature and body:

```python
async def log_activity(
    db: AsyncSession,
    company_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    metadata_: Optional[dict] = None,
    actor_type: ActorType = ActorType.company_user,
    engagement_id: Optional[uuid.UUID] = None,
) -> None:
    """Queue an activity row. Does not commit — the caller's transaction owns it,
    so a failed operation cannot leave an orphan audit entry."""
    db.add(
        ActivityLog(
            company_id=company_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_=metadata_,
            engagement_id=engagement_id,
        )
    )
```

- [ ] **Step 3: Write the migration**

Create `alembic/versions/b5d8f2a6c9e1_multi_auditor_grants.py` (use the head id from Step 1 as `down_revision`):

```python
"""multi-auditor grants: area_permissions + unique constraint; activity engagement link

Revision ID: b5d8f2a6c9e1
Revises: e2c4a6b8d0f1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'b5d8f2a6c9e1'
down_revision: Union[str, None] = 'e2c4a6b8d0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FULL_PERMS = '\'{"trial_balance": true, "entries": true, "requirements": true, "queries": true, "documents": true}\'::jsonb'


def upgrade() -> None:
    op.add_column(
        'auditor_engagement_grants',
        sa.Column('area_permissions', JSONB(), nullable=False, server_default=sa.text(_FULL_PERMS)),
    )
    op.create_unique_constraint('uq_grant_auditor_engagement', 'auditor_engagement_grants', ['auditor_id', 'engagement_id'])
    op.add_column('activity_logs', sa.Column('engagement_id', UUID(), nullable=True))
    op.create_index('ix_activity_logs_engagement_id', 'activity_logs', ['engagement_id'])


def downgrade() -> None:
    op.drop_index('ix_activity_logs_engagement_id', table_name='activity_logs')
    op.drop_column('activity_logs', 'engagement_id')
    op.drop_constraint('uq_grant_auditor_engagement', 'auditor_engagement_grants', type_='unique')
    op.drop_column('auditor_engagement_grants', 'area_permissions')
```

- [ ] **Step 4: Run migration up then down then up**

Run: `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: all three commands succeed with no error output.

- [ ] **Step 5: Commit**

```bash
git add app/models/auditease.py app/models/activity_log.py app/services/activity.py alembic/versions/b5d8f2a6c9e1_multi_auditor_grants.py
git commit -m "feat(auditease): grant area_permissions + activity engagement link"
```

---

### Task 2: Area-permission helpers

**Files:**
- Create: `app/services/auditor_access.py`
- Test: `unit_tests/test_auditor_access.py` (new directory file; plain pytest, no DB)

**Interfaces:**
- Consumes: `AUDITOR_AREAS` from Task 1.
- Produces: `normalize_area_permissions(payload: dict | None) -> dict[str, bool]` — raises `ValueError` on unknown area names; `None` returns all-true; explicit payload fills missing areas with `False`. And `area_enabled(perms: dict | None, area: str) -> bool` — missing key is `False`.

- [ ] **Step 1: Write the failing tests**

Create `unit_tests/test_auditor_access.py`:

```python
import pytest

from app.services.auditor_access import area_enabled, normalize_area_permissions


def test_none_means_full_access():
    assert normalize_area_permissions(None) == {
        "trial_balance": True,
        "entries": True,
        "requirements": True,
        "queries": True,
        "documents": True,
    }


def test_explicit_payload_fills_missing_with_false():
    perms = normalize_area_permissions({"entries": True})
    assert perms["entries"] is True
    assert perms["trial_balance"] is False
    assert perms["documents"] is False


def test_unknown_area_raises():
    with pytest.raises(ValueError):
        normalize_area_permissions({"nope": True})


def test_area_enabled_missing_key_is_denied():
    assert area_enabled({}, "entries") is False
    assert area_enabled(None, "entries") is False
    assert area_enabled({"entries": True}, "entries") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest unit_tests/test_auditor_access.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.auditor_access'`

- [ ] **Step 3: Implement**

Create `app/services/auditor_access.py`:

```python
"""Per-area permission helpers for auditor engagement grants.

Pure functions — no DB. The router layer owns queries and HTTP errors.
"""
from app.models.auditease import AUDITOR_AREAS


def normalize_area_permissions(payload: dict | None) -> dict[str, bool]:
    """None => every area enabled (invite default). An explicit payload sets the
    listed areas and DENIES everything omitted, so {"entries": true} means
    entries-only."""
    if payload is None:
        return {a: True for a in AUDITOR_AREAS}
    unknown = set(payload) - set(AUDITOR_AREAS)
    if unknown:
        raise ValueError(f"Unknown areas: {sorted(unknown)}")
    return {a: bool(payload.get(a, False)) for a in AUDITOR_AREAS}


def area_enabled(perms: dict | None, area: str) -> bool:
    return bool((perms or {}).get(area, False))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest unit_tests/test_auditor_access.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/auditor_access.py unit_tests/test_auditor_access.py
git commit -m "feat(auditease): area-permission normalize/enable helpers"
```

---

### Task 3: Schemas — auditors array, invite/update payloads, activity events, attribution names

**Files:**
- Modify: `app/schemas/auditease.py` (~lines 318–347 engagements section; entry/requirement/query response classes nearby)

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Tasks 4–10):
  - `EngagementAuditorResponse` `{auditor_id: Optional[UUID], name, email, status: str, area_permissions: dict, invited_at, accepted_at}` — `status` ∈ invited|accepted|revoked|pending; `auditor_id/name` are `None` for pending unregistered invites.
  - `AuditEngagementResponse`: drops `auditor_email`/`auditor_grant_status`, gains `auditors: List[EngagementAuditorResponse] = []` and optional `area_permissions: Optional[dict] = None` (populated only on the auditor's own list view).
  - `AuditorInviteCreate {email: str, area_permissions: Optional[dict] = None}` (replaces `AuditorInvite`).
  - `AuditorPermissionsUpdate {area_permissions: dict}`.
  - `ActivityEventResponse {id, action, entity_type, entity_id, metadata: Optional[dict], created_at}`.
  - Attribution fields: `AuditEntryResponse.created_by_name`, `RequirementRequestResponse.raised_by_name`, `QueryMessageResponse.sender_name` (all `Optional[str] = None`).

- [ ] **Step 1: Edit the engagement schemas**

In `app/schemas/auditease.py` replace lines 326–346 (`AuditEngagementResponse` and the existing `AuditorEngagementGrantResponse`) with:

```python
class EngagementAuditorResponse(BaseModel):
    auditor_id: Optional[uuid.UUID] = None  # None for pending unregistered invites
    name: Optional[str] = None
    email: str
    # one of: invited | accepted | revoked | pending (not yet registered)
    status: str
    area_permissions: dict[str, bool]
    invited_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None

class AuditEngagementResponse(AuditEngagementBase):
    id: uuid.UUID
    company_id: uuid.UUID
    status: EngagementStatus
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Company view: everyone ever granted (including revoked). Populated by the
    # router via attribute injection before serialization.
    auditors: List[EngagementAuditorResponse] = []
    # Auditor view only: the requesting auditor's own area map for this engagement.
    area_permissions: Optional[dict[str, bool]] = None
    model_config = {"from_attributes": True}
```

Keep `List`/`Optional`/`datetime`/`uuid` imports (already present in the file).

Directly below them add:

```python
class AuditorInviteCreate(BaseModel):
    email: str
    area_permissions: Optional[dict] = None  # None = full access

class AuditorPermissionsUpdate(BaseModel):
    area_permissions: dict

class ActivityEventResponse(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    metadata: Optional[dict] = None
    created_at: datetime
```

- [ ] **Step 2: Add attribution fields**

Find `AuditEntryResponse`, `RequirementRequestResponse`, `QueryMessageResponse` in the same file and add one field to each:

```python
    created_by_name: Optional[str] = None   # AuditEntryResponse
    raised_by_name: Optional[str] = None    # RequirementRequestResponse
    sender_name: Optional[str] = None       # QueryMessageResponse
```

- [ ] **Step 3: Verify the app still imports and routes load**

Run: `python -c "import app.main"` (or `uv run python -c "import app.main"`)
Expected: exits 0, no Pydantic errors.

- [ ] **Step 4: Commit**

```bash
git add app/schemas/auditease.py
git commit -m "feat(auditease): multi-auditor response schemas + attribution fields"
```

---

### Task 4: Multi-auditor invite endpoint + auditors-array hydration

**Files:**
- Modify: `app/routers/auditease.py` (`_hydrate_auditor_info` line 56; invite block lines 988–1050)
- Test: `tests/test_auditease_multi_auditor.py` (new)
- Modify: `tests/test_auditease.py` (mechanical path/assertion updates — see Step 5)

**Interfaces:**
- Consumes: Task 1 models/constants, Task 2 helpers, Task 3 schemas.
- Produces:
  - `POST /api/v1/auditease/engagements/{id}/auditors/invite` (manager/admin) → `AuditEngagementResponse` with populated `auditors`. Errors: 409 closed, 400 duplicate live grant, 409 duplicate pending email, 400 unknown area.
  - `_hydrate_auditors(db, eng)` and `_list_auditors(db, engagement_id) -> list[dict]` helpers (Task 7 list endpoint reuses `_list_auditors`).
  - `log_activity(..., action="auditor.invited", entity_type="audit_engagement", entity_id=eng.id, metadata_={"email": ...}, actor_type=ActorType.company_user, engagement_id=eng.id)`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_auditease_multi_auditor.py`:

```python
import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token


async def _register_login(client: AsyncClient, email: str) -> dict:
    await client.post("/api/v1/auth/auditor/register", json={"email": email, "password": "pass1234", "name": email.split("@")[0].title()})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": email, "password": "pass1234"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _make_user(client: AsyncClient, admin_headers: dict, email: str, role: str) -> dict:
    resp = await client.post("/api/v1/users", json={
        "email": email, "password": "pass1234",
        "full_name": email.split("@")[0], "role": role,
    }, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_two_auditors_coexist(client: AsyncClient):
    await create_test_company(client, email="ma@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="ma@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _register_login(client, "one@a.com")
    await _register_login(client, "two@a.com")

    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "one@a.com"}, headers=co)
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "two@a.com"}, headers=co)
    assert resp.status_code == 200, resp.text

    auds = resp.json()["auditors"]
    assert len(auds) == 2
    assert {a["email"] for a in auds} == {"one@a.com", "two@a.com"}
    assert all(a["status"] == "invited" for a in auds)
    # Full access default
    assert all(a["area_permissions"]["entries"] is True for a in auds)


@pytest.mark.asyncio
async def test_invite_with_restricted_areas(client: AsyncClient):
    await create_test_company(client, email="ra@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="ra@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _register_login(client, "tbonly@a.com")

    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "tbonly@a.com", "area_permissions": {"trial_balance": True}},
        headers=co,
    )
    assert resp.status_code == 200, resp.text
    aud = resp.json()["auditors"][0]
    assert aud["area_permissions"] == {
        "trial_balance": True, "entries": False, "requirements": False,
        "queries": False, "documents": False,
    }


@pytest.mark.asyncio
async def test_duplicate_live_and_pending_invites_rejected(client: AsyncClient):
    await create_test_company(client, email="dup@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="dup@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _register_login(client, "dupaud@a.com")

    r1 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "dupaud@a.com"}, headers=co)
    assert r1.status_code == 200
    r2 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "dupaud@a.com"}, headers=co)
    assert r2.status_code == 400

    # Unregistered email: second invite while pending is 409
    p1 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "ghost@firm.com"}, headers=co)
    assert p1.status_code == 200
    assert p1.json()["auditors"][-1]["status"] == "pending"
    p2 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "ghost@firm.com"}, headers=co)
    assert p2.status_code == 409


@pytest.mark.asyncio
async def test_remove_then_reinvite_resurrects_same_row(client: AsyncClient):
    await create_test_company(client, email="rr@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="rr@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _register_login(client, "comeback@a.com")
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "comeback@a.com"}, headers=co)

    aud_id = (await client.get(f"/api/v1/auditease/engagements/{eng_id}", headers=co)).json()["auditors"][0]["auditor_id"]
    resp = await client.delete(f"/api/v1/auditease/engagements/{eng_id}/auditors/{aud_id}", headers=co)
    assert resp.status_code == 204

    # Re-invite succeeds despite the unique constraint (row resurrected)
    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "comeback@a.com", "area_permissions": {"queries": True}},
        headers=co,
    )
    assert resp.status_code == 200, resp.text
    auds = [a for a in resp.json()["auditors"] if a["status"] != "revoked"]
    assert len(auds) == 1
    assert auds[0]["auditor_id"] == aud_id
    assert auds[0]["area_permissions"] == {
        "trial_balance": False, "entries": False, "requirements": False,
        "queries": True, "documents": False,
    }


@pytest.mark.asyncio
async def test_employee_cannot_manage_auditors(client: AsyncClient):
    await create_test_company(client, email="emp@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="emp@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _make_user(client, co, "staff@a.com", role="employee")
    emp = _headers(await get_company_token(client, email="staff@a.com", password="pass1234"))

    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "x@a.com"}, headers=emp)
    assert resp.status_code == 403
    # Reads stay open
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors", headers=emp)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invite_on_closed_engagement_409(client: AsyncClient):
    await create_test_company(client, email="cl@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="cl@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=co)
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "x@a.com"}, headers=co)
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auditease_multi_auditor.py -v`
Expected: FAIL (404 on `/auditors/invite` — route does not exist yet).

- [ ] **Step 3: Rewrite hydration + invite in `app/routers/auditease.py`**

Update the router imports (top of file): add `require_manager_or_admin` to the `app.auth` import; add `ActorType` via `from app.models.activity_log import ActorType`; add `from app.services.activity import log_activity`; add `from app.services.auditor_access import normalize_area_permissions`; add `FULL_AREA_PERMISSIONS, AREA_LABELS` to the existing `app.models.auditease` import; add `AuditorInviteCreate, EngagementAuditorResponse` to the existing `app.schemas.auditease` import (the old request model `AuditorInvite` is deleted along with the old endpoint below).

Replace `_hydrate_auditor_info` (lines 56–84) with:

```python
async def _list_auditors(db: AsyncSession, engagement_id: uuid.UUID) -> list[dict]:
    """Every grant row (incl. revoked) plus pending unregistered invites."""
    rows = await db.execute(
        select(AuditorEngagementGrant, Auditor.name, Auditor.email)
        .join(Auditor, Auditor.id == AuditorEngagementGrant.auditor_id)
        .where(AuditorEngagementGrant.engagement_id == engagement_id)
        .order_by(AuditorEngagementGrant.invited_at.desc())
    )
    out = [
        {
            "auditor_id": g.auditor_id,
            "name": name,
            "email": email,
            "status": g.status.value,
            "area_permissions": g.area_permissions or dict(FULL_AREA_PERMISSIONS),
            "invited_at": g.invited_at,
            "accepted_at": g.accepted_at,
        }
        for g, name, email in rows.all()
    ]
    pend = await db.execute(
        select(PendingAuditorInvite)
        .where(PendingAuditorInvite.engagement_id == engagement_id)
        .order_by(PendingAuditorInvite.created_at.desc())
    )
    for p in pend.scalars().all():
        out.append({
            "auditor_id": None, "name": None, "email": p.email,
            "status": "pending", "area_permissions": dict(FULL_AREA_PERMISSIONS),
            "invited_at": p.created_at, "accepted_at": None,
        })
    return out


async def _hydrate_auditors(db: AsyncSession, eng: AuditEngagement) -> AuditEngagement:
    """Attach the `auditors` array consumed by AuditEngagementResponse."""
    eng.auditors = await _list_auditors(db, eng.id)
    return eng
```

Replace the invite block (`class AuditorInvite(BaseModel)` through end of `invite_auditor`, lines 988–1050) with:

```python
@router.post("/engagements/{engagement_id}/auditors/invite", response_model=AuditEngagementResponse)
async def invite_auditor(
    engagement_id: uuid.UUID,
    invite: AuditorInviteCreate,
    current_user: Annotated[CompanyUser, Depends(require_manager_or_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Invite one auditor by email without disturbing other auditors. Registered
    emails get a grant (revoked grants are resurrected); unknown emails get a
    pending invite that auto-converts on registration."""
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    if eng.status == EngagementStatus.closed:
        raise HTTPException(status_code=409, detail="Cannot invite on a closed engagement")

    try:
        perms = normalize_area_permissions(invite.area_permissions)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    email = invite.email.strip().lower()

    aud_res = await db.execute(select(Auditor).where(func.lower(Auditor.email) == email))
    auditor = aud_res.scalar_one_or_none()

    if auditor:
        g_res = await db.execute(
            select(AuditorEngagementGrant).where(
                and_(
                    AuditorEngagementGrant.auditor_id == auditor.id,
                    AuditorEngagementGrant.engagement_id == engagement_id,
                )
            )
        )
        grant = g_res.scalar_one_or_none()
        if grant and grant.status != GrantStatus.revoked:
            raise HTTPException(status_code=400, detail="Auditor is already invited to this engagement")
        if grant:  # resurrect the revoked row — keeps uq_grant_auditor_engagement intact
            grant.status = GrantStatus.invited
            grant.invited_at = datetime.now(timezone.utc)
            grant.accepted_at = None
            grant.area_permissions = perms
        else:
            db.add(AuditorEngagementGrant(
                auditor_id=auditor.id, engagement_id=engagement_id,
                status=GrantStatus.invited, area_permissions=perms,
            ))
    else:
        pend_res = await db.execute(
            select(PendingAuditorInvite).where(
                and_(
                    PendingAuditorInvite.engagement_id == engagement_id,
                    func.lower(PendingAuditorInvite.email) == email,
                )
            )
        )
        if pend_res.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="An invite for this email is already pending")
        db.add(PendingAuditorInvite(engagement_id=engagement_id, email=email))

    log_activity(
        db, current_user.company_id, current_user.id,
        "auditor.invited", "audit_engagement", eng.id,
        metadata_={"email": email}, actor_type=ActorType.company_user,
        engagement_id=eng.id,
    )

    if eng.status == EngagementStatus.draft:
        eng.status = EngagementStatus.invited

    await db.commit()
    await db.refresh(eng)
    return await _hydrate_auditors(db, eng)
```

Also update `create_engagement`, `get_engagement`, `close_engagement`, `delete_engagement` responses: wherever they previously returned bare `eng` or called `_hydrate_auditor_info`, call `_hydrate_auditors` instead (`create_engagement` can return `await _hydrate_auditors(db, eng)` too — empty array is fine).

- [ ] **Step 4: Run the new tests**

Run: `pytest tests/test_auditease_multi_auditor.py -v`
Expected: 6 passed

- [ ] **Step 5: Update legacy call sites in `tests/test_auditease.py`**

Mechanical changes across the file (every occurrence):
- Path `.../invite-auditor` → `.../auditors/invite`.
- Assertions on `resp.json()["auditor_email"]` / `["auditor_grant_status"]` → derive from `resp.json()["auditors"]`, e.g. replace the two assertions at old lines 269–270 with:

```python
    auds = resp.json()["auditors"]
    assert len(auds) == 1
    assert auds[0]["email"] == "aud@a.com"
    assert auds[0]["status"] == GrantStatus.invited.value
```

and at old line 329:

```python
    assert resp.json()["auditors"][0]["status"] == "pending"
```

Affected tests: `test_engagement_lifecycle` (line 266), `test_delete_engagement_guard` (308), `test_pending_invite_autoconverts_on_registration` (326), `test_audit_entries` (~770), `test_requirements_and_queries` (~800), `test_auditor_document_access_and_queries` (~854), `test_entry_lines_include_ledger_name` (~932), plus any others surfaced by the run in Step 6.

- [ ] **Step 6: Run the whole auditease suite**

Run: `pytest tests/test_auditease.py tests/test_auditease_multi_auditor.py tests/test_auditease_reports.py -v`
Expected: all pass (fix any remaining legacy call sites until green).

- [ ] **Step 7: Commit**

```bash
git add app/routers/auditease.py tests/test_auditease.py tests/test_auditease_multi_auditor.py
git commit -m "feat(auditease): multi-auditor invites with per-area permissions"
```

---

### Task 5: Auditor-side area enforcement + own permissions on list

**Files:**
- Modify: `app/routers/auditor_engagements.py` (`check_auditor_access` line 34; every endpoint call site)
- Test: `tests/test_auditease_multi_auditor.py` (append tests)

**Interfaces:**
- Consumes: `area_enabled` from Task 2, `AREA_LABELS` from Task 1.
- Produces: `check_auditor_access(db, auditor_id, engagement_id, area=None) -> AuditEngagement` — same signature plus optional trailing arg; raises 403 `"Your access to <Label> was removed by the company."` when area disabled. `GET /api/v1/auditor/engagements` items gain `area_permissions` (the caller's own map).

- [ ] **Step 1: Append failing tests**

Append to `tests/test_auditease_multi_auditor.py`:

```python
@pytest.mark.asyncio
async def test_area_enforcement_blocks_disabled_areas(client: AsyncClient):
    import csv, io

    await create_test_company(client, email="ae@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="ae@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]

    # Import a minimal TB so trial-balance endpoints have data
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Ledger Name", "Closing"])
    w.writerow(["Sales", "100000"])
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/trial-balance/import",
        data={"column_map": '{"ledger_name": "Ledger Name", "closing_balance": "Closing"}'},
        files={"file": ("tb.csv", buf.getvalue(), "text/csv")},
        headers=co,
    )

    aud = await _register_login(client, "restricted@a.com")
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "restricted@a.com", "area_permissions": {}},
        headers=co,
    )
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud)

    # Every gated surface 403s with the clear message
    checks = [
        ("GET", f"/api/v1/auditor/engagements/{eng_id}/trial-balance", None),
        ("GET", f"/api/v1/auditor/engagements/{eng_id}/entries", None),
        ("POST", f"/api/v1/auditor/engagements/{eng_id}/entries",
         {"code": "ADJ1", "description": "d", "lines": []}),
        ("GET", f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", None),
        ("POST", f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
         {"description": "need docs"}),
        ("GET", f"/api/v1/auditor/engagements/{eng_id}/queries", None),
    ]
    for method, url, body in checks:
        if method == "GET":
            resp = await client.get(url, headers=aud)
        else:
            resp = await client.post(url, json=body, headers=aud)
        assert resp.status_code == 403, f"{method} {url} -> {resp.status_code}"
        assert "removed by the company" in resp.json()["detail"]

    # Accept + listing still work (no area gate)
    resp = await client.get("/api/v1/auditor/engagements", headers=aud)
    assert resp.status_code == 200 and len(resp.json()) == 1
    item = resp.json()[0]
    assert item["area_permissions"]["entries"] is False

    # Company widens access -> entries endpoint opens up
    aud_id = (await client.get(f"/api/v1/auditease/engagements/{eng_id}", headers=co)).json()["auditors"][0]["auditor_id"]
    resp = await client.patch(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/{aud_id}",
        json={"area_permissions": {"entries": True}},
        headers=co,
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/entries", headers=aud)
    assert resp.status_code == 200
```

Note: this test also exercises Task 7's PATCH endpoint; if you prefer strict TDD ordering, implement Task 7 Steps 1–3 (PATCH only) first, then return here. The plan orders it here because enforcement and widening share one test.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_auditease_multi_auditor.py::test_area_enforcement_blocks_disabled_areas -v`
Expected: FAIL — disabled-area calls currently return 200 (no area check exists).

- [ ] **Step 3: Implement enforcement**

In `app/routers/auditor_engagements.py`: add imports `from app.models.auditease import AREA_LABELS` (merge into existing import) and `from app.services.auditor_access import area_enabled`.

Replace `check_auditor_access`:

```python
async def check_auditor_access(
    db: AsyncSession,
    auditor_id: uuid.UUID,
    engagement_id: uuid.UUID,
    area: str | None = None,
) -> AuditEngagement:
    query = (
        select(AuditEngagement, AuditorEngagementGrant.area_permissions)
        .join(AuditorEngagementGrant, AuditEngagement.id == AuditorEngagementGrant.engagement_id)
        .where(
            and_(
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.engagement_id == engagement_id,
                AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
                AuditEngagement.status == EngagementStatus.active
            )
        )
    )
    row = (await db.execute(query)).first()
    if not row:
        raise HTTPException(status_code=403, detail="No access to this engagement")
    eng, perms = row
    if area is not None and not area_enabled(perms, area):
        raise HTTPException(
            status_code=403,
            detail=f"Your access to {AREA_LABELS.get(area, area)} was removed by the company.",
        )
    return eng
```

Then pass the area at each call site:
- `get_trial_balance` → `check_auditor_access(db, current_auditor.id, engagement_id, area="trial_balance")`
- `create_entry`, `list_auditor_entries` → `area="entries"`
- `delete_auditor_entry`: this one joins grants inline. Convert it to two steps: first resolve the entry's engagement (`select(AuditEntry.engagement_id).where(AuditEntry.id == entry_id)`), 404 if none, then `check = await check_auditor_access(db, current_auditor.id, eng_id_of_entry, area="entries")` wrapped so a 403 becomes 404 (keep today's opaque behavior):

```python
@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_auditor_entry(
    entry_id: uuid.UUID,
    current_auditor: Annotated[Auditor, Depends(get_current_auditor)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    eng_res = await db.execute(select(AuditEntry.engagement_id).where(AuditEntry.id == entry_id))
    eng_id = eng_res.scalar_one_or_none()
    check = None
    if eng_id:
        try:
            check = await check_auditor_access(db, current_auditor.id, eng_id, area="entries")
        except HTTPException as e:
            if e.status_code != 403:
                raise
    if check is None:
        raise HTTPException(status_code=404, detail="Entry not found or access denied")

    result = await db.execute(
        select(AuditEntry).where(and_(AuditEntry.id == entry_id, AuditEntry.engagement_id == eng_id))
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found or access denied")
    if entry.status != AuditEntryStatus.proposed:
        raise HTTPException(status_code=400, detail="Only proposed entries can be deleted")
    await db.delete(entry)
    await db.commit()
    return None
```

(Actual logging for delete happens in Task 6.)

- Requirements CRUD (`create_requirement`, `update_requirement`, `delete_requirement`, `list_requirements`) → `area="requirements"`
- Queries (`list_queries`, `get_query`, `create_query`, `add_query_message`, `close_query`) → `area="queries"`
- Documents (`get_document`, `download_document`): these authenticate through `doc_access.auditor_can_access_document`, which requires *any* live grant in the doc's company. Add an area check after it succeeds — documents carry no engagement FK, so the rule is "at least one live grant of this auditor at this company has `documents` enabled". In `app/services/document_access.py` extend `auditor_can_access_document`'s final grant query:

```python
    grant = await db.execute(
        select(AuditorEngagementGrant.area_permissions)
        .join(AuditEngagement, AuditEngagement.id == AuditorEngagementGrant.engagement_id)
        .where(
            and_(
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
                AuditEngagement.company_id == doc.company_id,
                AuditEngagement.status != EngagementStatus.closed,
            )
        )
    )
    if not any(area_enabled(p, "documents") for p in grant.scalars().all()):
        return None
    return doc
```

with `from app.models.auditease import EngagementStatus` merged into its auditease import and `from app.services.auditor_access import area_enabled` at top. Note the closed-engagement guard replaces the old implicit behavior (old code didn't filter engagement status there — adding it closes a gap where a revoked-at-close grant could still be `invited`; close revokes all grants anyway, so this is belt-and-braces).

- List endpoint (`list_engagements`): include own permissions. Change the select to `.add_columns(AuditorEngagementGrant.area_permissions)` i.e. select `(AuditEngagement, AuditorEngagementGrant.status, AuditorEngagementGrant.area_permissions)`, and in the loop build the dict with one extra key:

```python
        out.append({
            "id": eng.id,
            "company_id": eng.company_id,
            "period_label": eng.period_label,
            "status": display_status,
            "created_by": eng.created_by,
            "created_at": eng.created_at,
            "updated_at": eng.updated_at,
            "area_permissions": perms or {},
        })
```

(`AuditEngagementResponse.area_permissions` from Task 3 accepts it.)

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_auditease_multi_auditor.py tests/test_auditease.py -v`
Expected: all pass — including the pre-existing lifecycle suite (its TB/entry/query flows use full-access auditors).

- [ ] **Step 5: Commit**

```bash
git add app/routers/auditor_engagements.py app/services/document_access.py tests/test_auditease_multi_auditor.py
git commit -m "feat(auditease): enforce per-area access on auditor surfaces"
```

---

### Task 6: Workspace activity logging (auditor actor)

**Files:**
- Modify: `app/routers/auditor_engagements.py` (accept, entries, requirements, queries, documents endpoints)
- Test: `tests/test_auditease_multi_auditor.py` (append)

**Interfaces:**
- Consumes: `log_activity` (Task 1 signature), `check_auditor_access` returning the engagement (gives `eng.company_id` for logging).
- Produces: actions written with `actor_type=ActorType.auditor`, `actor_id=current_auditor.id`, `engagement_id=<engagement>`:
  - `auditor.grant_accepted` (entity `audit_engagement`)
  - `entry.created` / `entry.deleted` (entity `audit_entry`)
  - `requirement.raised` / `requirement.deleted` (entity `requirement_request`)
  - `query.opened` / `query.replied` / `query.closed` (entity `query`)
  - `document.downloaded` (entity `document`)
  Per the spec, requirement *updates* are intentionally not logged.

- [ ] **Step 1: Append failing test**

```python
@pytest.mark.asyncio
async def test_workspace_actions_are_logged(client: AsyncClient):
    await create_test_company(client, email="lg@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="lg@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    aud = await _register_login(client, "logger@a.com")
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "logger@a.com"}, headers=co)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud)

    await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
                      json={"description": "Bank statements"}, headers=aud)
    req_id = (await client.get(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", headers=aud)).json()[0]["id"]
    await client.delete(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{req_id}", headers=aud)

    q = await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries",
                          data={"initial_message": "hello"}, headers=aud)
    assert q.status_code == 200, q.text
    query_id = q.json()["id"]
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries/{query_id}/messages",
                      data={"text": "any update?"}, headers=aud)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries/{query_id}/close", headers=aud)

    rows = await client.get("/api/v1/activity-log?limit=100", headers=co)
    got = {r["action"] for r in rows.json()}
    assert {"auditor.grant_accepted", "requirement.raised", "requirement.deleted",
            "query.opened", "query.replied", "query.closed"} <= got
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_auditease_multi_auditor.py::test_workspace_actions_are_logged -v`
Expected: FAIL — none of those actions are logged yet.

- [ ] **Step 3: Wire logging into the endpoints**

In `app/routers/auditor_engagements.py` add imports:

```python
from app.models.activity_log import ActorType
from app.services.activity import log_activity
```

Insert a `log_activity(...)` call before each endpoint's `await db.commit()` (or before `db.flush()` where commit comes later), using the engagement captured from `check_auditor_access`:

- `accept_engagement` — after setting `grant.status`, before commit (note: this endpoint has no `eng` variable until it fetches one; it already selects `eng` — reuse it):

```python
    log_activity(db, eng.company_id, current_auditor.id,
                 "auditor.grant_accepted", "audit_engagement", engagement_id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
```

- `create_entry` (uses `eng`):

```python
    log_activity(db, eng.company_id, current_auditor.id,
                 "entry.created", "audit_entry", db_entry.id,
                 metadata_={"description": db_entry.description},
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
```

- `delete_auditor_entry` — before `db.commit()`:

```python
    log_activity(db, check.company_id, current_auditor.id,
                 "entry.deleted", "audit_entry", entry.id,
                 actor_type=ActorType.auditor, engagement_id=eng_id)
```

(capture the `check_auditor_access` return value into `check` in Task 5's rewrite).

- `create_requirement` — capture `eng = await check_auditor_access(...)` (currently discarded), then:

```python
    log_activity(db, eng.company_id, current_auditor.id,
                 "requirement.raised", "requirement_request", db_req.id,
                 metadata_={"title": db_req.title},
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
```

- `delete_requirement` — capture `eng` likewise:

```python
    log_activity(db, eng.company_id, current_auditor.id,
                 "requirement.deleted", "requirement_request", db_req.id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
```

- `create_query`:

```python
    log_activity(db, eng.company_id, current_auditor.id,
                 "query.opened", "query", db_query.id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
```

- `add_query_message`:

```python
    log_activity(db, eng.company_id, current_auditor.id,
                 "query.replied", "query", query_id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
```

- `close_query` — capture the access-call return into `eng`:

```python
    log_activity(db, eng.company_id, current_auditor.id,
                 "query.closed", "query", query_id,
                 actor_type=ActorType.auditor, engagement_id=engagement_id)
```

- `download_document` — just before building the `Response`:

```python
    log_activity(db, doc_full.company_id, current_auditor.id,
                 "document.downloaded", "document", document_id,
                 metadata_={"filename": version.original_filename},
                 actor_type=ActorType.auditor)
```

(no `engagement_id` — documents don't carry one; see Task 5.)

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_auditease_multi_auditor.py tests/test_auditease.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/routers/auditor_engagements.py tests/test_auditease_multi_auditor.py
git commit -m "feat(auditease): log auditor workspace + access events"
```

---

### Task 7: Auditors management endpoints — list, PATCH permissions, DELETE, per-auditor activity feed, close logging

**Files:**
- Modify: `app/routers/auditease.py`
- Test: `tests/test_auditease_multi_auditor.py` (append)

**Interfaces:**
- Consumes: `_list_auditors` (Task 4), `normalize_area_permissions` (Task 2), `log_activity`, schemas from Task 3.
- Produces (all tenant-scoped via `_get_owned_engagement`):
  - `GET /engagements/{id}/auditors` → `List[EngagementAuditorResponse]` (any company user)
  - `PATCH /engagements/{id}/auditors/{auditor_id}` (manager/admin) → updated `EngagementAuditorResponse`; 404 when no live grant; logs `auditor.permissions_updated` with the new map
  - `DELETE /engagements/{id}/auditors/{auditor_id}` (manager/admin) → 204; revokes live grant; 404 when none; logs `auditor.access_revoked`
  - `PATCH /engagements/{id}/close` additionally logs one `engagement.closed` row whose `metadata_` lists `{"revoked_auditor_ids": [...]}`
  - `GET /engagements/{id}/auditors/{auditor_id}/activity?limit=&offset=` → `List[ActivityEventResponse]`, newest first, filtered `company_id` + `engagement_id` + `actor_type=auditor` + `actor_id=auditor_id`, limit capped at 500 (default 50)

(The PATCH endpoint was already exercised by Task 5's widening test; DELETE/re-invite by Task 4's resurrection test.)

- [ ] **Step 1: Append failing tests**

```python
@pytest.mark.asyncio
async def test_per_auditor_activity_feed_filters_and_paginates(client: AsyncClient):
    await create_test_company(client, email="pf@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="pf@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    aud_a = await _register_login(client, "alfa@a.com")
    await _register_login(client, "bravo@a.com")
    for email, h in (("alfa@a.com", aud_a), ("bravo@a.com", await _register_login(client, "bravo@a.com"))):
        await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": email}, headers=co)
        await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=h)

    await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
                      json={"description": "alfa doc"}, headers=aud_a)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
                      json={"description": "bravo doc"},
                      headers=await _register_login(client, "bravo@a.com"))

    auds = (await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors", headers=co)).json()
    alfa = next(a for a in auds if a["email"] == "alfa@a.com")

    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors/{alfa['auditor_id']}/activity", headers=co)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) >= 2  # accepted + raised
    assert all(r["action"] in ("auditor.grant_accepted", "requirement.raised") for r in rows)
    assert rows[0]["created_at"] >= rows[-1]["created_at"]
    # Pagination shape
    resp = await client.get(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/{alfa['auditor_id']}/activity?limit=1&offset=1",
        headers=co,
    )
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_close_revokes_everyone_and_logs_event(client: AsyncClient):
    await create_test_company(client, email="cz@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="cz@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    aud = await _register_login(client, "closethis@a.com")
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "closethis@a.com"}, headers=co)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud)

    resp = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=co)
    assert resp.status_code == 200
    auds = resp.json()["auditors"]
    assert len(auds) == 1 and auds[0]["status"] == "revoked"

    rows = (await client.get("/api/v1/activity-log?limit=100", headers=co)).json()
    assert any(r["action"] == "engagement.closed" for r in rows)


@pytest.mark.asyncio
async def test_patch_unknown_auditor_404(client: AsyncClient):
    import uuid as _u
    await create_test_company(client, email="nf@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="nf@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    resp = await client.patch(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/{_u.uuid4()}",
        json={"area_permissions": {"entries": True}},
        headers=co,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auditor_endpoints_cross_tenant_isolated(client: AsyncClient):
    import uuid as _u

    await create_test_company(client, email="ten1@a.com", password="pass1234")
    await create_test_company(client, email="ten2@a.com", password="pass1234")
    co2 = _headers(await get_company_token(client, email="ten2@a.com", password="pass1234"))
    co1 = _headers(await get_company_token(client, email="ten1@a.com", password="pass1234"))
    eng1 = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co1)).json()["id"]

    base = f"/api/v1/auditease/engagements/{eng1}/auditors"
    assert (await client.get(base, headers=co2)).status_code == 404
    assert (await client.get(f"{base}/{_u.uuid4()}/activity", headers=co2)).status_code == 404
    assert (await client.get(f"{base}/{_u.uuid4()}/activity-report?format=xlsx", headers=co2)).status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_auditease_multi_auditor.py::test_per_auditor_activity_feed_filters_and_paginates tests/test_auditease_multi_auditor.py::test_close_revokes_everyone_and_logs_event tests/test_auditease_multi_auditor.py::test_patch_unknown_auditor_404 tests/test_auditease_multi_auditor.py::test_auditor_endpoints_cross_tenant_isolated -v`
Expected: FAIL — 404s (routes missing) except close-event assertion.

- [ ] **Step 3: Implement the endpoints**

In `app/routers/auditease.py` add schema imports to the existing `app.schemas.auditease` import list: `AuditorInviteCreate` (already needed by Task 4), `AuditorPermissionsUpdate`, `EngagementAuditorResponse`, `ActivityEventResponse`; and `from app.models.activity_log import ActorType, ActivityLog`.

Add after the invite endpoint:

```python
@router.get("/engagements/{engagement_id}/auditors", response_model=List[EngagementAuditorResponse])
async def list_engagement_auditors(
    engagement_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    return await _list_auditors(db, eng.id)


@router.patch("/engagements/{engagement_id}/auditors/{auditor_id}", response_model=EngagementAuditorResponse)
async def update_auditor_access(
    engagement_id: uuid.UUID,
    auditor_id: uuid.UUID,
    body: AuditorPermissionsUpdate,
    current_user: Annotated[CompanyUser, Depends(require_manager_or_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    try:
        perms = normalize_area_permissions(body.area_permissions)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    g_res = await db.execute(
        select(AuditorEngagementGrant).where(
            and_(
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.engagement_id == engagement_id,
                AuditorEngagementGrant.status != GrantStatus.revoked,
            )
        )
    )
    grant = g_res.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=404, detail="No active grant for this auditor on this engagement")

    grant.area_permissions = perms
    log_activity(
        db, current_user.company_id, current_user.id,
        "auditor.permissions_updated", "auditor_engagement_grant", grant.id,
        metadata_={"area_permissions": perms},
        actor_type=ActorType.company_user, engagement_id=eng.id,
    )
    await db.commit()

    aud_res = await db.execute(select(Auditor).where(Auditor.id == auditor_id))
    auditor = aud_res.scalar_one()
    return {
        "auditor_id": auditor.id, "name": auditor.name, "email": auditor.email,
        "status": grant.status.value, "area_permissions": grant.area_permissions,
        "invited_at": grant.invited_at, "accepted_at": grant.accepted_at,
    }


@router.delete("/engagements/{engagement_id}/auditors/{auditor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_engagement_auditor(
    engagement_id: uuid.UUID,
    auditor_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_manager_or_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)
    g_res = await db.execute(
        select(AuditorEngagementGrant).where(
            and_(
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.engagement_id == engagement_id,
                AuditorEngagementGrant.status != GrantStatus.revoked,
            )
        )
    )
    grant = g_res.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=404, detail="No active grant for this auditor on this engagement")

    grant.status = GrantStatus.revoked
    log_activity(
        db, current_user.company_id, current_user.id,
        "auditor.access_revoked", "auditor_engagement_grant", grant.id,
        actor_type=ActorType.company_user, engagement_id=eng.id,
    )
    await db.commit()
    return None


@router.get("/engagements/{engagement_id}/auditors/{auditor_id}/activity", response_model=List[ActivityEventResponse])
async def get_auditor_activity(
    engagement_id: uuid.UUID,
    auditor_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
):
    await _get_owned_engagement(db, current_user.company_id, engagement_id)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    res = await db.execute(
        select(ActivityLog)
        .where(
            and_(
                ActivityLog.company_id == current_user.company_id,
                ActivityLog.engagement_id == engagement_id,
                ActivityLog.actor_type == ActorType.auditor,
                ActivityLog.actor_id == auditor_id,
            )
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": r.id, "action": r.action, "entity_type": r.entity_type,
            "entity_id": r.entity_id, "metadata": r.metadata_, "created_at": r.created_at,
        }
        for r in res.scalars().all()
    ]
```

Update `close_engagement` to log the batch event — after the bulk revoke `update(...)`, before `commit`:

```python
    revoked_ids_res = await db.execute(
        select(AuditorEngagementGrant.auditor_id).where(
            and_(AuditorEngagementGrant.engagement_id == engagement_id,
                 AuditorEngagementGrant.status == GrantStatus.revoked)
        )
    )
    log_activity(
        db, current_user.company_id, current_user.id,
        "engagement.closed", "audit_engagement", eng.id,
        metadata_={"revoked_auditor_ids": [str(a) for a in revoked_ids_res.scalars().all()]},
        actor_type=ActorType.company_user, engagement_id=eng.id,
    )
```

And change its return to `return await _hydrate_auditors(db, eng)`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_auditease_multi_auditor.py tests/test_auditease.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/routers/auditease.py tests/test_auditease_multi_auditor.py
git commit -m "feat(auditease): auditors tab API — list, permissions, remove, activity feed"
```

---

### Task 8: Activity report builder + export endpoint

**Files:**
- Create: `app/services/reporting/activity_report.py`
- Modify: `app/routers/auditease.py` (export endpoint)
- Test: `tests/test_auditease_multi_auditor.py` (append)

**Interfaces:**
- Consumes: `ReportDocument/ReportSection/ReportRow/ColumnSpec/ColumnKind` from `app/services/reporting/document.py`; `render_pdf` (`app.services.reporting.pdf`), `write_document` (`app.services.reporting.workbook`) — both already imported in `routers/auditease.py` around line 1351.
- Produces: `build_auditor_activity_report(events, auditor_name, auditor_email, company_name, period_label) -> ReportDocument` where `events` is a sequence of dicts with keys `action`, `entity_type`, `metadata` (dict|None), `created_at` (datetime). Endpoint: `GET /engagements/{id}/auditors/{auditor_id}/activity-report?format=xlsx|pdf` (any company user) → file download named `auditor_activity_{safe_period}.xlsx|pdf`.

- [ ] **Step 1: Append failing test**

```python
@pytest.mark.asyncio
async def test_activity_report_exports_xlsx_and_pdf(client: AsyncClient):
    await create_test_company(client, email="rp@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="rp@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    aud = await _register_login(client, "reporter@a.com")
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "reporter@a.com"}, headers=co)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud)
    aud_id = (await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors", headers=co)).json()[0]["auditor_id"]

    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors/{aud_id}/activity-report?format=xlsx", headers=co)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(resp.content) > 200

    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors/{aud_id}/activity-report?format=pdf", headers=co)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_auditease_multi_auditor.py::test_activity_report_exports_xlsx_and_pdf -v`
Expected: FAIL — 404, route missing.

- [ ] **Step 3: Write the builder**

Create `app/services/reporting/activity_report.py`:

```python
"""Per-auditor engagement activity report.

Neutral ReportDocument in, rendered twice downstream (xlsx/pdf) like every other
AuditEase report. Pure — takes prepared event dicts, touches no DB.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from app.services.reporting.document import (
    ColumnKind, ColumnSpec, ReportDocument, ReportRow, ReportSection,
)

_COLS = (
    ColumnSpec(header="Timestamp", key="ts", kind=ColumnKind.text, width=24),
    ColumnSpec(header="Action", key="action", kind=ColumnKind.text, width=28),
    ColumnSpec(header="Entity", key="entity", kind=ColumnKind.text, width=24),
    ColumnSpec(header="Details", key="details", kind=ColumnKind.text, width=46),
)


def _details(meta: dict[str, Any] | None) -> str:
    if not meta:
        return ""
    parts = []
    for k, v in meta.items():
        s = str(v)
        parts.append(f"{k}: {s}")
    return "; ".join(parts)[:120]


def build_auditor_activity_report(
    events: Sequence[dict],
    auditor_name: str,
    auditor_email: str,
    company_name: str,
    period_label: str,
) -> ReportDocument:
    rows = tuple(
        ReportRow(cells={
            "ts": e["created_at"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(e["created_at"], datetime) else str(e["created_at"]),
            "action": e["action"],
            "entity": e["entity_type"],
            "details": _details(e.get("metadata")),
        })
        for e in events
    )
    section = ReportSection(title="Activity", columns=_COLS, rows=rows)
    return ReportDocument(
        title=f"Auditor Activity Report — {auditor_name}",
        subtitle=f"{auditor_email} · {len(rows)} event(s)",
        company_name=company_name,
        period_label=period_label,
        units="none",
        sections=(section,),
    )
```

- [ ] **Step 4: Add the export endpoint**

In `app/routers/auditease.py`, near the other report endpoints, add:

```python
@router.get("/engagements/{engagement_id}/auditors/{auditor_id}/activity-report")
async def export_auditor_activity_report(
    engagement_id: uuid.UUID,
    auditor_id: uuid.UUID,
    format: str = "xlsx",
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    from fastapi.responses import StreamingResponse

    eng = await _get_owned_engagement(db, current_user.company_id, engagement_id)

    aud_res = await db.execute(select(Auditor).where(Auditor.id == auditor_id))
    auditor = aud_res.scalar_one_or_none()
    if not auditor:
        raise HTTPException(status_code=404, detail="Auditor not found")

    ev_res = await db.execute(
        select(ActivityLog)
        .where(
            and_(
                ActivityLog.company_id == current_user.company_id,
                ActivityLog.engagement_id == engagement_id,
                ActivityLog.actor_type == ActorType.auditor,
                ActivityLog.actor_id == auditor_id,
            )
        )
        .order_by(ActivityLog.created_at.asc())
    )
    events = [
        {"action": r.action, "entity_type": r.entity_type,
         "metadata": r.metadata_, "created_at": r.created_at}
        for r in ev_res.scalars().all()
    ]

    from app.services.reporting.activity_report import build_auditor_activity_report

    company = await db.get(Company, current_user.company_id)
    company_name = ((company.legal_name if company else None) or (company.name if company else None) or "Company")
    doc = build_auditor_activity_report(
        events, auditor.name, auditor.email, company_name, eng.period_label,
    )

    safe_period = eng.period_label.replace(" ", "_").replace("/", "-")
    if format == "pdf":
        pdf_bytes = render_pdf(doc)
        filename = f"auditor_activity_{safe_period}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    stream = write_document(doc)
    filename = f"auditor_activity_{safe_period}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

If `units="none"` upsets any renderer, use `units="absolute"` instead (money formatting simply never applies — the report has no money columns).

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_auditease_multi_auditor.py tests/test_auditease_reports.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/reporting/activity_report.py app/routers/auditease.py tests/test_auditease_multi_auditor.py
git commit -m "feat(auditease): per-auditor activity report xlsx/pdf export"
```

---

### Task 9: Attribution names on shared-workspace payloads

**Files:**
- Modify: `app/routers/auditease.py` (company entries list + approve; requirements list; queries list/get)
- Modify: `app/routers/auditor_engagements.py` (entries create/list; requirements list/create/update/delete; queries list/get/create/message/close — anywhere those responses are built)
- Test: `tests/test_auditease_multi_auditor.py` (append)

**Interfaces:**
- Consumes: Task 3 schema fields (`created_by_name`, `raised_by_name`, `sender_name`).
- Produces: hydrated names on responses in BOTH routers — the shared workspace shows who did what.

Implementation pattern (repeat for each router): after fetching ORM objects, collect distinct creator ids and resolve names in ONE query, then set plain attributes (Pydantic `from_attributes` picks them up):

```python
async def attach_actor_names(db: AsyncSession, objs: Sequence[Any], id_attr: str, name_attr: str) -> None:
    """Resolve Auditor names for `id_attr` on each obj and set `name_attr`."""
    from app.models.auditor import Auditor

    ids = {getattr(o, id_attr, None) for o in objs}
    ids.discard(None)
    if not ids:
        return
    res = await db.execute(select(Auditor.name, Auditor.id).where(Auditor.id.in_(ids)))
    names = {aid: nm for nm, aid in res.all()}
    for o in objs:
        setattr(o, name_attr, names.get(getattr(o, id_attr, None)))
```

(with `Sequence, Any` imported from `typing`, `select` from `sqlalchemy` at module top).

Query message senders may be company users — handle in the routers directly where messages are serialized: for `QueryMessage` lists, resolve both tables:

```python
async def attach_sender_names(db: AsyncSession, msgs: Sequence[Any]) -> None:
    from app.models.auditor import Auditor
    from app.models.company import CompanyUser

    aud_ids = {m.sender_id for m in msgs if m.sender_type == SenderType.auditor}
    usr_ids = {m.sender_id for m in msgs if m.sender_type == SenderType.company_user}
    names: dict = {}
    if aud_ids:
        res = await db.execute(select(Auditor.name, Auditor.id).where(Auditor.id.in_(aud_ids)))
        names.update({aid: nm for nm, aid in res.all()})
    if usr_ids:
        res = await db.execute(select(CompanyUser.full_name, CompanyUser.id).where(CompanyUser.id.in_(usr_ids)))
        names.update({uid: fn for fn, uid in res.all()})
    for m in msgs:
        m.sender_name = names.get(m.sender_id)
```

Put `attach_sender_names` in `app/services/auditor_access.py` too (it needs `SenderType` from `app.models.auditease` — fine, no cycle).

Call sites (each: after fetching objects, before returning):
- `routers/auditease.py`: company `GET /engagements/{id}/entries` (find the list endpoint), `approve_reject_entry` (single obj → wrap in `[entry]`), company requirements list, company queries list + single query (then `attach_sender_names` over the nested `query.messages`).
- `routers/auditor_engagements.py`: `create_entry` final re-select result → `[entry]`, `list_auditor_entries`, requirements list/create/update/delete returns, queries list/get/create/message returns (messages nested).

- [ ] **Step 1: Append failing test**

```python
@pytest.mark.asyncio
async def test_creator_names_in_shared_workspace(client: AsyncClient):
    await create_test_company(client, email="nm@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="nm@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    aud = await _register_login(client, "named@a.com")
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "named@a.com"}, headers=co)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud)

    req = (await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
                             json={"description": "ledgers"}, headers=aud)).json()
    assert req["raised_by_name"] == "Named"

    # Company side sees the same attribution
    reqs = (await client.get(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests", headers=co)).json()
    assert reqs[0]["raised_by_name"] == "Named"

    q = (await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries",
                           data={"initial_message": "hi"}, headers=aud)).json()
    assert q["messages"][0]["sender_name"] == "Named"
```

(Note: `_register_login` registers with `name=email.split("@")[0].title()` → "Named".)

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_auditease_multi_auditor.py::test_creator_names_in_shared_workspace -v`
Expected: FAIL — fields are None.

- [ ] **Step 3: Implement** per the pattern above, then run:

Run: `pytest tests/test_auditease_multi_auditor.py tests/test_auditease.py -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/services/auditor_access.py app/routers/auditease.py app/routers/auditor_engagements.py tests/test_auditease_multi_auditor.py
git commit -m "feat(auditease): creator/sender attribution names in shared workspace"
```

---

### Task 10: Frontend API layer — types, endpoints, hooks

**Files:**
- Modify: `frontend/src/api/types.ts` (re-exports near line 147–160)
- Modify: `frontend/src/api/endpoints/auditease.ts`
- Modify: `frontend/src/api/hooks/auditease.ts`

**Interfaces:**
- Consumes: regenerated `schema.d.ts` (backend now running with Tasks 1–9).
- Produces hook names used by Task 11: `useEngagementAuditors(engagementId)`, `useInviteEngagementAuditor(engagementId)`, `useUpdateAuditorAccess(engagementId)`, `useRemoveEngagementAuditor(engagementId)`, `useAuditorActivity(engagementId, auditorId)`; endpoint fns `auditeaseEndpoints.listAuditors/inviteAuditor/updateAuditorAccess/removeAuditor/listAuditorActivity`; type exports `EngagementAuditorResponse`, `AuditorInviteCreate`, `AuditorPermissionsUpdate`, `ActivityEventResponse`.

- [ ] **Step 1: Regenerate types**

Start the backend (`uv run uvicorn app.main:app --reload` in a separate terminal or rely on docker compose), then in `frontend/`:

Run: `npm run gen:api`
Expected: `src/api/schema.d.ts` regenerates containing `EngagementAuditorResponse`, `AuditorInviteCreate`, `AuditorPermissionsUpdate`, `ActivityEventResponse`, and `AuditEngagementResponse.auditors`.

- [ ] **Step 2: Re-export types**

In `frontend/src/api/types.ts`, alongside the other auditease re-exports — and **replace** the now-dead `export type AuditorInvite = S['AuditorInvite']` line (the backend schema was removed):

```typescript
export type EngagementAuditorResponse = S['EngagementAuditorResponse']
export type AuditorInviteCreate = S['AuditorInviteCreate']
export type AuditorPermissionsUpdate = S['AuditorPermissionsUpdate']
export type ActivityEventResponse = S['ActivityEventResponse']
```

Fix any compile fallout from the removed singular fields: search usages —

Run: `rg -n "auditor_email|auditor_grant_status" frontend/src`
Expected hits: `EngagementsPage.tsx`, `EngagementWorkspace.tsx`, `EngagementWorkspace.contract.test.tsx`. Update each to read `auditors` (e.g. `const auds = e.auditors ?? []; auds.filter(a => a.status !== 'revoked')` for the header count; the contract test's fixture gains an `auditors: []` field). These edits are completed fully in Task 11/12 — here only make the TypeScript compiler pass minimally (`tsc` must succeed before continuing).

Run: `npx tsc --noEmit` (in `frontend/`)
Expected: exit 0.

- [ ] **Step 3: Endpoints**

In `frontend/src/api/endpoints/auditease.ts`, following the file's existing object style (add `EngagementAuditorResponse`, `AuditorInviteCreate`, `AuditorPermissionsUpdate`, `ActivityEventResponse` to its type imports):

```typescript
  listAuditors: (id: string) =>
    companyClient.get<EngagementAuditorResponse[]>(`/api/v1/auditease/engagements/${id}/auditors`),
  inviteAuditor: (id: string, body: AuditorInviteCreate) =>
    companyClient.post<AuditEngagementResponse>(`/api/v1/auditease/engagements/${id}/auditors/invite`, { body }),
  updateAuditorAccess: (id: string, auditorId: string, body: AuditorPermissionsUpdate) =>
    companyClient.patch<EngagementAuditorResponse>(`/api/v1/auditease/engagements/${id}/auditors/${auditorId}`, { body }),
  removeAuditor: (id: string, auditorId: string) =>
    companyClient.del(`/api/v1/auditease/engagements/${id}/auditors/${auditorId}`),
  listAuditorActivity: (id: string, auditorId: string, limit = 50, offset = 0) =>
    companyClient.get<ActivityEventResponse[]>(`/api/v1/auditease/engagements/${id}/auditors/${auditorId}/activity?limit=${limit}&offset=${offset}`),
```

Check how DELETE is spelled on `companyClient` (grep `del(` / `.delete(` in `frontend/src/api/http.ts`) and match it. Replace the old `inviteAuditor` entry pointing at `/invite-auditor` with the new one above rather than keeping both.

- [ ] **Step 4: Hooks**

In `frontend/src/api/hooks/auditease.ts` follow the file's existing mutation/query hook patterns (they exist for `useInviteAuditor` etc.):

```typescript
export function useEngagementAuditors(engagementId: string) {
  return useQuery({
    queryKey: ['auditease', 'engagements', engagementId, 'auditors'],
    queryFn: () => auditeaseEndpoints.listAuditors(engagementId),
    enabled: !!engagementId,
  })
}

export function useInviteEngagementAuditor(engagementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AuditorInviteCreate) => auditeaseEndpoints.inviteAuditor(engagementId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['auditease', 'engagements', engagementId] })
    },
  })
}

export function useUpdateAuditorAccess(engagementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ auditorId, body }: { auditorId: string; body: AuditorPermissionsUpdate }) =>
      auditeaseEndpoints.updateAuditorAccess(engagementId, auditorId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['auditease', 'engagements', engagementId, 'auditors'] })
    },
  })
}

export function useRemoveEngagementAuditor(engagementId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (auditorId: string) => auditeaseEndpoints.removeAuditor(engagementId, auditorId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['auditease', 'engagements', engagementId] })
    },
  })
}

export function useAuditorActivity(engagementId: string, auditorId: string | null) {
  return useQuery({
    queryKey: ['auditease', 'engagements', engagementId, 'auditors', auditorId, 'activity'],
    queryFn: () => auditeaseEndpoints.listAuditorActivity(engagementId, auditorId!),
    enabled: !!engagementId && !!auditorId,
  })
}
```

(Match exact import style/naming used in the file — read it first; adjust `auditeaseEndpoints` to whatever the file calls the endpoints import.)

- [ ] **Step 5: Verify compile**

Run: `npx tsc --noEmit && npx vitest run src/pages/company/auditease src/api` (in `frontend/`)
Expected: tsc clean; contract test passes or is consciously deferred to Task 12 (if the contract test still references removed fields and cannot pass yet, mark `test.skip` with comment `// TODO(Task 12): update fixture` — resolve before finishing Task 12).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api
git commit -m "feat(auditease-web): auditors-tab api layer (types, endpoints, hooks)"
```

---

### Task 11: AuditorsTab component + modals + workspace wiring

**Files:**
- Create: `frontend/src/pages/company/auditease/AuditorsTab.tsx`
- Create: `frontend/src/pages/company/auditease/EditAuditorAccessModal.tsx`
- Modify: `frontend/src/pages/company/auditease/EngagementWorkspace.tsx` (tabs array ~line 86; render switch ~line 137; header buttons)
- Modify: `frontend/src/pages/company/auditease/EngagementsPage.tsx` (singular-field usages found in Task 10)
- Modify: `frontend/src/pages/company/auditease/EngagementWorkspace.contract.test.tsx` (fixture gains `auditors`)
- Test: `npx vitest run src/pages/company/auditease`

**Interfaces:**
- Consumes: hooks from Task 10; `useCompanyAuth()` → `{ profile }` with `profile.role` (`AssetsPage.tsx:42` precedent); UI kit `Modal, Button, Field, Input, useToast` from `@/components/ui` (see `InviteAuditorModal.tsx` usage).
- Produces: `<AuditorsTab engagementId={string} canManage={boolean} />`.

- [ ] **Step 1: Build `EditAuditorAccessModal.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { Modal, Button, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { EngagementAuditorResponse } from '@/api/types'
import { useUpdateAuditorAccess } from '@/api/hooks/auditease'

const AREAS: { key: keyof Areas; label: string }[] = [
  { key: 'trial_balance', label: 'Trial Balance' },
  { key: 'entries', label: 'Entries' },
  { key: 'requirements', label: 'Requirements' },
  { key: 'queries', label: 'Queries' },
  { key: 'documents', label: 'Documents' },
]

type Areas = Record<string, boolean>

export function EditAuditorAccessModal({
  open, onClose, engagementId, auditor,
}: {
  open: boolean
  onClose: () => void
  engagementId: string
  auditor: EngagementAuditorResponse | null
}) {
  const toast = useToast()
  const update = useUpdateAuditorAccess(engagementId)
  const [areas, setAreas] = useState<Areas>({})

  useEffect(() => {
    if (auditor) setAreas({ ...auditor.area_permissions })
  }, [auditor])

  if (!auditor) return null

  const submit = async () => {
    try {
      await update.mutateAsync({ auditorId: auditor.auditor_id!, body: { area_permissions: areas } })
      toast.success('Access updated')
      onClose()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Update failed')
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Edit access — ${auditor.name ?? auditor.email}`}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={update.isPending}>Save</Button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <p className="text-sm text-text-secondary">
          Choose which parts of AuditEase {auditor.name ?? auditor.email} can work in. Changes take effect immediately.
        </p>
        {AREAS.map(({ key, label }) => (
          <label key={key} className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <span className="text-sm">{label}</span>
            <input
              type="checkbox"
              checked={!!areas[key]}
              onChange={(e) => setAreas((prev) => ({ ...prev, [key]: e.target.checked }))}
              className="h-4 w-4"
            />
          </label>
        ))}
      </div>
    </Modal>
  )
}
```

- [ ] **Step 2: Build `AuditorsTab.tsx`**

Table of auditors with expandable activity timeline and export links; mutations gated behind `canManage`. Follow the styling conventions of sibling tabs (read `RequirementsTab.tsx` first for card/table patterns and reuse them). Core structure:

```tsx
import { useState } from 'react'
import { Button, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { EngagementAuditorResponse } from '@/api/types'
import {
  useEngagementAuditors, useRemoveEngagementAuditor, useAuditorActivity,
} from '@/api/hooks/auditease'
import { EditAuditorAccessModal } from './EditAuditorAccessModal'

const STATUS_STYLES: Record<string, string> = {
  accepted: 'bg-green-100 text-green-800',
  invited: 'bg-blue-100 text-blue-800',
  pending: 'bg-amber-100 text-amber-800',
  revoked: 'bg-gray-100 text-gray-600',
}

function ActivityTimeline({ engagementId, auditor }: { engagementId: string; auditor: EngagementAuditorResponse }) {
  const { data: events, isLoading } = useAuditorActivity(engagementId, auditor.auditor_id)
  if (isLoading) return <p className="p-3 text-sm text-text-secondary">Loading activity…</p>
  if (!events?.length) return <p className="p-3 text-sm text-text-secondary">No activity recorded yet.</p>
  return (
    <ul className="divide-y divide-border">
      {events.map((ev) => (
        <li key={ev.id} className="flex items-baseline gap-3 px-3 py-2 text-sm">
          <span className="w-44 shrink-0 tabular-nums text-text-secondary">
            {new Date(ev.created_at).toLocaleString()}
          </span>
          <span className="font-medium">{ev.action}</span>
          <span className="text-text-secondary">{ev.entity_type}</span>
        </li>
      ))}
    </ul>
  )
}
```

Main component renders one row per auditor: name/email (pending rows show email + "invite pending registration"), status badge via `STATUS_STYLES[status]`, area chips (`Object.entries(a.area_permissions).filter(([, v]) => v).map(([k]) => k)` rendered as small pills), accepted date, and actions: expand toggle (all roles), `Export PDF` / `Export Excel` anchor links to `/api/v1/auditease/engagements/${engagementId}/auditors/${a.auditor_id}/activity-report?format=pdf|xlsx` (all roles — reads are open; the company API client attaches auth automatically only for fetch-based downloads — if the project's download pattern uses raw `<a href>`, mirror however `ReportsTab.tsx` triggers exports and copy that mechanism verbatim), and when `canManage`: `Edit access` + `Remove` buttons.

`Remove` uses a confirm dialog stating "Their past entries, requests and queries stay visible to your team." On confirm: `remove.mutateAsync(auditor.auditor_id!)` with toast + `ApiError` handling, same as elsewhere.

**Pending rows** (`auditor.auditor_id == null`) get no row actions — no expand, exports, edit, or remove (nothing to manage until they register; pending invites clear on close or convert on registration).

- [ ] **Step 3: Wire the tab into `EngagementWorkspace.tsx`**

Read the file. Changes:
1. Tabs array (~line 86): add `{ id: 'auditors', label: 'Auditors' }` (match the array's exact element shape used there).
2. Render switch (~line 137): add the `auditors` case rendering `<AuditorsTab engagementId={engagementId} canManage={canManageAuditors} />`.
3. Compute once near the top:

```tsx
const { profile } = useCompanyAuth()
const canManageAuditors = profile?.role === 'admin' || profile?.role === 'manager'
```

(import `useCompanyAuth` from `@/auth/company` — copy the import path used in `AssetsPage.tsx`.)
4. Header "Invite auditor" button visibility: gate on `canManageAuditors` (previously always shown).
5. Replace every remaining `auditor_email` / `auditor_grant_status` readout with the plural form, e.g. subtitle showing `${live.length} auditor(s)` where `live = (engagement.auditors ?? []).filter(a => a.status === 'invited' || a.status === 'accepted' || a.status === 'pending')`.
6. Pass `canManage` down wherever the old invite modal is opened.

- [ ] **Step 4: Update `EngagementsPage.tsx`**

Replace singular-auditor display (found via grep in Task 10) with the plural: show the first non-revoked auditor email + "+N more" when applicable.

- [ ] **Step 5: Fix the contract test fixture**

In `EngagementWorkspace.contract.test.tsx`, give the engagement fixture an `auditors: []` field (and any asserted auditor state the test relied upon expressed via `auditors` entries). Remove the Task 10 skip if one was added.

- [ ] **Step 6: Verify**

Run: `npx tsc --noEmit && npx vitest run src/pages/company/auditease` (in `frontend/`)
Expected: tsc clean, tests pass.

Manual smoke against dev backend: open an engagement → Auditors tab lists auditors; invite with all areas; edit access to entries-only; log in as that auditor → only Entries visible; remove auditor; export PDF opens.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/company/auditease
git commit -m "feat(auditease-web): Auditors tab with access editing, timeline, exports"
```

---

### Task 12: Invite modal areas + auditor workspace hiding + attribution display

**Files:**
- Modify: `frontend/src/pages/company/auditease/InviteAuditorModal.tsx`
- Modify: `frontend/src/pages/auditor/AuditorEngagementWorkspace.tsx` (tab list derived from `area_permissions`)
- Modify: `frontend/src/pages/auditor/AuditorEntriesTab.tsx`, `frontend/src/pages/auditor/RequirementsTab.tsx` + `QueriesTab.tsx` (creator-name display)
- Modify: `frontend/src/pages/company/auditease/AuditEntriesTab.tsx`, `RequirementsTab.tsx`, `QueriesTab.tsx` (same)
- Test: `npx vitest run src/pages`

**Interfaces:**
- Consumes: `AuditorInviteCreate` (areas optional → undefined means full), auditor list response `area_permissions` field (Task 5), `created_by_name` / `raised_by_name` / `sender_name` response fields (Task 9).
- Produces: complete UX per spec.

- [ ] **Step 1: Extend `InviteAuditorModal.tsx`**

Drop the `currentEmail` prop and the "Inviting a new auditor replaces this one" paragraph entirely. Add five checkboxes, default all checked, submitted only when the user changed something:

```tsx
const AREAS: { key: string; label: string }[] = [
  { key: 'trial_balance', label: 'Trial Balance' },
  { key: 'entries', label: 'Entries' },
  { key: 'requirements', label: 'Requirements' },
  { key: 'queries', label: 'Queries' },
  { key: 'documents', label: 'Documents' },
]
// state: const [areas, setAreas] = useState<Record<string, boolean>>(
//   Object.fromEntries(AREAS.map(a => [a.key, true])))
// touched flag: const [touched, setTouched] = useState(false)
```

Submit body: `touched ? { email, area_permissions: areas } : { email }`. Update callers (workspace/header) to stop passing `currentEmail`. Keep hint copy: "If they don't have an account yet, the invite is held until they register."

- [ ] **Step 2: Auditor workspace tab hiding**

In `AuditorEngagementWorkspace.tsx`, the engagement arrives via navigation from `AuditorEngagements.tsx` (verify: the list page navigates with `state={{ engagement }}` or refetch — follow what exists). Ensure `area_permissions` reaches this component (it is on the Task 5 list response). Filter the tab list:

```tsx
const perms = engagement?.area_permissions ?? {}
const tabs = baseTabs.filter(t => !t.area || perms[t.area] !== false)
```

where `baseTabs` entries gain `area`: overview → none, trial-balance → `'trial_balance'`, entries → `'entries'`, requirements → `'requirements'`, queries → `'queries'`. Server remains authoritative (Task 5).

- [ ] **Step 3: Creator attribution**

In both companies' and auditors' `AuditEntriesTab` / `RequirementsTab` / `QueriesTab`: render `entry.created_by_name`, `req.raised_by_name`, `msg.sender_name` next to timestamps (e.g. small muted text `· Named`). Fields may be null for legacy rows — render only when present. Mirror each file's existing badge/meta styling.

- [ ] **Step 4: Verify**

Run: `npx tsc --noEmit && npx vitest run src/pages` (in `frontend/`)
Expected: clean.

Manual smoke: restricted auditor sees only permitted tabs; company sees creator names on entries/requirements/queries.

- [ ] **Step 5: Full suites + commit**

Run (repo root): `pytest tests/test_auditease.py tests/test_auditease_multi_auditor.py tests/test_auditease_reports.py tests/test_auth.py -v`
Run (frontend/): `npx tsc --noEmit && npx vitest run`

```bash
git add frontend/src
git commit -m "feat(auditease-web): invite-time area selection, workspace gating, attribution"
```

---

## Verification (whole feature)

1. Repo root: `pytest tests/ -v` — entire suite green.
2. `frontend/`: `npx tsc --noEmit && npx vitest run` — clean.
3. Manual E2E (dev stack): company invites 2 auditors (one entries-only) → both accept → both work → company Auditors tab shows timelines + exports → employee account sees tab read-only → remove one auditor → their entries remain attributed → close engagement → both lose access → company still sees all work.
