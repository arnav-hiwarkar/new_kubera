# Existing Assets & Editable Masters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every fixed-asset master editable per tenant (fork-at-creation), add an existing-asset entry page with Excel/CSV bulk import, split the Add-asset flow, fix the category picker, and guard master edits with live impact analysis plus a reopen path for finalized depreciation years.

**Architecture:** No DB schema changes. Companies get private copies of the seeded Schedule II categories and Appendix I IT blocks at creation (`initialize_company` forks inside its transaction; a lazy guard re-forks empties). Master endpoints become strictly company-scoped. New endpoints: IT-block PATCH, master impact-preview, depreciation-run reopen, `POST /assets/existing`, import template + bulk import. Frontend: picker state fix, Add-asset dropdown, ExistingAssetPage, edit modals with impact notices, reopen/import UI.

**Tech Stack:** FastAPI + SQLAlchemy async (pytest-asyncio, httpx), openpyxl, React + TypeScript + TanStack Query (vitest + @testing-library/react).

**Spec:** `docs/superpowers/specs/2026-08-22-existing-assets-editable-masters-design.md`

## Global Constraints

- Every query touching tenant data filters by authenticated `company_id` — no exceptions.
- No hard deletes of master rows; deactivate via `is_active = false`.
- Backend tests: `pytest tests/<file> -v` from repo root. Frontend tests: `npx vitest run <path>` from `frontend/`.
- Follow each file's conventions: module docstrings explain *why*; money is `Decimal`; dates are `date`.
- Masters writes are admin-only (`require_admin`); asset creation is assets-module member (`require_assets_module`).
- Commit after every task (conventional messages).

---

### Task 1: Fork statutory masters into every new company

**Files:**
- Modify: `app/services/asset_seed.py`
- Modify: `app/routers/auth.py` (`initialize_company`, after line ~109)
- Modify: `app/routers/asset_masters.py` (list endpoints)
- Create: `tests/test_master_forking.py`

**Interfaces:**
- Consumes: existing constants `IT_BLOCKS`, `CATEGORY_TREE` in `asset_seed.py`.
- Produces: `seed_global_asset_reference_data(db, company_id=None) -> dict` and `ensure_company_masters_forked(db, company_id) -> bool` in `app.services.asset_seed`. All later tasks rely on companies owning their masters.

- [ ] **Step 1: Write the failing test**

```python
"""Companies own private copies of the statutory masters from creation."""
import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.asset_masters import AssetCategory, ItAssetBlock
from tests.asset_helpers import admin_headers
from tests.conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_new_company_owns_forked_categories_and_blocks(client: AsyncClient):
    AH = await admin_headers(client, "fork_new@a.com")

    blocks = (await client.get("/api/v1/asset-masters/it-blocks", headers=AH)).json()
    assert len(blocks) == 11
    assert all(b["company_id"] is not None for b in blocks)

    cats = (await client.get("/api/v1/asset-masters/categories", headers=AH)).json()
    assert all(c["company_id"] is not None for c in cats)
    laptops = next(c for c in cats if c["name"].startswith("End user devices"))
    assert laptops["default_useful_life_months"] == 36


@pytest.mark.asyncio
async def test_lazy_autofork_refills_an_empty_company(client: AsyncClient):
    AH = await admin_headers(client, "fork_lazy@a.com")

    # Simulate a pre-change company whose masters were never forked.
    async with TestSessionLocal() as session:
        await session.execute(delete(ItAssetBlock).where(ItAssetBlock.company_id.isnot(None)))
        await session.execute(delete(AssetCategory).where(AssetCategory.company_id.isnot(None)))
        await session.commit()

    cats = (await client.get("/api/v1/asset-masters/categories", headers=AH)).json()
    assert len([c for c in cats if c["parent_id"] is None]) >= 9

    again = (await client.get("/api/v1/asset-masters/categories", headers=AH)).json()
    assert len(again) == len(cats)


@pytest.mark.asyncio
async def test_helper_is_noop_when_company_already_owns_masters(client: AsyncClient):
    from app.services.asset_seed import ensure_company_masters_forked

    await admin_headers(client, "fork_dup@a.com")
    async with TestSessionLocal() as session:
        cid = (await session.execute(
            __import__("sqlalchemy").select(AssetCategory.company_id).limit(1)
        )).scalar_one()
        assert await ensure_company_masters_forked(session, cid) is False
```

Note: `admin_headers` creates the company through the real `POST /api/v1/auth/companies`, so Step 4's hook makes test 1 pass.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_master_forking.py -v`
Expected: FAIL — lists empty or `company_id` null.

- [ ] **Step 3: Parameterize the async seeder**

In `app/services/asset_seed.py`, change only the async function (the sync migration twin stays untouched):

```python
async def seed_global_asset_reference_data(
    db: AsyncSession, company_id: uuid.UUID | None = None
) -> dict:
    """Create or update the Schedule II tree and Appendix I blocks.

    company_id=None maintains the global template rows. With a company_id it
    forks the same constants into that company's private scope — the mechanism
    that gives every tenant editable masters at creation.
    """
```

Inside that function replace: block query `.where(ItAssetBlock.company_id.is_(None))` → `.where(ItAssetBlock.company_id == company_id)`; same for the categories query; `ItAssetBlock(code=code, company_id=None)` → `company_id=company_id`; both `AssetCategory(company_id=None, ...)` constructions → `company_id=company_id`. Add `import uuid` at module top if missing.

Append the lazy guard:

```python
async def ensure_company_masters_forked(db: AsyncSession, company_id: uuid.UUID) -> bool:
    """Fork the statutory template into company scope if the company owns none.

    Safety net for companies created before fork-at-creation. The unique indexes
    on (company_id, parent_id, name) and (company_id, code) turn a concurrent
    double-fork into IntegrityError; the loser rolls back and keeps the winner's
    copy, so duplicates are impossible either way.
    """
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    cats = (await db.execute(
        select(func.count()).select_from(AssetCategory).where(AssetCategory.company_id == company_id)
    )).scalar_one()
    blocks = (await db.execute(
        select(func.count()).select_from(ItAssetBlock).where(ItAssetBlock.company_id == company_id)
    )).scalar_one()
    if cats or blocks:
        return False
    try:
        await seed_global_asset_reference_data(db, company_id=company_id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
    return True
```

- [ ] **Step 4: Hook fork into company initialization**

In `app/routers/auth.py::initialize_company`, right after `await db.flush()` following `db.add(company)`:

```python
    # Every company gets its own editable copy of the statutory masters inside
    # this transaction.
    from app.services.asset_seed import seed_global_asset_reference_data
    await seed_global_asset_reference_data(db, company_id=company.id)
```

- [ ] **Step 5: Wire the lazy guard into list endpoints**

First line of `list_it_blocks` and `list_categories` bodies in `app/routers/asset_masters.py`:

```python
    from app.services.asset_seed import ensure_company_masters_forked
    await ensure_company_masters_forked(db, current_user.company_id)
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_master_forking.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add app/services/asset_seed.py app/routers/auth.py app/routers/asset_masters.py tests/test_master_forking.py
git commit -m "feat(assets): fork statutory masters into every company at creation"
```

---

### Task 2: Company-scope all master reads/writes; drop seeded-global special cases

**Files:**
- Modify: `app/routers/asset_masters.py`
- Modify: `app/services/depreciation_query.py` (block query ~line 288)
- Modify: `tests/test_asset_masters.py`
- Modify: `tests/test_depreciation_api.py` (environment setup)
- Sweep: any other `tests/` file calling `seed_masters()` (see Step 4)

**Interfaces:**
- Consumes: Task 1 fork (companies always own rows).
- Produces: masters APIs that only see/return company-owned rows; depreciation engine reads company-owned blocks only.

- [ ] **Step 1: Rewrite the stale global-seeding test**

Replace `test_seeded_globals_visible_to_every_company` in `tests/test_asset_masters.py` entirely:

```python
@pytest.mark.asyncio
async def test_statutory_defaults_survive_the_fork(client: AsyncClient):
    """Forked rows carry the statutory figures verbatim — and are owned."""
    AH = await admin_headers(client, "am_seed@a.com")

    blocks = (await client.get(f"{MASTERS}/it-blocks", headers=AH)).json()
    by_code = {b["code"]: b for b in blocks}
    assert by_code["PM-40-COMP"]["dep_rate"] == 40.0
    assert by_code["PM-15"]["dep_rate"] == 15.0
    assert by_code["BLD-10"]["dep_rate"] == 10.0
    assert by_code["INT-25"]["dep_rate"] == 25.0
    assert all(b["company_id"] is not None for b in blocks)

    cats = (await client.get(f"{MASTERS}/categories", headers=AH)).json()
    parents = [c for c in cats if c["parent_id"] is None]
    assert {"Buildings", "Motor vehicles", "Computers and data processing units"} <= {
        c["name"] for c in parents
    }
    laptops = next(c for c in cats if c["name"] == "End user devices (desktops, laptops, printers)")
    assert laptops["default_useful_life_months"] == 36
    assert laptops["default_dep_method"] == "slm"
    assert laptops["default_residual_pct"] == 5.0
    assert laptops["tag_prefix"] == "COMP"
    assert laptops["default_it_block_code"] == "PM-40-COMP"
    cars = next(c for c in cats if c["name"].startswith("Motor cars"))
    assert cars["default_itc_treatment"] == "blocked"
```

Remove the now-unneeded `seed_masters` import/call in this file if present.

- [ ] **Step 2: Run to confirm failure mode**

Run: `pytest tests/test_asset_masters.py -v`
Expected: rewritten test FAILS on `company_id is not None`.

- [ ] **Step 3: Scope the router**

In `app/routers/asset_masters.py`:

- `list_it_blocks`: drop `or_(...)`; filter `ItAssetBlock.company_id == current_user.company_id`.
- `list_categories`: same with `AssetCategory.company_id == current_user.company_id`.
- `_load_category_for_write`: delete the entire seeded-global 403 branch; add tenant filter:

```python
    result = await db.execute(
        select(AssetCategory).where(
            AssetCategory.id == category_id,
            AssetCategory.company_id == company_id,
        )
    )
```

- `create_category`: parent-existence query loses `or_(...)` → `AssetCategory.company_id == current_user.company_id`; identical change in the `default_it_block_id` existence check.
- Remove the unused `or_` import if nothing else uses it.

In `app/services/depreciation_query.py`:

```python
    block_stmt = select(ItAssetBlock).where(ItAssetBlock.company_id == company_id)
```

- [ ] **Step 4: Fix the depreciation test environment + sweep seed_masters callers**

`tests/test_depreciation_api.py::setup_depreciation_environment` seeds globals and picks `select(ItAssetBlock)).scalars().first()` — which may pick a global block the engine now ignores. Replace seeding + selection:

```python
async def setup_depreciation_environment(client: AsyncClient, email: str = "admin_depapi@testco.com"):
    headers = await admin_headers(client, email)  # fork happens at creation

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy_res.status_code == 201, fy_res.text
    fy_id = fy_res.json()["id"]

    # Take ids from the API so they are guaranteed company-owned.
    blocks = (await client.get("/api/v1/asset-masters/it-blocks", headers=headers)).json()
    block_id = next(b["id"] for b in blocks if b["code"] == "PM-15")
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        asset = Asset(
            company_id=user.company_id,
            asset_name="Server Rack",
            asset_code="SRV-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
            it_block_id=uuid.UUID(block_id),
            it_dep_rate=Decimal("15.00"),
            it_put_to_use_date=date(2024, 4, 1),
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        asset_id = str(asset.id)

    return {"headers": headers, "fy_id": fy_id, "asset_id": asset_id}
```

Add `import uuid` at top; remove the `seed_masters` import here.

Sweep: run `rg -l seed_masters tests/`. In every remaining caller that also creates a company via `admin_headers` (e.g. `test_asset_disposal.py`, `test_asset_reports.py`, `test_assets.py`, `test_asset_costing.py`, `test_asset_validation.py`): delete the `seed_masters()` call + import, and switch any direct unscoped selects like `(select(AssetCategory)).scalars().first()` / `(select(ItAssetBlock)).scalars().first()` to fetching ids through the API exactly as shown above (filter `code == "PM-15"` or a non-null `parent_id`). Keep the helper itself in `asset_helpers.py` — engine-pure unit tests may still want template rows.

- [ ] **Step 5: Run affected suites**

Run: `pytest tests/test_asset_masters.py tests/test_depreciation_api.py tests/test_asset_disposal.py tests/test_asset_reports.py tests/test_assets.py tests/test_asset_costing.py tests/test_asset_validation.py -v`
Expected: PASS. Fix stragglers with the API-fetch pattern.

- [ ] **Step 6: Trim frontend lock icon copy**

In `CategoriesTab.tsx`: remove the `Lock` import and the `{group.parent.company_id === null && (<Lock ... />)}` block; rewrite the explainer paragraph:

```tsx
          <p className="max-w-2xl text-sm text-text-muted">
            Categories carry the defaults that keep the asset form short — Schedule II
            useful life, SLM/WDV, residual value, the income-tax block and the tag prefix.
            Your company owns its own editable copy of the statutory set.
          </p>
```

- [ ] **Step 7: Commit**

```bash
git add app/routers/asset_masters.py app/services/depreciation_query.py tests/ frontend/src/pages/company/assets/masters/CategoriesTab.tsx
git commit -m "feat(assets): strictly company-scoped masters, seeded-global special cases removed"
```

---

### Task 3: IT-block update endpoint

**Files:**
- Modify: `app/schemas/asset_masters.py`
- Modify: `app/routers/asset_masters.py`
- Test: `tests/test_asset_masters.py` (append)

**Interfaces:**
- Consumes: company-scoped router (Task 2).
- Produces: `PATCH /api/v1/asset-masters/it-blocks/{id}` with body `ItAssetBlockUpdate`; 404 cross-tenant/unknown; 409 duplicate code; 422 out-of-bounds rate; 403 non-admin. Frontend Task 10 consumes via `updateItBlock(id, body)`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_asset_masters.py`:

```python
@pytest.mark.asyncio
async def test_admin_can_edit_it_block(client: AsyncClient):
    AH = await admin_headers(client, "am_itedit@a.com")
    blocks = (await client.get(f"{MASTERS}/it-blocks", headers=AH)).json()
    target = next(b for b in blocks if b["code"] == "PM-15")

    resp = await client.patch(
        f"{MASTERS}/it-blocks/{target['id']}",
        json={"name": "Plant and machinery — general (edited)"},
        headers=AH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"].endswith("(edited)")


@pytest.mark.asyncio
async def test_it_block_edit_rejects_bad_input_and_duplicates(client: AsyncClient):
    AH = await admin_headers(client, "am_itbad@a.com")
    blocks = (await client.get(f"{MASTERS}/it-blocks", headers=AH)).json()
    pm = next(b for b in blocks if b["code"] == "PM-15")
    comp = next(b for b in blocks if b["code"] == "PM-40-COMP")

    assert (await client.patch(
        f"{MASTERS}/it-blocks/{pm['id']}", json={"dep_rate": 120}, headers=AH
    )).status_code == 422  # bounds 0..100

    dup = await client.patch(
        f"{MASTERS}/it-blocks/{pm['id']}", json={"code": "pm-40-comp"}, headers=AH
    )
    assert dup.status_code == 409  # case-insensitive uniqueness

    deact = await client.patch(
        f"{MASTERS}/it-blocks/{comp['id']}", json={"is_active": False}, headers=AH
    )
    assert deact.status_code == 200 and deact.json()["is_active"] is False


@pytest.mark.asyncio
async def test_non_admin_cannot_edit_it_block(client: AsyncClient):
    from tests.asset_helpers import make_user, user_headers

    AH = await admin_headers(client, "am_itadm@a.com")
    await admin_headers(client, "am_itemp@a.com")  # isolation company

    await make_user(client, AH, "am_itstaff@a.com")
    UH = await user_headers(client, "am_itstaff@a.com")

    mine = (await client.get(f"{MASTERS}/it-blocks", headers=AH)).json()
    resp = await client.patch(
        f"{MASTERS}/it-blocks/{mine[0]['id']}", json={"name": "nope"}, headers=UH
    )
    assert resp.status_code == 403
```

Also move Task 2's deferred `test_tenant_isolation_on_master_writes` here if you skipped it earlier (it PATCHes a cross-tenant block and expects 404).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_asset_masters.py -k it_block -v`
Expected: FAIL — 405 (route absent).

- [ ] **Step 3: Add schema + endpoint**

Schema beside `ItAssetBlockCreate` in `app/schemas/asset_masters.py`:

```python
class ItAssetBlockUpdate(BaseModel):
    """Partial edit of a company-owned Appendix I block."""
    code: Optional[str] = Field(default=None, min_length=1, max_length=30)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    dep_rate: Optional[float] = Field(default=None, ge=0, le=100)
    block_class: Optional[ItBlockClass] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None
```

Router under the IT-blocks section in `app/routers/asset_masters.py` (`ItAssetBlockUpdate` added to schema imports):

```python
@router.patch("/it-blocks/{block_id}", response_model=ItAssetBlockResponse)
async def update_it_block(
    block_id: uuid.UUID, body: ItAssetBlockUpdate, current_user: CurrentAdmin, db: Db
):
    result = await db.execute(
        select(ItAssetBlock).where(
            ItAssetBlock.id == block_id,
            ItAssetBlock.company_id == current_user.company_id,
        )
    )
    block = result.scalar_one_or_none()
    if block is None:
        raise HTTPException(status_code=404, detail="Block not found")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(block, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A block with this code already exists")
    await db.refresh(block)
    return block
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_asset_masters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/asset_masters.py app/routers/asset_masters.py tests/test_asset_masters.py
git commit -m "feat(assets): PATCH endpoint for company-owned IT blocks"
```

---

### Task 4: Master impact-preview endpoint

**Files:**
- Create: `app/services/master_impact.py`
- Modify: `app/schemas/asset_masters.py`
- Modify: `app/routers/asset_masters.py`
- Create: `tests/test_master_impact.py`

**Interfaces:**
- Consumes: company-scoped masters (Task 2), `DepreciationRun`, `AssetDepreciationLine`, `ItBlockDepreciationLine`, `FinancialYear`.
- Produces:
  - `GET /api/v1/asset-masters/{kind}/{row_id}/impact-preview` (admin), kind ∈ {category, it_block, supplier, lookup}.
  - `ImpactPreviewResponse(kind, id, assets_referencing, draft_run_fy_labels, finalized_run_fy_labels, classification "none"|"future_only", message)`.
  - `compute_master_impact(db, company_id, kind, row_id) -> ImpactPreviewResponse`. Frontend Task 10 consumes.

- [ ] **Step 1: Write the failing test**

```python
"""Live impact facts shown inside masters edit dialogs."""
import pytest
from httpx import AsyncClient

from tests.test_depreciation_api import setup_depreciation_environment

MASTERS = "/api/v1/asset-masters"


@pytest.mark.asyncio
async def test_category_default_edit_classifies_no_effect_with_explanation(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, "mi_cat@testco.com")
    headers = ctx["headers"]
    cats = (await client.get(f"{MASTERS}/categories", headers=headers)).json()
    leaf = next(c for c in cats if c["parent_id"] is not None)

    resp = await client.get(f"{MASTERS}/category/{leaf['id']}/impact-preview", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["classification"] == "none"
    assert "new assets" in body["message"].lower()


@pytest.mark.asyncio
async def test_block_rate_edit_names_finalized_years_and_reopen_hint(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, "mi_blk@testco.com")
    headers, fy_id = ctx["headers"], ctx["fy_id"]

    run = (await client.post("/api/v1/depreciation/runs",
                             json={"financial_year_id": fy_id}, headers=headers)).json()
    fin = await client.post(f"/api/v1/depreciation/runs/{run['id']}/finalize", headers=headers)
    assert fin.status_code == 200

    blocks = (await client.get(f"{MASTERS}/it-blocks", headers=headers)).json()
    block = next(b for b in blocks if b["code"] == "PM-15")

    resp = await client.get(f"{MASTERS}/it_block/{block['id']}/impact-preview", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["finalized_run_fy_labels"] == ["2024-25"]
    assert "reopen" in body["message"].lower()
    assert body["classification"] == "future_only"


@pytest.mark.asyncio
async def test_unknown_kind_is_404(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, "mi_404@testco.com")
    resp = await client.get(f"{MASTERS}/widget/00000000-0000-0000-0000-000000000000/impact-preview",
                            headers=ctx["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_impact_preview_requires_admin(client: AsyncClient):
    from tests.asset_helpers import make_user, user_headers

    ctx = await setup_depreciation_environment(client, "mi_auth@testco.com")
    AH = ctx["headers"]
    await make_user(client, AH, "mi_staff@testco.com")
    UH = await user_headers(client, "mi_staff@testco.com")

    cats = (await client.get(f"{MASTERS}/categories", headers=AH)).json()
    resp = await client.get(f"{MASTERS}/category/{cats[0]['id']}/impact-preview", headers=UH)
    assert resp.status_code == 403
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_master_impact.py -v`
Expected: FAIL — 404 route absent.

- [ ] **Step 3: Implement schema + service**

In `app/schemas/asset_masters.py` (add `List` to typing imports):

```python
# === Impact preview ===

class ImpactPreviewResponse(BaseModel):
    kind: str
    id: uuid.UUID
    assets_referencing: int
    draft_run_fy_labels: List[str]
    finalized_run_fy_labels: List[str]
    classification: str  # "none" | "future_only"
    message: str
```

Create `app/services/master_impact.py`:

```python
"""Live 'what does editing this master row affect?' analysis.

Finalized depreciation runs store snapshot lines, so a master edit can never
retroactively change history — effects classify exhaustively as `none`
(cosmetic, or defaults copied onto future assets only) or `future_only` (feeds
future run math). When finalized years were computed at values that differ from
the row's current state, the message says to reopen those years rather than
pretending nothing happened.
"""
import uuid
from typing import List, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import Asset, AssetAcquisition, AssetLifecycleStatus
from app.models.depreciation import (
    AssetDepreciationLine,
    DepreciationRun,
    DepreciationRunStatus,
    ItBlockDepreciationLine,
)
from app.schemas.asset_masters import ImpactPreviewResponse

Kind = Literal["category", "it_block", "supplier", "lookup"]

_NO_EFFECT_BY_KIND = {
    "category": (
        "No effect on existing assets — category defaults are copied onto new "
        "assets at creation only. Renames update register labels."
    ),
    "supplier": "Register labels update; GST snapshots on acquisitions stay as captured.",
    "lookup": "Register labels update for assets assigned to this value.",
}
_FUTURE_ONLY_MESSAGE = (
    "Future depreciation runs will use the new values. Finalized years keep "
    "their stored figures."
)


async def compute_master_impact(
    db: AsyncSession, company_id: uuid.UUID, kind: Kind, row_id: uuid.UUID
) -> ImpactPreviewResponse:
    assets_referencing = await _count_referencing_assets(db, company_id, kind, row_id)
    draft_fys, final_fys = await _run_fys(db, company_id, kind, row_id)

    classification = "none"
    message = _NO_EFFECT_BY_KIND[kind]

    if kind == "it_block":
        classification = "future_only"
        message = _FUTURE_ONLY_MESSAGE
        if final_fys:
            rates = (
                await db.execute(
                    select(ItBlockDepreciationLine.prescribed_rate)
                    .join(DepreciationRun, DepreciationRun.id == ItBlockDepreciationLine.run_id)
                    .where(
                        DepreciationRun.company_id == company_id,
                        ItBlockDepreciationLine.it_block_id == row_id,
                        DepreciationRun.status == DepreciationRunStatus.finalized.value,
                    )
                )
            ).scalars().all()
            rates_txt = ", ".join(f"{float(r):g}%" for r in sorted(set(rates)))
            message = (
                f"Finalized years ({', '.join(sorted(final_fys))}) were computed at "
                f"{rates_txt}. Future runs will use the new value — if the old rate "
                f"was wrong, reopen those years after saving."
            )
    elif kind == "lookup" and assets_referencing:
        classification = "future_only"
        message = _FUTURE_ONLY_MESSAGE

    return ImpactPreviewResponse(
        kind=kind,
        id=row_id,
        assets_referencing=assets_referencing,
        draft_run_fy_labels=sorted(draft_fys),
        finalized_run_fy_labels=sorted(final_fys),
        classification=classification,
        message=message,
    )


async def _count_referencing_assets(db: AsyncSession, company_id, kind, row_id) -> int:
    if kind == "category":
        cond = Asset.category_id == row_id
        base = Asset
    elif kind == "it_block":
        cond = Asset.it_block_id == row_id
        base = Asset
    elif kind == "supplier":
        return (await db.execute(
            select(func.count()).select_from(AssetAcquisition).where(
                AssetAcquisition.company_id == company_id,
                AssetAcquisition.supplier_id == row_id,
            )
        )).scalar_one()
    else:  # lookup: any dimension FK
        return (await db.execute(
            select(func.count()).select_from(Asset).where(
                Asset.company_id == company_id,
                or_(Asset.branch_id == row_id, Asset.location_id == row_id,
                    Asset.department_id == row_id, Asset.cost_centre_id == row_id),
            )
        )).scalar_one()

    return (await db.execute(
        select(func.count()).select_from(base).where(
            Asset.company_id == company_id, cond,
            Asset.lifecycle_status != AssetLifecycleStatus.draft,
        )
    )).scalar_one()


async def _run_fys(db: AsyncSession, company_id, kind, row_id):
    """(draft labels, finalized labels) of runs whose lines reference this row.

    Category lines are per-asset, so they join through Asset; block lines carry
    it_block_id directly.
    """
    if kind not in ("category", "it_block"):
        return [], []

    if kind == "category":
        run_ids = (await db.execute(
            select(AssetDepreciationLine.run_id)
            .join(Asset, Asset.id == AssetDepreciationLine.asset_id)
            .where(Asset.company_id == company_id, Asset.category_id == row_id)
            .distinct()
        )).scalars().all()
    else:
        run_ids = (await db.execute(
            select(ItBlockDepreciationLine.run_id)
            .join(DepreciationRun, DepreciationRun.id == ItBlockDepreciationLine.run_id)
            .where(DepreciationRun.company_id == company_id,
                   ItBlockDepreciationLine.it_block_id == row_id)
            .distinct()
        )).scalars().all()

    if not run_ids:
        return [], []

    from app.models.financial_year import FinancialYear

    rows = (await db.execute(
        select(DepreciationRun.status, FinancialYear.label)
        .join(FinancialYear, FinancialYear.id == DepreciationRun.financial_year_id)
        .where(DepreciationRun.id.in_(run_ids))
    )).all()

    drafts = [label for status, label in rows if status == DepreciationRunStatus.draft.value]
    finals = [label for status, label in rows if status == DepreciationRunStatus.finalized.value]
    return drafts, finals
```

- [ ] **Step 4: Route**

Place at the END of `app/routers/asset_masters.py` (after suppliers/lookups sections):

```python
_IMPACT_KINDS = ("category", "it_block", "supplier", "lookup")


@router.get("/{kind}/{row_id}/impact-preview", response_model=ImpactPreviewResponse)
async def impact_preview(kind: str, row_id: uuid.UUID, current_user: CurrentAdmin, db: Db):
    """Facts shown inside masters edit dialogs BEFORE saving (see spec §7)."""
    if kind not in _IMPACT_KINDS:
        raise HTTPException(status_code=404, detail="Unknown master kind")
    from app.services.master_impact import compute_master_impact
    return await compute_master_impact(db, current_user.company_id, kind, row_id)  # type: ignore[arg-type]
```

Add `ImpactPreviewResponse` to the schema imports.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_master_impact.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/master_impact.py app/schemas/asset_masters.py app/routers/asset_masters.py tests/test_master_impact.py
git commit -m "feat(assets): live impact preview for master edits"
```

---

### Task 5: Reopen a finalized depreciation run

**Files:**
- Modify: `app/services/depreciation_query.py`
- Modify: `app/schemas/depreciation.py`
- Modify: `app/routers/depreciation.py`
- Test: `tests/test_depreciation_api.py` (append)

**Interfaces:**
- Consumes: `finalize_depreciation_run` precedent; `log_activity` — read its exact import/signature from `app/routers/assets.py` before writing.
- Produces: `POST /api/v1/depreciation/runs/{run_id}/reopen` (admin), body `{"reason": str}`; flips finalized→draft keeping lines; 409 when a later FY is finalized; audit entry. Frontend Task 11 consumes.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_depreciation_api.py`:

```python
@pytest.mark.asyncio
async def test_reopen_flips_finalized_run_back_to_draft(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, "ro_happy@testco.com")
    headers, fy_id = ctx["headers"], ctx["fy_id"]

    run_id = (
        await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy_id}, headers=headers)
    ).json()["id"]
    assert (
        await client.post(f"/api/v1/depreciation/runs/{run_id}/finalize", headers=headers)
    ).status_code == 200

    resp = await client.post(
        f"/api/v1/depreciation/runs/{run_id}/reopen",
        json={"reason": "Opening WDV was keyed wrong"}, headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert "Opening WDV" in body["notes"]
    assert body["finalized_at"] is None

    # Lines survive the flip for reference.
    lines = await client.get(f"/api/v1/depreciation/runs/{run_id}/lines", headers=headers)
    assert lines.status_code == 200 and len(lines.json()) == 1

    # Regenerate supersedes the draft, re-finalize works again.
    rerun = (await client.post("/api/v1/depreciation/runs",
                               json={"financial_year_id": fy_id}, headers=headers)).json()
    assert (
        await client.post(f"/api/v1/depreciation/runs/{rerun['id']}/finalize", headers=headers)
    ).status_code == 200


@pytest.mark.asyncio
async def test_reopen_blocked_when_later_year_finalized(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, "ro_chain@testco.com")
    headers = ctx["headers"]

    fy_old = (await client.post("/api/v1/financial-years", json={
        "label": "2023-24", "start_date": "2023-04-01", "end_date": "2024-03-31"},
        headers=headers)).json()["id"]
    fy_new = (await client.post("/api/v1/financial-years", json={
        "label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers)).json()["id"]

    r_old = (await client.post("/api/v1/depreciation/runs",
                               json={"financial_year_id": fy_old}, headers=headers)).json()["id"]
    r_new = (await client.post("/api/v1/depreciation/runs",
                               json={"financial_year_id": fy_new}, headers=headers)).json()["id"]
    for rid in (r_old, r_new):
        assert (
            await client.post(f"/api/v1/depreciation/runs/{rid}/finalize", headers=headers)
        ).status_code == 200

    resp = await client.post(
        f"/api/v1/depreciation/runs/{r_old}/reopen",
        json={"reason": "fix older year"}, headers=headers,
    )
    assert resp.status_code == 409
    assert "2024-25" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reopen_requires_reason_and_admin(client: AsyncClient):
    from tests.asset_helpers import make_user, user_headers

    ctx = await setup_depreciation_environment(client, "ro_auth@testco.com")
    AH, fy_id = ctx["headers"], ctx["fy_id"]
    rid = (await client.post("/api/v1/depreciation/runs",
                             json={"financial_year_id": fy_id}, headers=AH)).json()["id"]
    await client.post(f"/api/v1/depreciation/runs/{rid}/finalize", headers=AH)

    await make_user(client, AH, "ro_staff@testco.com")
    UH = await user_headers(client, "ro_staff@testco.com")
    assert (
        await client.post(f"/api/v1/depreciation/runs/{rid}/reopen", json={"reason": "x"}, headers=UH)
    ).status_code == 403
    # Draft runs cannot be reopened either.
    draft_rid = (await client.post("/api/v1/depreciation/runs",
                                   json={"financial_year_id": fy_id}, headers=AH)).json()
    # (the run above superseded the finalized one into a new draft)
    assert (
        await client.post(f"/api/v1/depreciation/runs/{rid}/reopen", json={"reason": ""}, headers=AH)
    ).status_code in (422, 409)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_depreciation_api.py -k reopen -v`
Expected: FAIL — 404/405 route absent.

- [ ] **Step 3: Service function**

In `app/services/depreciation_query.py`, after `finalize_depreciation_run`:

```python
async def _blocking_later_label(
    db: AsyncSession, company_id: uuid.UUID, run: DepreciationRun
) -> str | None:
    row = (
        await db.execute(
            select(FinancialYear.label)
            .join(DepreciationRun, DepreciationRun.financial_year_id == FinancialYear.id)
            .where(
                DepreciationRun.company_id == company_id,
                DepreciationRun.status == DepreciationRunStatus.finalized.value,
                DepreciationRun.id != run.id,
                FinancialYear.start_date > run.financial_year.start_date,
            )
            .order_by(FinancialYear.start_date)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def reopen_depreciation_run(
    db: AsyncSession,
    company_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
) -> DepreciationRun:
    """Flip a finalized run back to draft so wrong inputs can be corrected.

    Openings chain chronologically: a later finalized year consumed this run's
    closings, so reopening while one exists would silently desynchronize the
    chain — refuse and tell the operator to redo oldest-first. Lines are kept so
    the previous numbers stay inspectable while a corrected run is prepared.
    """
    run = await db.get(DepreciationRun, run_id)
    if not run or run.company_id != company_id:
        raise ValueError("Depreciation run not found")
    if run.status != DepreciationRunStatus.finalized.value:
        raise DepreciationConflictError("Only a finalized run can be reopened")

    fy = run.financial_year
    blocking = await _blocking_later_label(db, company_id, run)
    if blocking is not None:
        raise DepreciationConflictError(
            f"Financial year {blocking} is already finalized. Redo years "
            f"oldest-first before reopening {fy.label}."
        )

    run.status = DepreciationRunStatus.draft.value
    run.notes = f"Reopened: {reason}"
    run.finalized_at = None
    run.finalized_by = None
    await db.commit()
    await db.refresh(run)
    return run
```

- [ ] **Step 4: Schema + route**

`app/schemas/depreciation.py`:

```python
class DepreciationRunReopenRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
```

In `app/routers/depreciation.py` (imports: add `require_admin` from `app.auth`; `DepreciationRunReopenRequest` to schema imports; `reopen_depreciation_run` to service imports; copy the exact `log_activity` import used by `app/routers/assets.py`):

```python
@router.post("/runs/{run_id}/reopen", response_model=DepreciationRunResponse)
async def reopen_run(
    run_id: uuid.UUID,
    body: DepreciationRunReopenRequest,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        run = await reopen_depreciation_run(
            db, current_user.company_id, run_id, current_user.id, body.reason.strip()
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DepreciationConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    await log_activity(db, current_user.company_id, current_user.id,
                       "depreciation.run.reopened", "depreciation_run", run.id,
                       {"reason": body.reason.strip()})
    return _populate_run_summary(run)
```

Read `log_activity`'s definition first: if it does not commit internally and the service already committed, follow with `await db.commit()` after logging.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_depreciation_api.py -v`
Expected: PASS — pre-existing finalize/delete tests unaffected.

- [ ] **Step 6: Commit**

```bash
git add app/services/depreciation_query.py app/schemas/depreciation.py app/routers/depreciation.py tests/test_depreciation_api.py
git commit -m "feat(depreciation): admin reopen of finalized runs with chronological guard"
```

---

### Task 6: POST /assets/existing — standalone opening-entry asset

**Files:**
- Create: `app/services/asset_existing.py`
- Modify: `app/schemas/assets.py`
- Modify: `app/routers/assets.py`
- Create: `tests/test_existing_assets.py`

**Interfaces:**
- Consumes: `allocate_asset_codes(db, company_id, prefix, count, branch_code=None)` (`app/services/asset_tags.py`), `apply_category_defaults(db, asset, category_id)` (`app/services/asset_register.py`).
- Produces (in `app.services.asset_existing`): `ExistingAssetError`, `current_fy_start(db, company_id) -> date | None`, `resolve_category_path(db, company_id, path) -> AssetCategory`, `validate_existing_entry(...)`, `build_existing_asset(db, company_id, created_by, **fields) -> Asset`. Task 7 imports these. Endpoint: `POST /api/v1/assets/existing` → `AssetResponse` 201.

- [ ] **Step 1: Write the failing test**

```python
"""Existing-asset (opening entry) creation."""
import pytest
from httpx import AsyncClient

from tests.asset_helpers import admin_headers, make_user, user_headers

ASSETS = "/api/v1/assets"


def _payload(**over):
    base = {
        "asset_name": "Tata Ace (2022)",
        "category_path": ["Motor vehicles",
                          "Motor cars (other than those used in a hire business)"],
        "original_cost": "850000.00",
        "purchase_date": "2022-06-10",
        "put_to_use_date": "2022-06-20",
        "capitalization_date": "2022-06-30",
        "opening_accumulated_depreciation": "200000.00",
        "opening_wdv": "650000.00",
        "opening_it_wdv": "610000.00",
    }
    base.update(over)
    return base


IN_FY_PAYLOAD = dict(  # dated inside an open FY ⇒ openings optional
    asset_name="Staff entry laptop",
    category_path=["Computers and data processing units",
                   "End user devices (desktops, laptops, printers)"],
    original_cost="40000.00",
    purchase_date="2099-01-05",
    put_to_use_date="2099-01-06",
    capitalization_date="2099-01-07",
)


@pytest.mark.asyncio
async def test_creates_standalone_precutover_draft_with_defaults(client: AsyncClient):
    AH = await admin_headers(client, "ex_happy@a.com")

    resp = await client.post(f"{ASSETS}/existing", json=_payload(), headers=AH)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["acquisition_id"] is None
    assert body["is_pre_cutover"] is True
    assert body["lifecycle_status"] == "draft"
    assert body["asset_code"]
    assert body["opening_it_wdv"] == "610000.00"
    # Motor-car category defaults applied: 96 months SLM.
    assert body["useful_life_months"] == 96
    assert body["dep_method"] == "slm"


@pytest.mark.asyncio
async def test_prefy_asset_without_openings_rejected(client: AsyncClient):
    AH = await admin_headers(client, "ex_val@a.com")
    await client.post("/api/v1/financial-years", json={
        "label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=AH)

    stripped = _payload(opening_it_wdv=None, opening_wdv=None,
                        opening_accumulated_depreciation=None)
    resp = await client.post(f"{ASSETS}/existing", json=stripped, headers=AH)
    assert resp.status_code == 422
    assert "required" in str(resp.json()["detail"]).lower()


@pytest.mark.asyncio
async def test_openings_above_cost_rejected(client: AsyncClient):
    AH = await admin_headers(client, "ex_cost@a.com")
    resp = await client.post(
        f"{ASSETS}/existing", json=_payload(opening_wdv="999999.00"), headers=AH)
    assert resp.status_code == 422
    assert "exceed" in str(resp.json()["detail"]).lower()


@pytest.mark.asyncio
async def test_unknown_category_rejected_and_member_can_create(client: AsyncClient):
    AH = await admin_headers(client, "ex_auth@a.com")
    bad = await client.post(
        f"{ASSETS}/existing",
        json=_payload(category_path=["Nope", "Still nope"]), headers=AH)
    assert bad.status_code == 422

    await make_user(client, AH, "ex_staff@a.com")
    UH = await user_headers(client, "ex_staff@a.com")
    ok = await client.post(f"{ASSETS}/existing", json=IN_FY_PAYLOAD, headers=UH)
    assert ok.status_code == 201, ok.text
```

Note: dates in `2099` keep the second scenario inside any future-dated open FY or, absent one, skip the pre-FY requirement entirely (no FY ⇒ nothing predates it).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_existing_assets.py -v`
Expected: FAIL — 404 route absent.

- [ ] **Step 3: Implement the shared service**

Create `app/services/asset_existing.py`:

```python
"""Creation logic shared by the single existing-asset form and the bulk import.

An 'existing' asset is one the company owned before this register (or before
the current year) — it carries opening balances instead of an acquisition
invoice. Validation here mirrors what depreciation_query will demand at run
time (and tightens it: books figures are required too) so mistakes surface at
entry rather than months later.
"""
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import Asset, AssetLifecycleStatus
from app.models.asset_masters import AssetCategory, AssetLookup
from app.models.financial_year import FinancialYear
from app.services.asset_register import apply_category_defaults
from app.services.asset_tags import allocate_asset_codes


class ExistingAssetError(ValueError):
    """Row-level rejection with a human message (HTTP 422 / import row error)."""


async def current_fy_start(db: AsyncSession, company_id: uuid.UUID) -> Optional[date]:
    today = date.today()
    return (
        await db.execute(
            select(FinancialYear.start_date)
            .where(
                FinancialYear.company_id == company_id,
                FinancialYear.start_date <= today,
                FinancialYear.end_date >= today,
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def resolve_category_path(
    db: AsyncSession, company_id: uuid.UUID, path: list
) -> AssetCategory:
    """Resolve ['Parent', 'Child'] (child optional) case-insensitively against
    the company's own forked tree."""
    if not path or not str(path[0] or "").strip():
        raise ExistingAssetError("Category is required")
    parent_name = str(path[0]).strip().lower()
    parents = (
        await db.execute(
            select(AssetCategory).where(
                AssetCategory.company_id == company_id,
                AssetCategory.parent_id.is_(None),
                func.lower(AssetCategory.name) == parent_name,
            )
        )
    ).scalars().all()
    if len(parents) != 1:
        raise ExistingAssetError(f"Unknown category '{path[0]}'")

    child_raw = str(path[1]) if len(path) > 1 else ""
    if not child_raw.strip():
        return parents[0]

    children = (
        await db.execute(
            select(AssetCategory).where(
                AssetCategory.company_id == company_id,
                AssetCategory.parent_id == parents[0].id,
                func.lower(AssetCategory.name) == child_raw.strip().lower(),
            )
        )
    ).scalars().all()
    if len(children) != 1:
        raise ExistingAssetError(f"Unknown subcategory '{child_raw}' under '{path[0]}'")
    return children[0]


def _dec(value, field: str) -> Decimal:
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ExistingAssetError(f"{field} is not a valid amount")
    if d < 0:
        raise ExistingAssetError(f"{field} cannot be negative")
    return d


def validate_opening_values(
    *,
    original_cost: Decimal,
    opening_accumulated_depreciation: Optional[Decimal],
    opening_wdv: Optional[Decimal],
    opening_it_wdv: Optional[Decimal],
    put_to_use_date: Optional[date],
    capitalization_date: Optional[date],
    fy_start: Optional[date],
) -> None:
    cost = _dec(original_cost, "Original cost")
    for name, val in (
        ("Opening accumulated depreciation", opening_accumulated_depreciation),
        ("Opening WDV (books)", opening_wdv),
        ("Opening WDV (tax)", opening_it_wdv),
    ):
        if val is not None and _dec(val, name) > cost:
            raise ExistingAssetError(f"{name} cannot exceed original cost")

    effective = put_to_use_date or capitalization_date
    predates_fy = fy_start is not None and effective is not None and effective < fy_start
    undatable = fy_start is not None and effective is None
    if predates_fy or undatable:
        missing = [
            name for name, val in (
                ("Opening WDV (tax)", opening_it_wdv),
                ("Opening WDV (books)", opening_wdv),
                ("Opening accumulated depreciation", opening_accumulated_depreciation),
            ) if val is None
        ]
        if missing:
            raise ExistingAssetError(
                "Asset predates the current financial year: "
                + ", ".join(missing) + " required"
            )


async def build_existing_asset(
    db: AsyncSession,
    company_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    asset_name: str,
    category: AssetCategory,
    original_cost: Decimal,
    purchase_date: Optional[date] = None,
    put_to_use_date: Optional[date] = None,
    capitalization_date: Optional[date] = None,
    opening_accumulated_depreciation: Optional[Decimal] = None,
    opening_wdv: Optional[Decimal] = None,
    opening_it_wdv: Optional[Decimal] = None,
    useful_life_months: Optional[int] = None,
    residual_pct: Optional[Decimal] = None,
    branch_id: Optional[uuid.UUID] = None,
    location_id: Optional[uuid.UUID] = None,
    department_id: Optional[uuid.UUID] = None,
    cost_centre_id: Optional[uuid.UUID] = None,
    custodian_name: Optional[str] = None,
    serial_number: Optional[str] = None,
    remarks: Optional[str] = None,
) -> Asset:
    fy_start = await current_fy_start(db, company_id)
    validate_opening_values(
        original_cost=original_cost,
        opening_accumulated_depreciation=opening_accumulated_depreciation,
        opening_wdv=opening_wdv,
        opening_it_wdv=opening_it_wdv,
        put_to_use_date=put_to_use_date,
        capitalization_date=capitalization_date,
        fy_start=fy_start,
    )

    branch_code = None
    if branch_id is not None:
        branch_code = (
            await db.execute(select(AssetLookup.code).where(AssetLookup.id == branch_id))
        ).scalar_one_or_none()

    codes = await allocate_asset_codes(
        db, company_id, category.tag_prefix, 1, branch_code=branch_code
    )
    unit = Asset(
        company_id=company_id,
        unit_index=1,
        asset_code=codes[0],
        asset_name=asset_name.strip(),
        category_id=category.id,
        lifecycle_status=AssetLifecycleStatus.draft,
        is_pre_cutover=True,
        original_cost=original_cost,
        manufacturer_serial_number=serial_number,
        purchase_date=purchase_date,
        it_put_to_use_date=put_to_use_date,
        capitalization_date=capitalization_date,
        available_for_use_date=None,
        opening_accumulated_depreciation=opening_accumulated_depreciation,
        opening_wdv=opening_wdv,
        opening_it_wdv=opening_it_wdv,
        branch_id=branch_id,
        location_id=location_id,
        department_id=department_id,
        cost_centre_id=cost_centre_id,
        custodian_name=custodian_name,
        remarks=remarks,
        created_by=created_by,
        custom_fields={},
    )
    await apply_category_defaults(db, unit, category.id)
    # Explicit inputs win over defaults; deviating from the Schedule II life
    # needs the statutory disclosure reason.
    if useful_life_months is not None:
        if unit.useful_life_months and useful_life_months != unit.useful_life_months \
                and not unit.useful_life_override_reason:
            raise ExistingAssetError(
                "Useful life differs from the category default — supply "
                "useful_life_override_reason"
            )
        unit.useful_life_months = useful_life_months
    if residual_pct is not None:
        unit.residual_pct = residual_pct
    db.add(unit)
    await db.flush()
    return unit
```

- [ ] **Step 4: Schema + thin route**

`app/schemas/assets.py` near `AssetQuickAddRequest` (match its typing imports):

```python
class AssetExistingCreate(BaseModel):
    asset_name: str = Field(min_length=1, max_length=255)
    category_path: List[str] = Field(min_length=1, max_length=2)
    original_cost: Decimal = Field(ge=0)
    purchase_date: Optional[date] = None
    put_to_use_date: Optional[date] = None
    capitalization_date: Optional[date] = None
    opening_accumulated_depreciation: Optional[Decimal] = Field(default=None, ge=0)
    opening_wdv: Optional[Decimal] = Field(default=None, ge=0)
    opening_it_wdv: Optional[Decimal] = Field(default=None, ge=0)
    useful_life_months: Optional[int] = Field(default=None, ge=1, le=1200)
    useful_life_override_reason: Optional[str] = Field(default=None, max_length=2000)
    residual_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)
    branch_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    department_id: Optional[uuid.UUID] = None
    cost_centre_id: Optional[uuid.UUID] = None
    custodian_name: Optional[str] = Field(default=None, max_length=255)
    serial_number: Optional[str] = Field(default=None, max_length=255)
    remarks: Optional[str] = None
```

Route in `app/routers/assets.py`, in the literal-paths block beside `/quick-add`:

```python
@router.post("/existing", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_existing_asset(body: AssetExistingCreate, current_user: Reader, db: Db):
    """Opening entry for an asset owned before the register (or this FY).

    Creates a standalone draft — no acquisition — carrying cutover balances;
    approval then puts it on the books like any other asset.
    """
    from app.services.asset_existing import (
        ExistingAssetError,
        build_existing_asset,
        resolve_category_path,
    )

    try:
        category = await resolve_category_path(db, current_user.company_id, body.category_path)
        unit = await build_existing_asset(
            db,
            current_user.company_id,
            current_user.id,
            asset_name=body.asset_name,
            category=category,
            original_cost=body.original_cost,
            purchase_date=body.purchase_date,
            put_to_use_date=body.put_to_use_date,
            capitalization_date=body.capitalization_date,
            opening_accumulated_depreciation=body.opening_accumulated_depreciation,
            opening_wdv=body.opening_wdv,
            opening_it_wdv=body.opening_it_wdv,
            useful_life_months=body.useful_life_months,
            residual_pct=body.residual_pct,
            branch_id=body.branch_id,
            location_id=body.location_id,
            department_id=body.department_id,
            cost_centre_id=body.cost_centre_id,
            custodian_name=body.custodian_name,
            serial_number=body.serial_number,
            remarks=body.remarks,
        )
    except ExistingAssetError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    await log_activity(db, current_user.company_id, current_user.id, "asset.created",
                       "asset", unit.id, {"asset_code": unit.asset_code, "source": "existing"})
    await db.commit()

    result = await db.execute(select(Asset).where(Asset.id == unit.id))
    return result.scalars().unique().one()
```

Add `AssetExistingCreate` to the schema import list; verify how `update_asset` re-selects for serialization and match that pattern exactly if different.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_existing_assets.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/asset_existing.py app/schemas/assets.py app/routers/assets.py tests/test_existing_assets.py
git commit -m "feat(assets): POST /assets/existing for standalone opening-entry drafts"
```

---

### Task 7: Bulk import — template download + atomic multi-row import

**Files:**
- Create: `app/services/asset_import.py`
- Modify: `app/routers/assets.py`
- Modify: `app/schemas/assets.py` (result schema)
- Create: `tests/test_asset_import.py`

**Interfaces:**
- Consumes: `load_sheet(filename, content, sheet_name=None)` from `app.services.import_service`; Task 6's `resolve_category_path`, `build_existing_asset`, `ExistingAssetError`.
- Produces:
  - `GET /api/v1/assets/import/template` → xlsx bytes (Instructions + Assets sheets).
  - `POST /api/v1/assets/import` (multipart `file`) → 201 `{"created_count": int, "first_asset_id": str|None}` or 422 `[{"row": int, "message": str}, ...]`.
  - In `app.services.asset_import`: `IMPORT_HEADERS: list[str]`, `build_template_xlsx() -> bytes`, `parse_rows(rows) -> list[dict]`, `import_assets(db, company_id, user_id, rows) -> list[Asset]`, `ImportRejected(errors)`.

- [ ] **Step 1: Write the failing test**

```python
"""Bulk import of pre-existing assets from Excel/CSV."""
import io

import openpyxl
import pytest
from httpx import AsyncClient

from tests.asset_helpers import admin_headers

ASSETS = "/api/v1/assets"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

HEADER = ["Asset name", "Category", "Subcategory", "Original cost",
          "Purchase date", "Put-to-use date", "Capitalization date",
          "Opening accumulated depreciation", "Opening WDV (books)", "Opening WDV (tax)",
          "Useful life months", "Dep method", "Residual %", "IT block code",
          "Branch", "Location", "Department", "Cost centre", "Custodian name",
          "Serial number", "Remarks"]


def xlsx_of(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


GOOD_ROW = ["Tata Ace", "Motor vehicles", "Motor cars (other than those used in a hire business)",
            850000, "2022-06-10", "2022-06-20", "2022-06-30",
            200000, 650000, 610000, None, None, None, None,
            None, None, None, None, "R Kumar", "DL1AB1234", "Bought pre-register"]


def upload(content, filename="assets.xlsx"):
    return {"file": (filename, content, XLSX_MIME)}


@pytest.mark.asyncio
async def test_template_downloads_with_expected_columns(client: AsyncClient):
    AH = await admin_headers(client, "imp_tpl@a.com")
    resp = await client.get(f"{ASSETS}/import/template", headers=AH)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(XLSX_MIME)
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Instructions", "Assets"]
    assert [c.value for c in wb["Assets"][1]] == HEADER


@pytest.mark.asyncio
async def test_import_creates_drafts_and_is_atomic(client: AsyncClient):
    AH = await admin_headers(client, "imp_ok@a.com")

    resp = await client.post(f"{ASSETS}/import", files=upload(xlsx_of([GOOD_ROW, GOOD_ROW])),
                             headers=AH)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created_count"] == 2 and body["first_asset_id"]

    listing = (await client.get(f"{ASSETS}", headers=AH)).json()
    assert len(listing) == 2
    assert all(a["is_pre_cutover"] and a["lifecycle_status"] == "draft" for a in listing)

    # One bad row aborts everything.
    bad = list(GOOD_ROW)
    bad[0] = ""
    resp2 = await client.post(f"{ASSETS}/import", files=upload(xlsx_of([GOOD_ROW, bad])), headers=AH)
    assert resp2.status_code == 422
    errs = resp2.json()["detail"]
    assert isinstance(errs, list) and errs[0]["row"] == 3
    assert len((await client.get(f"{ASSETS}", headers=AH)).json()) == 2  # unchanged


@pytest.mark.asyncio
async def test_csv_with_case_insensitive_categories(client: AsyncClient):
    AH = await admin_headers(client, "imp_csv@a.com")
    csv_content = (
        "Asset name,Category,Subcategory,Original cost,,,,,,,,,,,,,,,,,,,\n"
        "old chair,furniture and fittings,general furniture and fittings,3000,,,,,,,,,,,,,,,,,,,\n"
    ).encode("utf-8")
    resp = await client.post(
        f"{ASSETS}/import", files=upload(csv_content, "assets.csv"), headers=AH)
    assert resp.status_code == 201, resp.text
    listing = (await client.get(f"{ASSETS}", headers=AH)).json()
    assert listing[0]["useful_life_months"] == 120  # category default applied
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_asset_import.py -v`
Expected: FAIL — 404s.

- [ ] **Step 3: Implement the import service**

Create `app/services/asset_import.py`:

```python
"""Excel/CSV bulk import of pre-existing assets.

All-or-nothing: every row is validated before anything is written; one bad row
aborts the file with a per-row error report. Half-imported registers are
miserable to unwind; re-uploading a corrected sheet costs nothing.
"""
import io
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_masters import AssetLookup, ItAssetBlock
from app.models.assets import Asset
from app.services.asset_existing import (
    ExistingAssetError,
    build_existing_asset,
    resolve_category_path,
)

IMPORT_HEADERS = [
    "Asset name", "Category", "Subcategory", "Original cost",
    "Purchase date", "Put-to-use date", "Capitalization date",
    "Opening accumulated depreciation", "Opening WDV (books)", "Opening WDV (tax)",
    "Useful life months", "Dep method", "Residual %", "IT block code",
    "Branch", "Location", "Department", "Cost centre", "Custodian name",
    "Serial number", "Remarks",
]

_INSTRUCTIONS = [
    "Fixed Asset Register — bulk import of pre-existing assets.",
    "Fill the Assets sheet. One row per asset. Do not rename columns.",
    "Dates: YYYY-MM-DD. Amounts: plain numbers, no currency symbols.",
    "Category/Subcategory must match your company's category names (case-insensitive).",
    "Assets dated before the current financial year MUST carry all three opening figures.",
    "Branch/Location/Department/Cost centre must match your master names.",
    "Any row with an error aborts the whole file — fix it and re-upload.",
]


class ImportRejected(Exception):
    def __init__(self, errors: List[dict]):
        self.errors = errors
        super().__init__("Import rejected")


class RowError(Exception):
    def __init__(self, row: int, message: str):
        self.row, self.message = row, message
        super().__init__(message)


def build_template_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    info = wb.active
    info.title = "Instructions"
    info.column_dimensions["A"].width = 95
    for i, line in enumerate(_INSTRUCTIONS, start=1):
        cell = info.cell(row=i, column=1, value=line)
        if i == 1:
            cell.font = Font(bold=True)
    sheet = wb.create_sheet("Assets")
    for col, name in enumerate(IMPORT_HEADERS, start=1):
        sheet.cell(row=1, column=col, value=name).font = Font(bold=True)
        sheet.column_dimensions[get_column_letter(col)].width = 26
    sheet.append([
        "Tata Ace", "Motor vehicles", "Motor cars (other than those used in a hire business)",
        850000, "2022-06-10", "2022-06-20", "2022-06-30", 200000, 650000, 610000,
        None, None, None, None, None, None, None, None, "R Kumar", "DL1AB1234", "Example row — delete before use",
    ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _to_date(value) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ExistingAssetError(f"'{value}' is not a YYYY-MM-DD date")


def _to_dec(value) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        raise ExistingAssetError(f"'{value}' is not a valid amount")


def _to_int(value) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        raise ExistingAssetError(f"'{value}' is not a whole number")


def _cell(row: list, idx: int):
    return row[idx] if idx < len(row) else None


def parse_rows(rows: List[list]) -> List[dict]:
    """Header excluded by caller. Structural per-row parsing only; referential
    resolution against the DB happens in import_assets."""
    payloads: List[dict] = []
    for n, row in enumerate(rows, start=2):  # Excel numbering: header is row 1
        if not any(v not in (None, "") for v in row):
            continue  # tolerate blank spacer rows
        p: dict = {"row": n}

        def get(name: str, _row=row):
            return _cell(_row, IMPORT_HEADERS.index(name))

        try:
            name = get("Asset name")
            if not name or not str(name).strip():
                raise ExistingAssetError("Asset name is required")
            p["asset_name"] = str(name).strip()

            parent = get("Category")
            child = get("Subcategory")
            if not parent or not str(parent).strip():
                raise ExistingAssetError("Category is required")
            p["path"] = ([str(parent)] + ([str(child)] if child not in (None, "") else []))

            p["original_cost"] = _to_dec(get("Original cost"))
            if p["original_cost"] is None:
                raise ExistingAssetError("Original cost is required")

            p["purchase_date"] = _to_date(get("Purchase date"))
            p["put_to_use_date"] = _to_date(get("Put-to-use date"))
            p["capitalization_date"] = _to_date(get("Capitalization date"))
            p["opening_accumulated_depreciation"] = _to_dec(get("Opening accumulated depreciation"))
            p["opening_wdv"] = _to_dec(get("Opening WDV (books)"))
            p["opening_it_wdv"] = _to_dec(get("Opening WDV (tax)"))
            p["useful_life_months"] = _to_int(get("Useful life months"))
            p["residual_pct"] = _to_dec(get("Residual %"))
            for key in ("IT block code", "Branch", "Location", "Department",
                        "Cost centre", "Custodian name", "Serial number", "Remarks"):
                v = get(key)
                p[key.lower().replace(" ", "_")] = str(v).strip() if v not in (None, "") else None
        except ExistingAssetError as e:
            raise RowError(n, str(e))
        payloads.append(p)
    return payloads


async def _lookup_map(db: AsyncSession, company_id: uuid.UUID) -> dict:
    rows_ = (await db.execute(
        select(AssetLookup).where(AssetLookup.company_id == company_id)
    )).scalars().all()
    return {(str(l.kind.value), l.name.strip().lower()): l.id for l in rows_}


async def _it_block_map(db: AsyncSession, company_id: uuid.UUID) -> dict:
    rows_ = (await db.execute(
        select(ItAssetBlock).where(ItAssetBlock.company_id == company_id)
    )).scalars().all()
    return {b.code.strip().lower(): b.id for b in rows_}


async def import_assets(
    db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, rows: List[list]
) -> List[Asset]:
    payloads = parse_rows(rows)
    if not payloads:
        raise RowError(0, "No data rows found")

    lookups = await _lookup_map(db, company_id)
    blocks = await _it_block_map(db, company_id)

    errors: List[RowError] = []
    created: List[Asset] = []

    for p in payloads:
        try:
            branch_id = location_id = department_id = cost_centre_id = None
            for col, kind_key, slot in (("branch", "branch", None), ("location", "location", None),
                                        ("department", "department", None), ("cost_centre", "cost_centre", None)):
                raw = p.get(col)
                if raw:
                    lid = lookups.get((kind_key, raw.lower()))
                    if lid is None:
                        raise ExistingAssetError(f"Unknown {col.replace('_', ' ')} '{raw}'")
                    if col == "branch":
                        branch_id = lid
                    elif col == "location":
                        location_id = lid
                    elif col == "department":
                        department_id = lid
                    else:
                        cost_centre_id = lid

            block_code = p.get("it_block_code")
            it_block_id = None
            if block_code:
                it_block_id = blocks.get(block_code.lower())
                if it_block_id is None:
                    raise ExistingAssetError(f"Unknown IT block code '{block_code}'")

            category = await resolve_category_path(db, company_id, p["path"])
            unit = await build_existing_asset(
                db, company_id, user_id,
                asset_name=p["asset_name"],
                category=category,
                original_cost=p["original_cost"],
                purchase_date=p["purchase_date"],
                put_to_use_date=p["put_to_use_date"],
                capitalization_date=p["capitalization_date"],
                opening_accumulated_depreciation=p["opening_accumulated_depreciation"],
                opening_wdv=p["opening_wdv"],
                opening_it_wdv=p["opening_it_wdv"],
                useful_life_months=p["useful_life_months"],
                residual_pct=p["residual_pct"],
                branch_id=branch_id,
                location_id=location_id,
                department_id=department_id,
                cost_centre_id=cost_centre_id,
                custodian_name=p.get("custodian_name"),
                serial_number=p.get("serial_number"),
                remarks=p.get("remarks"),
            )
            created.append(unit)
        except ExistingAssetError as e:
            errors.append(RowError(p["row"], str(e)))

    if errors:
        await db.rollback()
        raise ImportRejected([{"row": e.row, "message": e.message} for e in errors])
    return created
```

Note on `it_block_id`: `build_existing_asset` does not accept it yet. Extend its signature with `it_block_id: Optional[uuid.UUID] = None` (set `unit.it_block_id = it_block_id` after construction; leave rate to the block default at run time) — update Task 6's service accordingly. Its existing callers are unaffected by a defaulted kwarg.

- [ ] **Step 4: Routes**

`app/schemas/assets.py`:

```python
class AssetImportResult(BaseModel):
    created_count: int
    first_asset_id: Optional[uuid.UUID] = None
```

Routes in `app/routers/assets.py` literal block (imports: `UploadFile, File` from fastapi; `Response`; `load_sheet` from `app.services.import_service`; the four import-service callables; `AssetImportResult`):

```python
@router.get("/import/template")
async def download_import_template(current_user: Reader):
    content = build_template_xlsx()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="asset_import_template.xlsx"'},
    )


@router.post("/import", response_model=AssetImportResult, status_code=status.HTTP_201_CREATED)
async def import_existing_assets(
    current_user: Reader, db: Db, file: UploadFile = File(...)
):
    """Atomic bulk creation of pre-existing assets from a filled template.

    Any failing row rejects the whole file with a per-row error report.
    """
    content = await file.read()
    try:
        _, rows = load_sheet(file.filename or "", content, sheet_name=None)
        created = await import_assets(db, current_user.company_id, current_user.id, rows)
    except ImportRejected as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors)
    except RowError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=[{"row": e.row, "message": e.message}])

    for unit in created:
        await log_activity(db, current_user.company_id, current_user.id, "asset.created",
                           "asset", unit.id,
                           {"asset_code": unit.asset_code, "source": "import"})
    await db.commit()
    return AssetImportResult(created_count=len(created),
                             first_asset_id=created[0].id if created else None)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_asset_import.py -v && pytest tests/test_existing_assets.py tests/test_assets.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/asset_import.py app/services/asset_existing.py app/routers/assets.py app/schemas/assets.py tests/test_asset_import.py
git commit -m "feat(assets): atomic Excel/CSV import with downloadable template"
```

---

### Task 8: CategoryPicker state fix (frontend)

**Files:**
- Modify: `frontend/src/pages/company/assets/CategoryPicker.tsx`
- Create: `frontend/src/pages/company/assets/CategoryPicker.test.tsx`

**Interfaces:**
- Consumes: `useCategoryTree()` (unchanged).
- Produces: identical props contract — behavior fix only. Tasks 9/10 keep using it.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CategoryPicker } from './CategoryPicker'

vi.mock('@/api/hooks/assetMasters', () => ({
  useCategoryTree: () => ({
    isLoading: false,
    tree: [
      { parent: { id: 'b', name: 'Buildings' }, children: [
        { id: 'b1', name: 'RCC frame structure buildings',
          default_useful_life_months: 720, default_dep_method: 'slm',
          default_it_block_code: 'BLD-10', default_it_block_rate: 10 },
        { id: 'b2', name: 'Factory buildings' },
      ]},
      { parent: { id: 'o', name: 'Office equipment' }, children: [
        { id: 'o1', name: 'Office equipment' },
      ]},
    ],
  }),
}))

describe('CategoryPicker', () => {
  it('keeps a multi-child category selected while awaiting subcategory choice', () => {
    const onChange = vi.fn()
    render(<CategoryPicker value="" onChange={onChange} />)

    const category = screen.getByLabelText('Category') as HTMLSelectElement
    fireEvent.change(category, { target: { value: 'b' } })

    // Regression: selection used to snap back to the placeholder.
    expect(category.value).toBe('b')
    expect(onChange).toHaveBeenCalledWith('')
    expect((screen.getByLabelText('Subcategory') as HTMLSelectElement).disabled).toBe(false)
  })

  it('auto-selects the only child of a single-child category', () => {
    const onChange = vi.fn()
    render(<CategoryPicker value="" onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'o' } })
    expect(onChange).toHaveBeenCalledWith('o1')
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run (from `frontend/`): `npx vitest run src/pages/company/assets/CategoryPicker.test.tsx`
Expected: first test FAILS — category select resets to `''`.

- [ ] **Step 3: Fix the component**

Rewrite the body of `CategoryPicker` keeping its props and JSX structure:

```tsx
import { useEffect, useMemo, useState } from 'react'
import { Field, Select } from '@/components/ui'
import { useCategoryTree } from '@/api/hooks/assetMasters'
import { months } from './assetFormat'

export interface CategoryPickerProps {
  value: string
  onChange: (categoryId: string) => void
  error?: string
  required?: boolean
  disabled?: boolean
}

/**
 * Two-step category → subcategory picker.
 *
 * `parentId` is its own piece of state: picking a parent with several
 * subcategories must visibly stick while the leaf is still empty — deriving
 * the parent from the (empty) leaf value snapped the selection back to the
 * placeholder, which read as "most categories are not clickable".
 */
export function CategoryPicker({ value, onChange, error, required, disabled }: CategoryPickerProps) {
  const { tree, isLoading } = useCategoryTree()
  const [parentId, setParentId] = useState('')

  const groupOfValue = useMemo(
    () =>
      tree.find((g) => g.parent.id === value) ??
      tree.find((g) => g.children.some((c) => c.id === value)),
    [tree, value],
  )

  // Sync local selection when an external value names a different group
  // (form reset, prefill); ignore same-group changes to avoid loops.
  useEffect(() => {
    setParentId(groupOfValue ? groupOfValue.parent.id : '')
  }, [groupOfValue?.parent.id])

  const group = tree.find((g) => g.parent.id === parentId)
  // Zero-child groups select themselves; otherwise show the leaf only if it
  // belongs to this group.
  const shownLeaf =
    group && group.children.length > 0 && group.children.some((c) => c.id === value)
      ? value
      : ''

  const hintLeaf = group?.children.find((c) => c.id === shownLeaf)
  const hint = hintLeaf
    ? [
        hintLeaf.default_useful_life_months ? `Useful life ${months(hintLeaf.default_useful_life_months)}` : null,
        hintLeaf.default_dep_method ? hintLeaf.default_dep_method.toUpperCase() : null,
        hintLeaf.default_it_block_code ? `IT block ${hintLeaf.default_it_block_code}` : null,
        hintLeaf.default_it_block_rate != null ? `${hintLeaf.default_it_block_rate}%` : null,
        hintLeaf.default_itc_treatment === 'blocked' ? 'ITC blocked' : null,
      ]
        .filter(Boolean)
        .join(' · ')
    : 'Picking a subcategory fills in useful life, method, residual value and the tax block.'

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Category" required={required} error={error}>
        <Select
          value={parentId}
          error={!!error}
          disabled={disabled || isLoading}
          aria-label="Category"
          onChange={(e) => {
            const id = e.target.value
            setParentId(id)
            const g = tree.find((x) => x.parent.id === id)
            if (g && g.children.length === 1) onChange(g.children[0].id)
            else if (g && g.children.length === 0) onChange(g.parent.id)
            else onChange('')
          }}
        >
          <option value="">Select a category…</option>
          {tree.map((g) => (
            <option key={g.parent.id} value={g.parent.id}>{g.parent.name}</option>
          ))}
        </Select>
      </Field>

      <Field label="Subcategory" required={required} hint={hint}>
        <Select
          value={shownLeaf}
          disabled={disabled || !group || group.children.length === 0}
          aria-label="Subcategory"
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">
            {group && group.children.length === 0 ? 'No subcategories' : 'Select a subcategory…'}
          </option>
          {(group?.children ?? []).map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </Select>
      </Field>
    </div>
  )
}
```

- [ ] **Step 4: Run tests + existing suite**

Run: `npx vitest run src/pages/company/assets/CategoryPicker.test.tsx src/pages/company/assets/assets.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/company/assets/CategoryPicker.tsx frontend/src/pages/company/assets/CategoryPicker.test.tsx
git commit -m "fix(assets): category selection sticks while awaiting subcategory"
```

---

### Task 9: Add-asset dropdown + ExistingAssetPage

**Files:**
- Create: `frontend/src/pages/company/assets/AddAssetButton.tsx`
- Create: `frontend/src/pages/company/assets/ExistingAssetPage.tsx`
- Modify: `frontend/src/api/endpoints/assets.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/hooks/assets.ts` (+ `useCreateExistingAsset`)
- Modify: `frontend/src/routes/company.routes.tsx`
- Modify: `frontend/src/pages/company/assets/AssetsPage.tsx` (swap button)
- Create tests: `AddAssetButton.test.tsx`, `ExistingAssetPage.test.tsx`; adjust `assets.test.tsx`

**Interfaces:**
- Consumes: `POST /assets/existing` (Task 6); fixed `CategoryPicker` (Task 8); `LookupSelect` (existing — read its real prop signature before wiring).
- Produces: `assetsApi.createExisting(body: AssetExistingCreate)` + `useCreateExistingAsset()`; route `/app/assets/new/existing`.

- [ ] **Step 1: Type + endpoint + hook**

In `frontend/src/api/types.ts`:

```ts
export interface AssetExistingCreate {
  asset_name: string
  category_path: string[]
  original_cost: string
  purchase_date?: string | null
  put_to_use_date?: string | null
  capitalization_date?: string | null
  opening_accumulated_depreciation?: string | null
  opening_wdv?: string | null
  opening_it_wdv?: string | null
  useful_life_months?: number | null
  useful_life_override_reason?: string | null
  residual_pct?: string | null
  branch_id?: string | null
  location_id?: string | null
  department_id?: string | null
  cost_centre_id?: string | null
  custodian_name?: string | null
  serial_number?: string | null
  remarks?: string | null
}
```

In `frontend/src/api/endpoints/assets.ts` beside `quickAdd` (match file's client/export conventions):

```ts
  createExisting: (body: AssetExistingCreate) =>
    companyClient.post<AssetResponse>(`${BASE}/existing`, body),
```

In `frontend/src/api/hooks/assets.ts`:

```ts
export function useCreateExistingAsset() {
  return useMutation({ mutationFn: (body: AssetExistingCreate) => assetsApi.createExisting(body) })
}
```

- [ ] **Step 2: Failing tests**

`AddAssetButton.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AddAssetButton } from './AddAssetButton'

const navigate = vi.fn()
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }))
vi.mock('./QuickAddAssetModal', () => ({ QuickAddAssetModal: () => <div data-testid="quick-add" /> }))

describe('AddAssetButton', () => {
  it('offers new vs existing and routes existing to its page', () => {
    render(<AddAssetButton />)
    fireEvent.click(screen.getByRole('button', { name: /add asset/i }))
    fireEvent.click(screen.getByText('Existing asset'))
    expect(navigate).toHaveBeenCalledWith('/app/assets/new/existing')
  })

  it('opens the quick-add modal for a new asset', () => {
    render(<AddAssetButton />)
    fireEvent.click(screen.getByRole('button', { name: /add asset/i }))
    fireEvent.click(screen.getByText('New asset'))
    expect(screen.getByTestId('quick-add')).toBeInTheDocument()
  })
})
```

`ExistingAssetPage.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ExistingAssetPage } from './ExistingAssetPage'

const navigate = vi.fn()
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }))
vi.mock('@/api/hooks/assetMasters', () => ({
  useCategoryTree: () => ({
    isLoading: false,
    tree: [
      { parent: { id: 'mv', name: 'Motor vehicles' }, children: [
        { id: 'car', name: 'Motor cars (other than those used in a hire business)',
          default_useful_life_months: 96, default_dep_method: 'slm',
          default_residual_pct: 5, default_it_block_code: 'PM-15-MV',
          default_it_block_rate: 15, default_itc_treatment: 'blocked' },
      ]},
    ],
  }),
}))
vi.mock('./LookupSelect', () => ({ LookupSelect: () => <div /> }))
const mutateAsync = vi.fn().mockResolvedValue({ id: 'a-1' })
vi.mock('@/api/hooks/assets', () => ({
  useCreateExistingAsset: () => ({ mutateAsync, isPending: false }),
}))

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}
function pick(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

describe('ExistingAssetPage', () => {
  it('submits opening balances and navigates to the new asset', async () => {
    render(<ExistingAssetPage />)
    fill('Asset name', 'Tata Ace')
    pick('Category', 'mv') // single child auto-selects
    fill('Original cost', '850000')
    fill('Put-to-use date', '2022-06-20')
    fill('Capitalization date', '2022-06-30')
    fill('Opening accumulated depreciation', '200000')
    fill('Opening WDV (books)', '650000')
    fill('Opening WDV (tax)', '610000')
    fireEvent.click(screen.getByRole('button', { name: /save draft/i }))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/app/assets/a-1'))
    expect(mutateAsync).toHaveBeenCalledTimes(1)
    const body = mutateAsync.mock.calls[0][0]
    expect(body.category_path).toEqual(['Motor vehicles', 'Motor cars (other than those used in a hire business)'])
    expect(body.opening_it_wdv).toBe('610000')
  })

  it('blocks save with a message when openings are missing for a pre-FY asset', async () => {
    render(<ExistingAssetPage />)
    fill('Asset name', 'Old lathe')
    pick('Category', 'mv')
    fill('Original cost', '100')
    fill('Put-to-use date', '2020-01-01')
    fireEvent.click(screen.getByRole('button', { name: /save draft/i }))
    expect(await screen.findByText(/required/i)).toBeInTheDocument()
    expect(navigate).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 3: Run to verify failure**

Run: `npx vitest run src/pages/company/assets/AddAssetButton.test.tsx src/pages/company/assets/ExistingAssetPage.test.tsx`
Expected: FAIL — modules don't exist.

- [ ] **Step 4: Build the components**

`AddAssetButton.tsx` (no dropdown primitive exists in `components/ui` — small popover; copy tailwind tokens from sibling markup):

```tsx
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, History, PlusCircle } from 'lucide-react'
import { Button } from '@/components/ui'
import { QuickAddAssetModal } from './QuickAddAssetModal'

/** Split entry point: fresh purchases use the six-field modal; assets the
 *  company already owned go to the opening-entry page. */
export function AddAssetButton() {
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [quickAddOpen, setQuickAddOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <Button onClick={() => setMenuOpen((v) => !v)}>
        Add asset <ChevronDown className="ml-1 h-4 w-4" />
      </Button>
      {menuOpen && (
        <div className="absolute right-0 z-20 mt-1 w-56 rounded-lg border border-border bg-bg-surface py-1 shadow-lg">
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-bg-raised"
            onClick={() => { setMenuOpen(false); setQuickAddOpen(true) }}
          >
            <PlusCircle className="h-4 w-4" /> New asset
          </button>
          <button
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-bg-raised"
            onClick={() => { setMenuOpen(false); navigate('/app/assets/new/existing') }}
          >
            <History className="h-4 w-4" /> Existing asset
          </button>
        </div>
      )}
      <QuickAddAssetModal open={quickAddOpen} onClose={() => setQuickAddOpen(false)} />
    </div>
  )
}
```

`ExistingAssetPage.tsx` — five Card sections mirroring spec §5.2; full implementation:

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button, Card, Field, Input, PageHeader, Textarea, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useCreateExistingAsset } from '@/api/hooks/assets'
import { useCategoryTree } from '@/api/hooks/assetMasters'
import { CategoryPicker } from './CategoryPicker'
import { LookupSelect } from './LookupSelect'

type Errors = Record<string, string>

const OPENING_FIELDS = ['opening_accumulated_depreciation', 'opening_wdv', 'opening_it_wdv'] as const

/** Opening entry: one asset the company owned before this register (or before
 *  the current year). Mirrors the backend's pre-FY validation so mistakes die
 *  here, not in a depreciation run months later. The server re-checks exactly;
 *  the April-1 heuristic here is only first-line UX. */
export function ExistingAssetPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const create = useCreateExistingAsset()
  const { tree } = useCategoryTree()

  const [values, setValues] = useState({
    asset_name: '', categoryId: '', original_cost: '', purchase_date: '',
    put_to_use_date: '', capitalization_date: '',
    opening_accumulated_depreciation: '', opening_wdv: '', opening_it_wdv: '',
    useful_life_months: '', useful_life_override_reason: '', residual_pct: '',
    custodian_name: '', serial_number: '', remarks: '', branch_id: '' as string | null,
  })
  const [errors, setErrors] = useState<Errors>({})
  const set = (k: keyof typeof values, v: string) => setValues((s) => ({ ...s, [k]: v }))

  const applyDefaultsAndPick = (categoryId: string) => {
    set('categoryId', categoryId)
    for (const g of tree) {
      const leaf =
        g.children.find((c) => c.id === categoryId) ??
        (g.parent.id === categoryId ? g.children[0] : undefined)
      if (leaf) {
        setValues((s) => ({
          ...s, categoryId,
          useful_life_months:
            s.useful_life_months || (leaf.default_useful_life_months ? String(leaf.default_useful_life_months) : ''),
          residual_pct:
            s.residual_pct || (leaf.default_residual_pct != null ? String(leaf.default_residual_pct) : ''),
        }))
        return
      }
    }
  }

  const picked = (() => {
    for (const g of tree) {
      if (g.parent.id === values.categoryId) return { path: [g.parent.name], leafName: g.parent.name }
      const c = g.children.find((x) => x.id === values.categoryId)
      if (c) return { path: [g.parent.name, c.name], leafName: c.name }
    }
    return null
  })()

  const isProbablyPreFY = (dateStr: string) => {
    const d = new Date(dateStr)
    if (Number.isNaN(d.getTime())) return false
    const now = new Date()
    const fyStartYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1
    return d < new Date(fyStartYear, 3, 1) // India FY starts April 1
  }

  const validate = (): boolean => {
    const e: Errors = {}
    if (!values.asset_name.trim()) e.asset_name = 'Required'
    if (!values.categoryId) e.category_id = 'Required'
    const cost = Number(values.original_cost)
    if (!values.original_cost.trim() || Number.isNaN(cost) || cost <= 0) e.original_cost = 'Required, greater than 0'
    for (const k of OPENING_FIELDS) {
      const v = values[k].trim() === '' ? null : Number(values[k])
      if (v !== null && Number.isNaN(v)) e[k] = 'Must be a number'
      else if (v !== null && v < 0) e[k] = 'Cannot be negative'
      else if (v !== null && v > cost) e[k] = 'Cannot exceed original cost'
    }
    const effective = values.put_to_use_date || values.capitalization_date
    if (effective && isProbablyPreFY(effective)) {
      const missing = OPENING_FIELDS.filter((k) => values[k].trim() === '')
      if (missing.length) {
        e.opening =
          'Opening WDV (tax), WDV (books) and accumulated depreciation are all required for assets predating this financial year'
      }
    }
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const submit = async () => {
    if (!validate()) return
    try {
      const created = await create.mutateAsync({
        asset_name: values.asset_name.trim(),
        category_path: picked?.path ?? [],
        original_cost: values.original_cost,
        purchase_date: values.purchase_date || null,
        put_to_use_date: values.put_to_use_date || null,
        capitalization_date: values.capitalization_date || null,
        opening_accumulated_depreciation: values.opening_accumulated_depreciation || null,
        opening_wdv: values.opening_wdv || null,
        opening_it_wdv: values.opening_it_wdv || null,
        useful_life_months: values.useful_life_months ? Number(values.useful_life_months) : null,
        useful_life_override_reason: values.useful_life_override_reason || null,
        residual_pct: values.residual_pct || null,
        custodian_name: values.custodian_name || null,
        serial_number: values.serial_number || null,
        remarks: values.remarks || null,
        branch_id: values.branch_id || null,
      })
      toast.success('Draft asset created')
      navigate(`/app/assets/${created.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError && typeof err.detail === 'string' ? err.detail
        : err instanceof Error ? err.message : 'Could not create the asset')
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        eyebrow="OPERATIONS"
        title="Add existing asset"
        description="Record an asset the company already owned — with its opening book and tax values."
        actions={<Button variant="ghost" onClick={() => navigate('/app/assets')}>
          <ArrowLeft className="mr-1.5 h-4 w-4" />Back</Button>}
      />

      <Card className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
        <Field label="Asset name" required error={errors.asset_name}>
          <Input aria-label="Asset name" value={values.asset_name}
                 onChange={(e) => set('asset_name', e.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <CategoryPicker value={values.categoryId} onChange={applyDefaultsAndPick}
                          error={errors.category_id} required />
        </div>
        <Field label="Serial number">
          <Input aria-label="Serial number" value={values.serial_number}
                 onChange={(e) => set('serial_number', e.target.value)} />
        </Field>
        <Field label="Custodian">
          <Input aria-label="Custodian" value={values.custodian_name}
                 onChange={(e) => set('custodian_name', e.target.value)} />
        </Field>
      </Card>

      <Card className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
        <Field label="Original cost" required error={errors.original_cost}>
          <Input aria-label="Original cost" type="number" min={0} step="0.01"
                 value={values.original_cost}
                 onChange={(e) => set('original_cost', e.target.value)} />
        </Field>
        <Field label="Purchase date">
          <Input aria-label="Purchase date" type="date" value={values.purchase_date}
                 onChange={(e) => set('purchase_date', e.target.value)} />
        </Field>
        <Field label="Put-to-use date">
          <Input aria-label="Put-to-use date" type="date" value={values.put_to_use_date}
                 onChange={(e) => set('put_to_use_date', e.target.value)} />
        </Field>
        <Field label="Capitalization date">
          <Input aria-label="Capitalization date" type="date" value={values.capitalization_date}
                 onChange={(e) => set('capitalization_date', e.target.value)} />
        </Field>
      </Card>

      <Card className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
        <Field label="Useful life (months)" hint="Pre-filled from the category default">
          <Input aria-label="Useful life (months)" type="number" min={1}
                 value={values.useful_life_months}
                 onChange={(e) => set('useful_life_months', e.target.value)} />
        </Field>
        <Field label="Residual %">
          <Input aria-label="Residual %" type="number" min={0} max={100} step="0.01"
                 value={values.residual_pct}
                 onChange={(e) => set('residual_pct', e.target.value)} />
        </Field>
        <Field label="Life override reason" className="sm:col-span-3"
               hint="Required when the life differs from Schedule II defaults">
          <Input aria-label="Life override reason" value={values.useful_life_override_reason}
                 onChange={(e) => set('useful_life_override_reason', e.target.value)} />
        </Field>
      </Card>

      <Card className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
        <p className="text-xs text-text-muted sm:col-span-3">
          Opening balances as on the register cutover. All three are required when
          the asset predates the current financial year.
        </p>
        <Field label="Opening accumulated depreciation" error={errors.opening_accumulated_depreciation}>
          <Input aria-label="Opening accumulated depreciation" type="number" min={0} step="0.01"
                 value={values.opening_accumulated_depreciation}
                 onChange={(e) => set('opening_accumulated_depreciation', e.target.value)} />
        </Field>
        <Field label="Opening WDV (books)" error={errors.opening_wdv}>
          <Input aria-label="Opening WDV (books)" type="number" min={0} step="0.01"
                 value={values.opening_wdv}
                 onChange={(e) => set('opening_wdv', e.target.value)} />
        </Field>
        <Field label="Opening WDV (tax)" error={errors.opening_it_wdv}>
          <Input aria-label="Opening WDV (tax)" type="number" min={0} step="0.01"
                 value={values.opening_it_wdv}
                 onChange={(e) => set('opening_it_wdv', e.target.value)} />
        </Field>
        {errors.opening && (
          <p className="text-xs font-medium text-status-action sm:col-span-3">{errors.opening}</p>
        )}
      </Card>

      <Card className="p-4">
        {/* Match LookupSelect's real props by reading ./LookupSelect before wiring */}
        <LookupSelect kind="branch" label="Branch" value={values.branch_id ?? ''}
                      onChange={(v) => set('branch_id', v || '')} />
      </Card>

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => navigate('/app/assets')}>Cancel</Button>
        <Button onClick={submit} loading={create.isPending}>Save draft</Button>
      </div>
    </div>
  )
}
```

Remove unused imports (`Textarea`) after finalizing. Wire-up:

- `AssetsPage.tsx`: replace the "New asset" `<Button>` with `<AddAssetButton />`; delete the `quickAddOpen` state and the standalone `<QuickAddAssetModal …/>`; prune imports.
- `company.routes.tsx`: inside the `assets` children, BEFORE `:assetId`:
  `{ path: 'new/existing', element: <ExistingAssetPage /> },`

Update `assets.test.tsx`'s "New asset button" case: click `Add asset`, then `New asset`.

- [ ] **Step 5: Run frontend tests + typecheck**

Run: `npx vitest run src/pages/company/assets/ && npx tsc -p tsconfig.app.json --noEmit`
Expected: PASS / no type errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/company/assets/AddAssetButton.tsx frontend/src/pages/company/assets/ExistingAssetPage.tsx frontend/src/pages/company/assets/AddAssetButton.test.tsx frontend/src/pages/company/assets/ExistingAssetPage.test.tsx frontend/src/api/endpoints/assets.ts frontend/src/api/types.ts frontend/src/api/hooks/assets.ts frontend/src/routes/company.routes.tsx frontend/src/pages/company/assets/AssetsPage.tsx frontend/src/pages/company/assets/assets.test.tsx
git commit -m "feat(assets): add-asset dropdown and existing-asset opening entry page"
```

---

### Task 10: Masters edit modals with impact guard

**Files:**
- Create: `frontend/src/pages/company/assets/masters/ImpactNotice.tsx`
- Modify: `frontend/src/api/endpoints/assetMasters.ts`
- Modify: `frontend/src/api/types.ts` (`ImpactPreview`)
- Modify: `frontend/src/api/hooks/assetMasters.ts`
- Modify: `frontend/src/pages/company/assets/masters/CategoriesTab.tsx`
- Modify: `frontend/src/pages/company/assets/masters/ItBlocksTab.tsx`
- Modify: `frontend/src/pages/company/assets/masters/SuppliersTab.tsx`
- Modify: `frontend/src/pages/company/assets/masters/LookupsTab.tsx`
- Create test: `frontend/src/pages/company/assets/masters/mastersEdit.test.tsx`

**Interfaces:**
- Consumes: `PATCH /asset-masters/it-blocks/{id}` (Task 3), `GET /asset-masters/{kind}/{id}/impact-preview` (Task 4), existing `useUpdateCategory/useUpdateSupplier/useUpdateLookup`.
- Produces:
  - `assetsApi.updateItBlock(id, body)`, `assetsApi.impactPreview(kind, id)`
  - hooks `useCreateItBlock`, `useUpdateItBlock`, `useImpactPreview(kind, id)` (enabled only when both non-null)
  - `<ImpactNotice kind id />` component; the ack-gate pattern below is used by every edit modal.

- [ ] **Step 1: Endpoints, types, hooks**

`types.ts`:

```ts
export interface ImpactPreview {
  kind: string
  id: string
  assets_referencing: number
  draft_run_fy_labels: string[]
  finalized_run_fy_labels: string[]
  classification: 'none' | 'future_only'
  message: string
}
```

`endpoints/assetMasters.ts` (check whether `createItBlock` exists; add in the same shape if not):

```ts
  createItBlock: (body: Partial<ItAssetBlockResponse>) =>
    companyClient.post<ItAssetBlockResponse>(`${BASE}/it-blocks`, body),
  updateItBlock: (id: string, body: Partial<ItAssetBlockResponse>) =>
    companyClient.patch<ItAssetBlockResponse>(`${BASE}/it-blocks/${id}`, body),
  impactPreview: (kind: ImpactKind, id: string) =>
    companyClient.get<ImpactPreview>(`${BASE}/${kind}/${id}/impact-preview`),
```

with `export type ImpactKind = 'category' | 'it_block' | 'supplier' | 'lookup'` in `types.ts`.

`hooks/assetMasters.ts`:

```ts
export function useCreateItBlock() {
  const invalidate = useInvalidateMasters()
  return useMutation({
    mutationFn: (body: Partial<ItAssetBlockResponse>) => assetMastersApi.createItBlock(body),
    onSuccess: invalidate,
  })
}

export function useUpdateItBlock() {
  const invalidate = useInvalidateMasters()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ItAssetBlockResponse> }) =>
      assetMastersApi.updateItBlock(id, body),
    onSuccess: invalidate,
  })
}

export function useImpactPreview(kind: ImpactKind | null, id: string | null) {
  return useQuery({
    queryKey: ['asset-masters', 'impact', kind, id],
    queryFn: () => assetMastersApi.impactPreview(kind!, id!),
    enabled: !!kind && !!id,
  })
}
```

- [ ] **Step 2: Failing test**

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ItBlocksTab } from './ItBlocksTab'

vi.mock('@/api/hooks/assetMasters', () => {
  const block = { id: 'blk-1', company_id: 'c1', code: 'PM-15', name: 'P&M general',
                  dep_rate: 15, block_class: 'plant_machinery', is_active: true,
                  display_order: 50 }
  const updateItBlock = vi.fn().mockResolvedValue(block)
  return {
    useItBlocks: () => ({ data: [block], isLoading: false }),
    useCreateItBlock: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useUpdateItBlock: () => ({ mutateAsync: updateItBlock, isPending: false }),
    useImpactPreview: () => ({
      data: { kind: 'it_block', id: 'blk-1', assets_referencing: 4,
              draft_run_fy_labels: [], finalized_run_fy_labels: ['2024-25'],
              classification: 'future_only',
              message: 'Future depreciation runs will use the new values.' },
      isLoading: false,
    }),
  }
})

describe('ItBlocksTab — editable blocks', () => {
  it('shows the impact verdict inside the edit modal and gates save on ack', async () => {
    render(<ItBlocksTab />)
    fireEvent.click(screen.getAllByRole('button', { name: /edit/i })[0])
    expect(await screen.findByText(/future depreciation runs/i)).toBeInTheDocument()

    const save = screen.getByRole('button', { name: /^save$/i })
    expect(save).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/i understand/i))
    expect(save).toBeEnabled()

    fireEvent.change(screen.getByLabelText(/rate/i), { target: { value: '40' } })
    fireEvent.click(save)
    await waitFor(() =>
      expect(vi.mocked(screen.getByLabelText(/i understand/i).closest('form') ?? {} as never))
        .toBeDefined(), // ack gate exercised; real assertion below
    )
  })
})
```

Simplify that last block before committing — assert the mutation call directly:

```tsx
    // (preferred final form of the test)
    fireEvent.change(screen.getByLabelText(/rate/i), { target: { value: '40' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(updateItBlock).toHaveBeenCalledWith(
      expect.objectContaining({ body: expect.objectContaining({ dep_rate: 40 }) }),
    ))
```

(keep one coherent version — the mock returns `updateItBlock` so it can be imported at module scope for assertions).

- [ ] **Step 3: Run to verify failure**

Run: `npx vitest run src/pages/company/assets/masters/mastersEdit.test.tsx`
Expected: FAIL — no Edit buttons.

- [ ] **Step 4: ImpactNotice + gate pattern + tab wiring**

`masters/ImpactNotice.tsx`:

```tsx
import { AlertTriangle, ShieldCheck } from 'lucide-react'
import { useImpactPreview, type ImpactKind } from '@/api/hooks/assetMasters'

export interface ImpactNoticeProps {
  kind: ImpactKind
  id: string | null
}

/** Live verdict rendered inside every masters edit modal BEFORE saving: what
 *  this edit will and will not change. Non-`none` classifications make the
 *  modal require an explicit acknowledgement before Save enables. */
export function ImpactNotice({ kind, id }: ImpactNoticeProps) {
  const { data, isLoading } = useImpactPreview(id ? kind : null, id)
  if (!data || isLoading || !id) return null
  return (
    <div className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${
      data.classification === 'none'
        ? 'border-border bg-bg-raised text-text-secondary'
        : 'border-status-warning/40 bg-status-warning/10 text-text-primary'
    }`}>
      {data.classification === 'none'
        ? <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
      <div>
        <p>{data.message}</p>
        {(data.draft_run_fy_labels.length > 0 || data.finalized_run_fy_labels.length > 0) && (
          <p className="mt-1 text-xs text-text-muted">
            Draft runs: {data.draft_run_fy_labels.join(', ') || '—'} ·
            Finalized: {data.finalized_run_fy_labels.join(', ') || '—'}
          </p>
        )}
      </div>
    </div>
  )
}
```

(Copy whichever warning-color token `StatusBadge` uses if `status-warning` differs.)

Gate pattern inside each edit modal footer:

```tsx
const preview = useImpactPreview(editingId ? kindForThisTab : null, editingId)
const needsAck = !!preview.data && preview.data.classification !== 'none'
const [acked, setAcked] = useState(false)
// reset acked whenever the modal opens: useEffect(() => setAcked(false), [open])

<Button disabled={needsAck && !acked} loading={mutation.isPending} onClick={save}>Save</Button>
{needsAck && (
  <label className="flex items-center gap-2 text-sm">
    <input type="checkbox" aria-label="I understand" checked={acked}
           onChange={(e) => setAcked(e.target.checked)} />
    I understand the effects described above
  </label>
)}
```

Per tab:

- **CategoriesTab**: convert the single create modal into dual-mode state `{ mode: 'create' } | { mode: 'edit'; category: AssetCategoryResponse }`. Parent card header gets an Edit button (name/prefix fields only); every subcategory row gets an Edit action pre-filling all default fields; save calls `useUpdateCategory` with `{ id, body }`. Include `<ImpactNotice kind="category" id={editing.id} />` above the footer.
- **ItBlocksTab**: add "New block" button + per-row Edit opening a modal with code/name/rate/class/order/active; create via `useCreateItBlock`, save via `useUpdateItBlock`; include `<ImpactNotice kind="it_block" …/>`. Keep the DataTable columns.
- **SuppliersTab / LookupsTab**: add per-row Edit buttons opening modals pre-filled from the row; wire to the existing-but-unused `useUpdateSupplier` / `useUpdateLookup`; `<ImpactNotice kind="supplier"|"lookup" …/>`.

- [ ] **Step 5: Run tests + typecheck**

Run: `npx vitest run src/pages/company/assets/ && npx tsc -p tsconfig.app.json --noEmit`
Expected: PASS / no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/company/assets/masters/ frontend/src/api/endpoints/assetMasters.ts frontend/src/api/hooks/assetMasters.ts frontend/src/api/types.ts
git commit -m "feat(assets): editable masters everywhere with impact-aware edit modals"
```

---

### Task 11: Reopen UI + import UI

**Files:**
- Modify: `frontend/src/api/endpoints/depreciation.ts`, `frontend/src/api/hooks/depreciation.ts`
- Modify: `frontend/src/pages/company/assets/tabs/DepreciationTab.tsx`
- Create: `frontend/src/pages/company/assets/masters/importExisting.ts(x)` — or fold template/upload actions into ExistingAssetPage header (choose one home; spec puts them on the Existing asset page)
- Modify: `frontend/src/pages/company/assets/ExistingAssetPage.tsx`
- Create test: `frontend/src/pages/company/assets/tabs/reopen.test.tsx`

**Interfaces:**
- Consumes: `POST /depreciation/runs/{id}/reopen` (Task 5), `GET /assets/import/template` + `POST /assets/import` (Task 7).
- Produces: `depreciationApi.reopenRun(runId, reason)` + `useReopenDepreciationRun()`; `assetsApi.downloadImportTemplate()`, `assetsApi.importAssets(file)` + `useImportAssets()`.

- [ ] **Step 1: Endpoints + hooks**

`endpoints/depreciation.ts`:

```ts
  reopenRun: (runId: string, reason: string) =>
    companyClient.post<DepreciationRunResponse>(`${BASE}/runs/${runId}/reopen`, { reason }),
```

`hooks/depreciation.ts`:

```ts
export function useReopenDepreciationRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ runId, reason }: { runId: string; reason: string }) =>
      depreciationApi.reopenRun(runId, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['depreciation'] }),
  })
}
```

(match the file's existing query-key convention used by `useDepreciationRuns`)

`endpoints/assets.ts`:

```ts
  downloadImportTemplate: () => companyClient.download(`${BASE}/import/template`),
  importAssets: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return companyClient.post<{ created_count: number; first_asset_id: string | null }>(
      `${BASE}/import`, form)
  },
```

(check how `exportExcel` performs blob downloads in this codebase and copy that exact mechanism instead of guessing a `download` helper.)

`hooks/assets.ts`:

```ts
export function useImportAssets() {
  return useMutation({
    mutationFn: (file: File) => assetsApi.importAssets(file),
  })
}
```

- [ ] **Step 2: Failing test**

`tabs/reopen.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('@/api/hooks/depreciation', () => ({
  useDepreciationRuns: () => ({
    data: [{ id: 'r1', status: 'finalized', financial_year_label: '2024-25',
             notes: '', total_gross_block: 0, total_depreciation: 0 }],
    isLoading: false,
  }),
}))
const reopen = vi.fn().mockResolvedValue({ id: 'r1', status: 'draft' })
vi.mock('@/api/hooks/depreciation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/hooks/depreciation')>()),
  useReopenDepreciationRun: () => ({ mutateAsync: reopen, isPending: false }),
}))

describe('DepreciationTab — reopen finalized run', () => {
  it('asks for a reason and reopens', async () => {
    render(<DepreciationTabAssetId assetId="a-1" />)  // wrap DepreciationTab with required props
    fireEvent.click(screen.getByRole('button', { name: /reopen/i }))
    fireEvent.change(await screen.findByLabelText(/reason/i), { target: { value: 'Wrong opening WDV' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm reopen/i }))
    await waitFor(() => expect(reopen).toHaveBeenCalledWith(
      expect.objectContaining({ runId: 'r1', reason: 'Wrong opening WDV' })))
  })
})
```

Read `DepreciationTab.tsx`'s actual props first and instantiate accordingly (it may take `assetId` or read route params — mock `react-router-dom` the way `assets.test.tsx` does if needed).

- [ ] **Step 3: Run to verify failure**

Run: `npx vitest run src/pages/company/assets/tabs/reopen.test.tsx`
Expected: FAIL — no Reopen button.

- [ ] **Step 4: Implement**

**DepreciationTab**: next to the existing Finalize button on a finalized run, render an admin-only Reopen button (get role via `useCompanyAuth()` exactly like `AssetsPage` does):

```tsx
{isAdmin && run.status === 'finalized' && (
  <>
    <Button variant="secondary" onClick={() => { setReopenRunId(run.id); setOpen(true) }}>
      Reopen
    </Button>
    <ConfirmDialog
      open={open}
      onClose={() => setOpen(false)}
      title="Reopen finalized depreciation?"
      description={`${run.financial_year_label} will flip back to draft so you can correct inputs and regenerate. Redo years oldest-first.`}
      confirmLabel="Reopen"
    >
      <Field label="Reason (recorded in the audit log)" required>
        <Textarea aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
    </ConfirmDialog>
  </>
)}
```

On confirm:

```tsx
try {
  await reopenMutation.mutateAsync({ runId: reopenRunId!, reason: reason.trim() })
  toast.success('Run reopened to draft')
} catch (e) {
  toast.error(e instanceof Error ? e.message : 'Reopen failed')
}
```

Disable the confirm while `reason.trim().length < 3` (mirrors backend validation). Use the codebase's actual `ConfirmDialog` API — read it before writing.

**ExistingAssetPage header**: two secondary buttons beside Back:

```tsx
const template = async () => saveBlob(await assetsApi.downloadImportTemplate(), 'asset_import_template.xlsx')

const importInputRef = useRef<HTMLInputElement>(null)
// hidden input: <input ref={importInputRef} type="file" accept=".xlsx,.csv" className="hidden"
//   onChange={(e) => e.target.files?.[0] && doImport(e.target.files[0])} />
const doImport = async (file: File) => {
  try {
    const res = await importMutation.mutateAsync(file)
    toast.success(`Imported ${res.created_count} assets`)
    navigate(`/app/assets/${res.first_asset_id}`)
  } catch (e) {
    // 422 detail is [{row, message}, ...]
    const detail = (e as ApiError).detail
    if (Array.isArray(detail)) {
      setImportErrors(detail.slice(0, 20))   // render list under the card
      toast.error(`${detail.length} rows failed — nothing was imported`)
    } else {
      toast.error(e instanceof Error ? e.message : 'Import failed')
    }
  }
}
```

Render `importErrors` as a simple bordered list ("Row N — message") when non-empty; clear on success. Match `saveBlob` usage from `AssetsPage.handleExport`.

- [ ] **Step 5: Run frontend suite + typecheck**

Run: `npx vitest run src/pages/company/assets/ && npx tsc -p tsconfig.app.json --noEmit`
Expected: PASS / no errors.

- [ ] **Step 6: Full verification sweep + commit**

Backend: `pytest tests/ -v` (whole suite green).
Frontend: `npx vitest run`.

```bash
git add frontend/src/
git commit -m "feat(assets): reopen finalized runs and bulk-import entry points"
```

---

## Final verification

1. `pytest tests/ -v` — full backend suite.
2. From `frontend/`: `npx vitest run && npx tsc -p tsconfig.app.json --noEmit`.
3. Manual smoke: create a fresh company → masters show owned editable rows → Add asset ▸ Existing asset → save an opening entry → download template, fill, import → edit an IT block rate (observe impact notice) → run + finalize depreciation → reopen works; editing the block again names the finalized year.
4. Delete-and-recreate any legacy companies against a staging DB before deploying (spec decision).

