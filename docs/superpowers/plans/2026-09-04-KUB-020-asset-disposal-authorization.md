# KUB-020: Asset Disposal Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate KUB-020 by enforcing module and role-based authorization on `POST /api/v1/assets/{asset_id}/dispose` and across the fixed-asset register, hardening the frontend, and establishing static reflection regression tests to prevent unauthorized intra-tenant asset manipulation.

**Architecture:** Add router-level `require_assets_module` dependency on `app/routers/assets.py` to enforce module boundaries before handler execution. Annotate `dispose_asset` with `Admin` (`require_admin`) and normalize `approve_asset`/`reject_asset` onto the declarative dependency. Provide a pure `can_dispose_asset` predicate for table-driven unit tests, update frontend components to remove dead role checks and handle 403 responses gracefully, and extend static reflection tests in `tests/test_module_enforcement.py`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (asyncio), asyncpg, pytest, TypeScript, React, TailwindCSS.

## Global Constraints
- Target endpoints: `/api/v1/assets/*`, specifically `POST /api/v1/assets/{asset_id}/dispose`.
- Role system: `UserRole.admin` and `UserRole.employee` (no `manager` role).
- Module gate: `require_assets_module` (`require_module("assets")`).
- Admin role always passes module gates (`user_has_module` in `app/auth.py`).
- Single-admin SoD policy: Do not bar creator or approver from disposing if they are an admin.
- Information disclosure policy: 403 before `_load_asset` execution for unauthorized callers; 404 for non-existent or cross-tenant assets for authorized admins.
- Test constraints: Run only affected test files (`pytest tests/test_asset_disposal.py tests/test_module_enforcement.py tests/test_asset_validation.py -q`). Use `@testco.com` email addresses. Seed masters with `await seed_masters()` where categories/IT blocks are needed.

---

### Task 1: Pure Predicate & Unit Tests (TDD)

**Files:**
- Modify: `app/services/asset_validation.py:370-380`
- Modify: `tests/test_asset_validation.py:280-295`

**Interfaces:**
- Produces: `can_dispose_asset(user: CompanyUser, asset: Asset) -> tuple[bool, str | None]`
- Consumes: `CompanyUser` (`app.models.company`), `Asset`, `AssetLifecycleStatus` (`app.models.assets`)

- [ ] **Step 1: Write the failing unit tests in `tests/test_asset_validation.py`**

Add table-driven unit tests testing the pure authorization and lifecycle predicate across all role and status permutations:

```python
import uuid
import pytest
from app.models.company import CompanyUser, UserRole
from app.models.assets import Asset, AssetLifecycleStatus
from app.services.asset_validation import can_dispose_asset


def test_can_dispose_asset_matrix():
    """Table-driven unit test verifying can_dispose_asset across roles and lifecycle statuses."""
    admin = CompanyUser(id=uuid.uuid4(), company_id=uuid.uuid4(), role=UserRole.admin)
    emp = CompanyUser(id=uuid.uuid4(), company_id=uuid.uuid4(), role=UserRole.employee)

    # Only admin + capitalized is allowed
    cases = [
        # (user, status, expected_ok, expected_err_substring)
        (admin, AssetLifecycleStatus.capitalized, True, None),
        (admin, AssetLifecycleStatus.draft, False, "Only a capitalized asset can be disposed of"),
        (admin, AssetLifecycleStatus.ready, False, "Only a capitalized asset can be disposed of"),
        (admin, AssetLifecycleStatus.disposed, False, "Only a capitalized asset can be disposed of"),
        (emp, AssetLifecycleStatus.capitalized, False, "Insufficient permissions"),
        (emp, AssetLifecycleStatus.draft, False, "Insufficient permissions"),
        (emp, AssetLifecycleStatus.ready, False, "Insufficient permissions"),
        (emp, AssetLifecycleStatus.disposed, False, "Insufficient permissions"),
    ]

    for user, status, expected_ok, expected_msg in cases:
        asset = Asset(id=uuid.uuid4(), company_id=user.company_id, lifecycle_status=status)
        ok, reason = can_dispose_asset(user, asset)
        assert ok is expected_ok, f"Failed for {user.role} with status {status}: got ok={ok}"
        if expected_msg:
            assert expected_msg in (reason or ""), f"Expected '{expected_msg}' in '{reason}'"


def test_can_dispose_asset_creator_approver_allowed_for_admin():
    """An admin who created and approved the asset can still dispose of it (single-admin SoD rule)."""
    admin_id = uuid.uuid4()
    company_id = uuid.uuid4()
    admin = CompanyUser(id=admin_id, company_id=company_id, role=UserRole.admin)
    asset = Asset(
        id=uuid.uuid4(),
        company_id=company_id,
        lifecycle_status=AssetLifecycleStatus.capitalized,
        created_by=admin_id,
        approved_by=admin_id,
    )
    ok, reason = can_dispose_asset(admin, asset)
    assert ok is True
    assert reason is None
```

- [ ] **Step 2: Run unit test to verify it fails**

Run:
```bash
./.venv/bin/pytest tests/test_asset_validation.py -k "test_can_dispose_asset" -v
```
Expected: FAIL with `ImportError: cannot import name 'can_dispose_asset' from 'app.services.asset_validation'`.

- [ ] **Step 3: Implement `can_dispose_asset` in `app/services/asset_validation.py`**

Add the function at the bottom of `app/services/asset_validation.py`:

```python
def can_dispose_asset(user: "CompanyUser", asset: "Asset") -> tuple[bool, Optional[str]]:
    """Pure authorization and lifecycle predicate for asset disposal.
    
    Returns (allowed, reason_if_denied).
    """
    from app.models.company import UserRole

    if user.role != UserRole.admin:
        return False, "Insufficient permissions"
    if asset.lifecycle_status != AssetLifecycleStatus.capitalized:
        return (
            False,
            f"Only a capitalized asset can be disposed of (this asset is {asset.lifecycle_status.value})",
        )
    return True, None
```

- [ ] **Step 4: Run unit test to verify it passes**

Run:
```bash
./.venv/bin/pytest tests/test_asset_validation.py -k "test_can_dispose_asset" -v
```
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git add app/services/asset_validation.py tests/test_asset_validation.py
git commit -m "feat(assets): add can_dispose_asset predicate and unit tests"
```

---

### Task 2: Integration, Edge-Case & Anti-Exploit Tests (Failing Suite)

**Files:**
- Modify: `tests/test_asset_disposal.py`

**Interfaces:**
- Consumes: `admin_headers`, `make_user`, `user_headers` (`tests.asset_helpers`), `client` (`httpx.AsyncClient`)

- [ ] **Step 1: Write integration, edge-case, and anti-exploit tests in `tests/test_asset_disposal.py`**

Append the comprehensive test suite to `tests/test_asset_disposal.py`:

```python
from app.models.activity import ActivityLog


# --- Category 2: Functional / Integration Tests ---

@pytest.mark.asyncio
async def test_employee_with_assets_module_cannot_dispose(client: AsyncClient):
    """An employee with the assets module granted gets 403 Insufficient permissions."""
    admin_h = await admin_headers(client, "admin_disp_e1@testco.com")
    await make_user(client, admin_h, "emp_disp_e1@testco.com", role="employee")
    emp_h = await user_headers(client, "emp_disp_e1@testco.com")

    cats = (await client.get("/api/v1/asset-masters/categories", headers=admin_h)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == "admin_disp_e1@testco.com"))).scalar_one()
        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Employee Disposal Target",
            asset_code="EMP-DISP-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=36,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("50000.00"),
        )
        session.add(cap_asset)
        await session.commit()
        await session.refresh(cap_asset)
        asset_id = str(cap_asset.id)

    res = await client.post(
        f"/api/v1/assets/{asset_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 10000.0,
        },
        headers=emp_h,
    )
    assert res.status_code == 403
    assert "Insufficient permissions" in res.text

    # Verify state is untouched in DB
    async with TestSessionLocal() as session:
        refreshed = await session.get(Asset, uuid.UUID(asset_id))
        assert refreshed.lifecycle_status == AssetLifecycleStatus.capitalized
        assert refreshed.disposal_date is None


@pytest.mark.asyncio
async def test_employee_with_zero_modules_cannot_dispose(client: AsyncClient):
    """An employee with zero accessible modules gets 403 No access to the assets module."""
    admin_h = await admin_headers(client, "admin_disp_zmod@testco.com")
    # Create employee with explicitly empty modules
    create_resp = await client.post(
        "/api/v1/users",
        headers=admin_h,
        json={
            "email": "zero_mod_disp@testco.com",
            "password": "Valid1!Pass",
            "full_name": "Zero Module User",
            "role": "employee",
            "accessible_modules": [],
        },
    )
    assert create_resp.status_code == 201
    emp_h = await user_headers(client, "zero_mod_disp@testco.com")

    cats = (await client.get("/api/v1/asset-masters/categories", headers=admin_h)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == "admin_disp_zmod@testco.com"))).scalar_one()
        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Zero Mod Target",
            asset_code="ZMOD-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=36,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("50000.00"),
        )
        session.add(cap_asset)
        await session.commit()
        await session.refresh(cap_asset)
        asset_id = str(cap_asset.id)

    res = await client.post(
        f"/api/v1/assets/{asset_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 10000.0,
        },
        headers=emp_h,
    )
    assert res.status_code == 403
    assert "No access to the assets module" in res.text


# --- Category 3: Edge-Case Tests ---

@pytest.mark.asyncio
async def test_disposal_auth_checked_before_lifecycle_state(client: AsyncClient):
    """An employee attempting to dispose a draft or already disposed asset gets 403, not 409."""
    admin_h = await admin_headers(client, "admin_edge_auth@testco.com")
    await make_user(client, admin_h, "emp_edge_auth@testco.com", role="employee")
    emp_h = await user_headers(client, "emp_edge_auth@testco.com")

    cats = (await client.get("/api/v1/asset-masters/categories", headers=admin_h)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == "admin_edge_auth@testco.com"))).scalar_one()
        draft_asset = Asset(
            company_id=user.company_id,
            asset_name="Draft Non-Cap Asset",
            asset_code="DRF-EDGE-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.draft,
            operational_status=AssetOperationalStatus.in_use,
            original_cost=Decimal("50000.00"),
        )
        session.add(draft_asset)
        await session.commit()
        await session.refresh(draft_asset)
        asset_id = str(draft_asset.id)

    res = await client.post(
        f"/api/v1/assets/{asset_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 10000.0,
        },
        headers=emp_h,
    )
    # Auth failure (403) must take precedence over lifecycle mismatch (409)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_disposal_auth_checked_before_asset_existence(client: AsyncClient):
    """An employee attempting to dispose a non-existent asset gets 403, not 404 (oracle prevention)."""
    admin_h = await admin_headers(client, "admin_oracle@testco.com")
    await make_user(client, admin_h, "emp_oracle@testco.com", role="employee")
    emp_h = await user_headers(client, "emp_oracle@testco.com")

    bogus_id = str(uuid.uuid4())
    res = await client.post(
        f"/api/v1/assets/{bogus_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 10000.0,
        },
        headers=emp_h,
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_disposal_cross_tenant_returns_404_for_admin(client: AsyncClient):
    """Admin of Company A cannot dispose an asset of Company B, receiving 404 Not Found."""
    admin_a_h = await admin_headers(client, "admin_co_a@testco.com")
    admin_b_h = await admin_headers(client, "admin_co_b@testco.com")

    cats_b = (await client.get("/api/v1/asset-masters/categories", headers=admin_b_h)).json()
    cat_b_id = next(c["id"] for c in cats_b if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user_b = (await session.execute(select(CompanyUser).where(CompanyUser.email == "admin_co_b@testco.com"))).scalar_one()
        asset_b = Asset(
            company_id=user_b.company_id,
            asset_name="Company B Asset",
            asset_code="COB-001",
            category_id=uuid.UUID(cat_b_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=36,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("50000.00"),
        )
        session.add(asset_b)
        await session.commit()
        await session.refresh(asset_b)
        asset_b_id = str(asset_b.id)

    res = await client.post(
        f"/api/v1/assets/{asset_b_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 10000.0,
        },
        headers=admin_a_h,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Asset not found"


@pytest.mark.asyncio
async def test_disposal_double_dispose_returns_409(client: AsyncClient):
    """Calling dispose twice on the same asset: first call returns 200, second returns 409 Conflict."""
    admin_h = await admin_headers(client, "admin_double_disp@testco.com")
    cats = (await client.get("/api/v1/asset-masters/categories", headers=admin_h)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == "admin_double_disp@testco.com"))).scalar_one()
        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Double Disposal Asset",
            asset_code="DBL-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=36,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("50000.00"),
        )
        session.add(cap_asset)
        await session.commit()
        await session.refresh(cap_asset)
        asset_id = str(cap_asset.id)

    payload = {
        "disposal_date": "2024-09-30",
        "disposal_type": "sale",
        "sale_proceeds": 25000.0,
        "buyer_name": "First Buyer",
    }
    first_res = await client.post(f"/api/v1/assets/{asset_id}/dispose", json=payload, headers=admin_h)
    assert first_res.status_code == 200

    second_res = await client.post(
        f"/api/v1/assets/{asset_id}/dispose",
        json={
            "disposal_date": "2024-10-01",
            "disposal_type": "scrap",
            "buyer_name": "Second Buyer",
        },
        headers=admin_h,
    )
    assert second_res.status_code == 409
    assert "Only a capitalized asset can be disposed of" in second_res.text

    # Verify original disposal metadata was not overwritten
    async with TestSessionLocal() as session:
        refreshed = await session.get(Asset, uuid.UUID(asset_id))
        assert refreshed.disposal_date == date(2024, 9, 30)
        assert refreshed.buyer_name == "First Buyer"


# --- Category 4: Anti-Exploit Tests ---

@pytest.mark.asyncio
async def test_kub_020_zero_module_exploit_prevented(client: AsyncClient):
    """KUB-020 Exploit Reproduction:
    Zero-module employee POSTs valid disposal against capitalized asset.
    Must fail with 403 Forbidden, leave asset untouched, and write ZERO activity logs.
    """
    admin_h = await admin_headers(client, "admin_exploit@testco.com")
    create_resp = await client.post(
        "/api/v1/users",
        headers=admin_h,
        json={
            "email": "attacker_zmod@testco.com",
            "password": "Valid1!Pass",
            "full_name": "Attacker Zero Mod",
            "role": "employee",
            "accessible_modules": [],
        },
    )
    assert create_resp.status_code == 201
    emp_h = await user_headers(client, "attacker_zmod@testco.com")

    cats = (await client.get("/api/v1/asset-masters/categories", headers=admin_h)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == "admin_exploit@testco.com"))).scalar_one()
        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="High Value Server",
            asset_code="SRV-KUB020-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=48,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("500000.00"),
        )
        session.add(cap_asset)
        await session.commit()
        await session.refresh(cap_asset)
        asset_id = cap_asset.id

    # Attacker attempts disposal
    res = await client.post(
        f"/api/v1/assets/{asset_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 100.0,  # Understated proceeds
            "buyer_name": "Attacker Shell Corp",
        },
        headers=emp_h,
    )
    assert res.status_code == 403

    # Assert database state and side effects
    async with TestSessionLocal() as session:
        refreshed = await session.get(Asset, asset_id)
        assert refreshed.lifecycle_status == AssetLifecycleStatus.capitalized
        assert refreshed.disposal_date is None
        assert refreshed.sale_proceeds is None
        assert refreshed.disposed_by is None
        assert refreshed.buyer_name is None

        # Assert no activity log row was written
        act_stmt = select(ActivityLog).where(
            ActivityLog.entity_id == asset_id,
            ActivityLog.action == "asset.disposed",
        )
        act_rows = (await session.execute(act_stmt)).scalars().all()
        assert len(act_rows) == 0
```

- [ ] **Step 2: Run tests to verify the vulnerability reproduces (fails)**

Run:
```bash
./.venv/bin/pytest tests/test_asset_disposal.py -k "test_kub_020_zero_module_exploit_prevented" -v
```
Expected: FAIL (returns 200 OK instead of 403 Forbidden, proving the exploit exists!).

- [ ] **Step 3: Commit the test file**

```bash
git add tests/test_asset_disposal.py
git commit -m "test(assets): add integration, edge-case, and anti-exploit tests for KUB-020"
```

---

### Task 3: Backend Router Hardening & Normalization

**Files:**
- Modify: `app/routers/assets.py:1-25`, `app/routers/assets.py:89`, `app/routers/assets.py:736-848`, `app/routers/assets.py:849-933`

**Interfaces:**
- Produces: Hardened `APIRouter` with `dependencies=[Depends(require_assets_module)]`, `dispose_asset` gated with `current_user: Admin`, `approve_asset`/`reject_asset` normalized to `Admin`.
- Consumes: `require_assets_module`, `require_admin` (`app.auth`).

- [ ] **Step 1: Update `app/routers/assets.py` header docstring and router dependencies**

Replace lines 1-11 with truthful permission documentation:
```python
"""Fixed asset register — asset units and lifecycle transitions.

Permission model:
  * module gate — all endpoints require the `assets` module (admins pass all module gates).
  * read — anyone with the `assets` module sees the whole register (company-scoped).
  * create / edit drafts / submit — anyone with the `assets` module.
  * approve -> capitalized — admin only (unreviewed capitalized cost enters the depreciation base).
  * reject -> draft — admin only.
  * edit after capitalization — admin only, and statutory cost/depreciation fields are locked.
  * dispose — admin only (irreversible accounting event removing asset from active gross block with P&L consequences; logged with full user attribution).
  * delete draft — admin only (capitalized assets can never be deleted; they must be disposed).
"""
```

Mount `require_assets_module` on line 89:
```python
router = APIRouter(
    prefix="/api/v1/assets",
    tags=["assets"],
    dependencies=[Depends(require_assets_module)],
)
```

- [ ] **Step 2: Normalize `approve_asset` and `reject_asset`**

In `approve_asset`:
```python
@router.post("/{asset_id}/approve", response_model=TransitionResponse)
async def approve_asset(
    asset_id: uuid.UUID,
    body: TransitionRequest,
    current_user: Admin,
    db: Db,
):
    """ready -> capitalized. Admin only — an unreviewed capitalized cost enters the depreciation base."""
    anchor = await _load_asset(asset_id, current_user.company_id, db)
    units = await _units_for_transition(anchor, body.apply_to_siblings, db)

    updated = []
    now = datetime.now(timezone.utc)
    for unit in units:
        if unit.lifecycle_status != AssetLifecycleStatus.ready:
            if not body.apply_to_siblings:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Only an asset awaiting approval can be capitalized "
                        f"(this asset is {unit.lifecycle_status.value})"
                    ),
                )
            continue
        category = await _category_of(db, unit)
        roles = await _present_doc_roles(db, unit)
        issues = validate_transition(
            unit,
            unit.acquisition,
            AssetLifecycleStatus.capitalized,
            present_doc_roles=roles,
            category=category,
        )
        if issues:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "This asset cannot be capitalized yet",
                    "asset_id": str(unit.id),
                    "asset_code": unit.asset_code,
                    "issues": [i.as_dict() for i in issues],
                },
            )
        unit.lifecycle_status = AssetLifecycleStatus.capitalized
        unit.approved_by = current_user.id
        unit.approved_at = now
        updated.append(unit.id)
        await log_activity(
            db,
            current_user.company_id,
            current_user.id,
            "asset.capitalized",
            "asset",
            unit.id,
            {
                "note": body.note,
                "original_cost": str(unit.original_cost),
                "capitalization_date": str(unit.capitalization_date),
            },
        )

    await db.commit()
    return TransitionResponse(updated=updated, lifecycle_status=AssetLifecycleStatus.capitalized)
```

In `reject_asset`:
```python
@router.post("/{asset_id}/reject", response_model=TransitionResponse)
async def reject_asset(
    asset_id: uuid.UUID,
    body: TransitionRequest,
    current_user: Admin,
    db: Db,
):
    """ready -> draft, so the submitter can fix it."""
    anchor = await _load_asset(asset_id, current_user.company_id, db)
    units = await _units_for_transition(anchor, body.apply_to_siblings, db)

    updated = []
    for unit in units:
        if unit.lifecycle_status != AssetLifecycleStatus.ready:
            continue
        unit.lifecycle_status = AssetLifecycleStatus.draft
        unit.submitted_by = None
        unit.submitted_at = None
        updated.append(unit.id)
        await log_activity(
            db,
            current_user.company_id,
            current_user.id,
            "asset.rejected",
            "asset",
            unit.id,
            {"note": body.note},
        )
    if not updated:
        raise HTTPException(status_code=409, detail="No asset awaiting approval")
    await db.commit()
    return TransitionResponse(updated=updated, lifecycle_status=AssetLifecycleStatus.draft)
```

- [ ] **Step 3: Update `dispose_asset` signature**

Update `dispose_asset` signature to take `current_user: Admin`:
```python
@router.post("/{asset_id}/dispose", response_model=AssetResponse)
async def dispose_asset(
    asset_id: uuid.UUID,
    body: AssetDisposalRequest,
    current_user: Admin,
    db: Db,
):
    """Dispose of a capitalized asset (sale, scrap, write-off, etc.). Admin only."""
    asset = await _load_asset(asset_id, current_user.company_id, db)
    ...
```

- [ ] **Step 4: Run test suite to verify tests pass**

Run:
```bash
./.venv/bin/pytest tests/test_asset_disposal.py -v
```
Expected: All 16 tests PASS.

- [ ] **Step 5: Commit changes**

```bash
git add app/routers/assets.py
git commit -m "fix(assets): gate dispose_asset with Admin and enforce assets module on router"
```

---

### Task 4: Static Reflection Regression Tests

**Files:**
- Modify: `tests/test_module_enforcement.py:10-48`

**Interfaces:**
- Produces: `test_every_module_router_has_a_server_side_gate` covering `/api/v1/assets`, `test_no_route_has_bare_company_user_without_gate`.

- [ ] **Step 1: Update `GATED_ROUTES` in `tests/test_module_enforcement.py`**

Add `"/api/v1/assets": "assets"` to `GATED_ROUTES`:
```python
GATED_ROUTES = {
    "/api/v1/docvault": "docvault",
    "/api/v1/auditease": "auditease",
    "/api/v1/sales": "sales",
    "/api/v1/kra": "kra",
    "/api/v1/notifications": "notifications",
    "/api/v1/activity-log": "activity",
    "/api/v1/depreciation": "assets",
    "/api/v1/financial-years": "assets",
    "/api/v1/assets": "assets",
}
```

- [ ] **Step 2: Add `test_no_route_has_bare_company_user_without_gate`**

Add the generic static reflection test:
```python
ALLOWED_BARE_ROUTES = {
    "/api/v1/auth/company/me",
    "/api/v1/company/profile",
    "/api/v1/company/profile/logo",
    "/api/v1/users/me",
    "/api/v1/users/me/change-password",
    "/api/v1/users/me/avatar",
    "/api/v1/users/{user_id}/avatar",
    "/api/v1/custom-fields/{module}",  # Known deferred gap from KUB-001
}


def test_no_route_has_bare_company_user_without_gate():
    """No route in the app should depend on get_current_company_user without
    either a module gate or a role gate (unless explicitly allowlisted)."""
    from app.auth import get_current_company_user
    from app.main import app

    def inspect_dependencies(route):
        calls = []
        def walk(dep, depth=0):
            if depth > 5:
                return
            for sub in dep.dependencies:
                calls.append(sub.call)
                walk(sub, depth + 1)
        if getattr(route, "dependant", None):
            walk(route.dependant)
        return calls

    unprotected = []
    for route in app.routes:
        path = getattr(route, "path", "")
        calls = inspect_dependencies(route)
        has_user = any(c == get_current_company_user for c in calls)
        has_checker = any(getattr(c, "__name__", "") == "checker" for c in calls)

        if has_user and not has_checker and path not in ALLOWED_BARE_ROUTES:
            unprotected.append((path, getattr(route, "methods", None)))

    assert not unprotected, f"Found routes using bare get_current_company_user without role/module gate: {unprotected}"
```

- [ ] **Step 3: Run static tests to verify they pass**

Run:
```bash
./.venv/bin/pytest tests/test_module_enforcement.py -k "test_every_module_router_has_a_server_side_gate or test_no_route_has_bare_company_user_without_gate" -v
```
Expected: PASS.

- [ ] **Step 4: Commit changes**

```bash
git add tests/test_module_enforcement.py
git commit -m "test(auth): add /api/v1/assets to GATED_ROUTES and assert no bare user dependencies"
```

---

### Task 5: Frontend Hardening & 403 Response Handling

**Files:**
- Modify: `frontend/src/pages/company/assets/AssetDetailPage.tsx:95-97`, `frontend/src/pages/company/assets/AssetDetailPage.tsx:250`
- Modify: `frontend/src/pages/company/assets/AssetDisposalModal.tsx:58-62`

**Interfaces:**
- Consumes: `ApiError` (`@/api/http`), `useToast` (`@/components/ui`)

- [ ] **Step 1: Clean up role checks in `AssetDetailPage.tsx`**

In `frontend/src/pages/company/assets/AssetDetailPage.tsx`:
Replace lines 95-96:
```typescript
  const isAdmin = profile?.role === 'admin'
  const canApprove = isAdmin
  const canDispose = isAdmin
```

Update line 250:
```typescript
            {asset.lifecycle_status === 'capitalized' && (
              <>
                <span className="inline-flex items-center gap-1.5 text-sm text-status-verified">
                  <CheckCircle2 className="h-4 w-4" />
                  On the books
                </span>
                {canDispose && (
                  <Button variant="secondary" size="sm" onClick={() => setDisposalOpen(true)}>
                    Dispose Asset
                  </Button>
                )}
              </>
            )}
```

- [ ] **Step 2: Add 403 error handling to `AssetDisposalModal.tsx`**

Import `ApiError`:
```typescript
import { ApiError } from '@/api/http'
```

Update `handleSubmit` catch block:
```typescript
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        toast.error(err.message || 'You do not have permission to dispose of assets.')
        onClose()
      } else {
        toast.error(err instanceof Error ? err.message : 'Failed to dispose asset')
      }
    } finally {
      setLoading(false)
    }
```

- [ ] **Step 3: Verify frontend type-checks cleanly**

Run:
```bash
cd frontend && npm run build
```
Expected: Build passes with 0 errors.

- [ ] **Step 4: Commit changes**

```bash
git add frontend/src/pages/company/assets/AssetDetailPage.tsx frontend/src/pages/company/assets/AssetDisposalModal.tsx
git commit -m "fix(frontend): align asset disposal with admin role and handle 403 error in modal"
```

---

### Task 6: Full Verification Suite

**Files:** None (verification step)

- [ ] **Step 1: Run the backend test suite**

Run:
```bash
./.venv/bin/pytest tests/test_asset_disposal.py tests/test_module_enforcement.py tests/test_asset_validation.py -v
```
Expected: All tests pass.

- [ ] **Step 2: Run frontend linter and build check**

Run:
```bash
cd frontend && npm run build
```
Expected: Clean build without type errors or warnings.
