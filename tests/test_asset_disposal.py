"""Integration tests for asset disposals."""
from datetime import date
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.assets import Asset, AssetLifecycleStatus, AssetOperationalStatus
from app.models.company import CompanyUser
from app.models.financial_year import FinancialYear, FinancialYearStatus
from tests.asset_helpers import admin_headers, make_user, user_headers
from tests.conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_dispose_draft_asset_rejected(client: AsyncClient):
    """Disposing a draft asset must return 409 Conflict."""
    email = "admin_disp_draft@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        draft_asset = Asset(
            company_id=user.company_id,
            asset_name="Draft Asset Prototype",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.draft,
            operational_status=AssetOperationalStatus.in_use,
            original_cost=Decimal("50000.00"),
        )
        session.add(draft_asset)
        await session.commit()
        await session.refresh(draft_asset)
        draft_id = str(draft_asset.id)

    disp_res = await client.post(
        f"/api/v1/assets/{draft_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 20000.0,
        },
        headers=headers,
    )
    assert disp_res.status_code == 409, f"Expected 409 for draft asset disposal, got {disp_res.status_code}: {disp_res.text}"


@pytest.mark.asyncio
async def test_disposal_date_before_capitalization_rejected(client: AsyncClient):
    """Disposal date earlier than capitalization date must return 422 Unprocessable Entity."""
    email = "admin_disp_date@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Capitalized Laptop A",
            asset_code="LAP-001",
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
        cap_id = str(cap_asset.id)

    bad_disp = await client.post(
        f"/api/v1/assets/{cap_id}/dispose",
        json={
            "disposal_date": "2024-03-01",
            "disposal_type": "sale",
            "sale_proceeds": 20000.0,
        },
        headers=headers,
    )
    assert bad_disp.status_code == 422, f"Expected 422 for premature disposal date, got {bad_disp.status_code}: {bad_disp.text}"


@pytest.mark.asyncio
async def test_disposal_into_closed_financial_year_rejected(client: AsyncClient):
    """Disposal date in a closed financial year must return 422 Unprocessable Entity.
    
    Expected to FAIL: Rule is not implemented in disposal endpoint.
    """
    email = "admin_disp_closed@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        closed_fy = FinancialYear(
            company_id=user.company_id,
            label="2023-24",
            start_date=date(2023, 4, 1),
            end_date=date(2024, 3, 31),
            status=FinancialYearStatus.closed.value,
        )
        session.add(closed_fy)

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Capitalized Machine X",
            asset_code="MCH-100",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2023, 4, 1),
            available_for_use_date=date(2023, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
        )
        session.add(cap_asset)
        await session.commit()
        await session.refresh(cap_asset)
        cap_id = str(cap_asset.id)

    disp_res = await client.post(
        f"/api/v1/assets/{cap_id}/dispose",
        json={
            "disposal_date": "2023-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 50000.0,
        },
        headers=headers,
    )
    assert disp_res.status_code == 422, f"Expected 422 for disposal in closed financial year, got {disp_res.status_code}: {disp_res.text}"


@pytest.mark.asyncio
async def test_disposal_sale_without_proceeds_rejected(client: AsyncClient):
    """Disposal with type 'sale' / 'sold' with sale_proceeds omitted must return 422 Unprocessable Entity.
    
    Expected to FAIL: Schema defaults proceeds to 0.00 and does not require explicit proceeds on sales.
    """
    email = "admin_disp_noproc@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Capitalized Vehicle Y",
            asset_code="VEH-200",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("200000.00"),
        )
        session.add(cap_asset)
        await session.commit()
        await session.refresh(cap_asset)
        cap_id = str(cap_asset.id)

    disp_res = await client.post(
        f"/api/v1/assets/{cap_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
        },
        headers=headers,
    )
    assert disp_res.status_code == 422, f"Expected 422 when sale_proceeds is omitted on sale disposal, got {disp_res.status_code}: {disp_res.text}"


@pytest.mark.asyncio
async def test_successful_asset_disposal(client: AsyncClient):
    """Successful disposal sets lifecycle_status to disposed and records disposal fields."""
    email = "admin_disp_good@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Capitalized Laptop B",
            asset_code="LAP-002",
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
        cap_id = str(cap_asset.id)

    good_disp = await client.post(
        f"/api/v1/assets/{cap_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 25000.0,
            "buyer_name": "Tech Recyclers Ltd",
            "disposal_invoice_no": "INV-DISP-101",
            "disposal_remarks": "Sold after project completion",
        },
        headers=headers,
    )
    assert good_disp.status_code == 200, f"Expected 200 for valid disposal, got {good_disp.status_code}: {good_disp.text}"
    asset_data = good_disp.json()
    assert asset_data["lifecycle_status"] == "disposed"
    assert asset_data["disposal_date"] == "2024-09-30"
    assert float(asset_data["sale_proceeds"]) == 25000.0
    assert asset_data["buyer_name"] == "Tech Recyclers Ltd"


@pytest.mark.parametrize("disp_type", ["scrap", "write_off", "loss_destruction"])
@pytest.mark.asyncio
async def test_disposal_without_proceeds(client: AsyncClient, disp_type: str):
    """B2: Disposals without proceeds (scrap, write_off, loss_destruction) must return 200 and set status disposed."""
    email = f"admin_disp_{disp_type}@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name=f"Equipment for {disp_type}",
            asset_code=f"EQ-{disp_type[:4].upper()}-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=36,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("75000.00"),
        )
        session.add(cap_asset)
        await session.commit()
        await session.refresh(cap_asset)
        cap_id = str(cap_asset.id)

    disp_res = await client.post(
        f"/api/v1/assets/{cap_id}/dispose",
        json={
            "disposal_date": "2024-10-15",
            "disposal_type": disp_type,
            # No sale_proceeds provided
        },
        headers=headers,
    )
    assert disp_res.status_code == 200, f"Expected 200 for {disp_type} disposal without proceeds, got {disp_res.status_code}: {disp_res.text}"
    data = disp_res.json()
    assert data["lifecycle_status"] == "disposed"
    assert data["disposal_type"] == disp_type


@pytest.mark.asyncio
async def test_disposal_negative_sale_proceeds_rejected(client: AsyncClient):
    """B3: Negative sale proceeds must return 422 Unprocessable Entity."""
    email = "admin_disp_neg@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Asset with Negative Proceeds",
            asset_code="NEG-001",
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
        cap_id = str(cap_asset.id)

    disp_res = await client.post(
        f"/api/v1/assets/{cap_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": -50000.0,
        },
        headers=headers,
    )
    assert disp_res.status_code == 422, f"Expected 422 for negative sale_proceeds, got {disp_res.status_code}: {disp_res.text}"


@pytest.mark.asyncio
async def test_disposal_invalid_type_banana_returns_422(client: AsyncClient):
    """H1: Invalid disposal_type ('banana') must return 422 Unprocessable Entity."""
    email = "admin_disp_banana@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Asset for Banana Disposal",
            asset_code="BAN-001",
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
        cap_id = str(cap_asset.id)

    disp_res = await client.post(
        f"/api/v1/assets/{cap_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "banana",
            "sale_proceeds": 10000.0,
        },
        headers=headers,
    )
    assert disp_res.status_code == 422, f"Expected 422 for invalid disposal_type, got {disp_res.status_code}: {disp_res.text}"


@pytest.mark.asyncio
async def test_disposal_sets_disposed_by_user_attribution(client: AsyncClient):
    """H1: Disposing an asset sets asset.disposed_by to the acting user."""
    email = "admin_disp_by@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        user_id = user.id

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Asset with Disposed By Attribution",
            asset_code="ATTR-001",
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
        cap_id = cap_asset.id

    disp_res = await client.post(
        f"/api/v1/assets/{cap_id}/dispose",
        json={
            "disposal_date": "2024-09-30",
            "disposal_type": "sale",
            "sale_proceeds": 15000.0,
        },
        headers=headers,
    )
    assert disp_res.status_code == 200

    async with TestSessionLocal() as session:
        reloaded = await session.get(Asset, cap_id)
        assert reloaded is not None
        assert reloaded.disposed_by == user_id


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
            "sale_proceeds": 100.0,
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



