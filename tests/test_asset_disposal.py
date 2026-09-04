"""Integration tests for asset disposals."""
from datetime import date
from decimal import Decimal
import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.activity_log import ActivityLog
from app.models.assets import Asset, AssetLifecycleStatus, AssetOperationalStatus
from app.models.company import CompanyUser, UserRole
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

    async with TestSessionLocal() as session:
        refreshed = await session.get(Asset, uuid.UUID(asset_id))
        assert refreshed.lifecycle_status == AssetLifecycleStatus.capitalized
        assert refreshed.disposal_date is None
        assert refreshed.disposed_by is None


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





# --- Additional coverage for KUB-020 (see the design's test plan) ---


async def _capitalized_asset_for(admin_email: str, cat_id: str, code: str) -> uuid.UUID:
    """Insert a genuinely capitalized, company-owned asset and return its id."""
    async with TestSessionLocal() as session:
        user = (
            await session.execute(
                select(CompanyUser).where(CompanyUser.email == admin_email)
            )
        ).scalar_one()
        asset = Asset(
            company_id=user.company_id,
            asset_name=f"Fixture {code}",
            asset_code=code,
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
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return asset.id


async def _child_category_id(client: AsyncClient, admin_h: dict) -> str:
    cats = (await client.get("/api/v1/asset-masters/categories", headers=admin_h)).json()
    return next(c["id"] for c in cats if c["parent_id"] is not None)


DISPOSAL_BODY = {
    "disposal_date": "2024-09-30",
    "disposal_type": "sale",
    "sale_proceeds": 10000.0,
    "buyer_name": "Some Buyer",
}


async def _assert_untouched(asset_id: uuid.UUID):
    """A rejected disposal must leave no trace at all — not on the row, not in
    the activity log. A 403 that still committed the write has to fail."""
    async with TestSessionLocal() as session:
        asset = await session.get(Asset, asset_id)
        assert asset.lifecycle_status == AssetLifecycleStatus.capitalized
        assert asset.disposal_date is None
        assert asset.disposal_type is None
        assert asset.sale_proceeds is None
        assert asset.buyer_name is None
        assert asset.disposed_by is None
        rows = (
            await session.execute(
                select(ActivityLog).where(
                    ActivityLog.entity_id == asset_id,
                    ActivityLog.action == "asset.disposed",
                )
            )
        ).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_employee_with_unrelated_module_cannot_dispose(client: AsyncClient):
    """Holding some *other* module is not holding `assets`."""
    admin_h = await admin_headers(client, "admin_disp_unrel@testco.com")
    created = await client.post(
        "/api/v1/users",
        headers=admin_h,
        json={
            "email": "sales_only_disp@testco.com",
            "password": "Valid1!Pass",
            "full_name": "Sales Only",
            "role": "employee",
            "accessible_modules": ["sales"],
        },
    )
    assert created.status_code == 201
    emp_h = await user_headers(client, "sales_only_disp@testco.com")

    cat_id = await _child_category_id(client, admin_h)
    asset_id = await _capitalized_asset_for(
        "admin_disp_unrel@testco.com", cat_id, "UNREL-001"
    )

    res = await client.post(
        f"/api/v1/assets/{asset_id}/dispose", json=DISPOSAL_BODY, headers=emp_h
    )
    assert res.status_code == 403
    assert "No access to the assets module" in res.text
    await _assert_untouched(asset_id)


@pytest.mark.asyncio
async def test_disposal_malformed_uuid_returns_422(client: AsyncClient):
    """A malformed path param is a request-shape error, not an auth signal."""
    admin_h = await admin_headers(client, "admin_disp_baduuid@testco.com")
    res = await client.post(
        "/api/v1/assets/not-a-uuid/dispose", json=DISPOSAL_BODY, headers=admin_h
    )
    assert res.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lifecycle",
    [
        AssetLifecycleStatus.draft,
        AssetLifecycleStatus.ready,
        AssetLifecycleStatus.disposed,
    ],
)
async def test_disposal_auth_precedes_state_for_every_lifecycle(
    client: AsyncClient, lifecycle: AssetLifecycleStatus
):
    """For a non-admin, the authorization error wins over the state error in
    *every* non-capitalized state — otherwise the 409 text ("this asset is
    draft") leaks the asset's lifecycle to someone with no business reading it.
    """
    email = f"admin_prec_{lifecycle.value}@testco.com"
    admin_h = await admin_headers(client, email)
    await make_user(client, admin_h, f"emp_prec_{lifecycle.value}@testco.com", role="employee")
    emp_h = await user_headers(client, f"emp_prec_{lifecycle.value}@testco.com")

    cat_id = await _child_category_id(client, admin_h)
    async with TestSessionLocal() as session:
        user = (
            await session.execute(select(CompanyUser).where(CompanyUser.email == email))
        ).scalar_one()
        asset = Asset(
            company_id=user.company_id,
            asset_name=f"Precedence {lifecycle.value}",
            asset_code=f"PREC-{lifecycle.value.upper()}",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=lifecycle,
            operational_status=AssetOperationalStatus.in_use,
            original_cost=Decimal("50000.00"),
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        asset_id = asset.id

    res = await client.post(
        f"/api/v1/assets/{asset_id}/dispose", json=DISPOSAL_BODY, headers=emp_h
    )
    assert res.status_code == 403, res.text
    assert lifecycle.value not in res.text

    # The same asset, for an admin, must surface the real state error instead.
    admin_res = await client.post(
        f"/api/v1/assets/{asset_id}/dispose", json=DISPOSAL_BODY, headers=admin_h
    )
    assert admin_res.status_code == 409, admin_res.text
    assert lifecycle.value in admin_res.json()["detail"]


@pytest.mark.asyncio
async def test_disposal_denied_after_role_downgraded_mid_session(client: AsyncClient):
    """Token still valid, permission gone. `get_current_company_user` re-reads the
    row on every request, so the role must be re-evaluated per call rather than
    trusted from the JWT."""
    admin_h = await admin_headers(client, "admin_downgrade@testco.com")
    cat_id = await _child_category_id(client, admin_h)
    asset_id = await _capitalized_asset_for(
        "admin_downgrade@testco.com", cat_id, "DOWNGRADE-001"
    )

    # Same token, role revoked underneath it. Keep the assets module granted so
    # the 403 proves the *role* gate fired, not the module gate.
    async with TestSessionLocal() as session:
        user = (
            await session.execute(
                select(CompanyUser).where(
                    CompanyUser.email == "admin_downgrade@testco.com"
                )
            )
        ).scalar_one()
        user.role = UserRole.employee
        user.accessible_modules = ["assets"]
        await session.commit()

    res = await client.post(
        f"/api/v1/assets/{asset_id}/dispose", json=DISPOSAL_BODY, headers=admin_h
    )
    assert res.status_code == 403, res.text
    assert "Insufficient permissions" in res.text
    await _assert_untouched(asset_id)


@pytest.mark.asyncio
async def test_concurrent_disposal_commits_exactly_once(client: AsyncClient):
    """Two disposals of the same unit fired together must not both land. Disposal
    is irreversible with a P&L consequence, so the loser has to 409 rather than
    overwrite the winner's proceeds/buyer/disposed_by or add a second
    `asset.disposed` log row."""
    admin_h = await admin_headers(client, "admin_concurrent@testco.com")
    cat_id = await _child_category_id(client, admin_h)
    asset_id = await _capitalized_asset_for(
        "admin_concurrent@testco.com", cat_id, "CONC-001"
    )

    first = {
        "disposal_date": "2024-09-30",
        "disposal_type": "sale",
        "sale_proceeds": 25000.0,
        "buyer_name": "Buyer One",
    }
    second = {
        "disposal_date": "2024-10-01",
        "disposal_type": "sale",
        "sale_proceeds": 1.0,
        "buyer_name": "Buyer Two",
    }

    responses = await asyncio.gather(
        client.post(f"/api/v1/assets/{asset_id}/dispose", json=first, headers=admin_h),
        client.post(f"/api/v1/assets/{asset_id}/dispose", json=second, headers=admin_h),
        return_exceptions=True,
    )
    for r in responses:
        assert not isinstance(r, BaseException), f"request raised: {r!r}"

    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409], [r.status_code for r in responses]

    winner = next(r for r in responses if r.status_code == 200).json()
    async with TestSessionLocal() as session:
        asset = await session.get(Asset, asset_id)
        assert asset.lifecycle_status == AssetLifecycleStatus.disposed
        # The persisted row must match whichever call won — not a blend.
        assert str(asset.disposal_date) == winner["disposal_date"]
        assert asset.buyer_name == winner["buyer_name"]
        assert Decimal(str(asset.sale_proceeds)) == Decimal(str(winner["sale_proceeds"]))

        rows = (
            await session.execute(
                select(ActivityLog).where(
                    ActivityLog.entity_id == asset_id,
                    ActivityLog.action == "asset.disposed",
                )
            )
        ).scalars().all()
        assert len(rows) == 1, f"expected one asset.disposed row, got {len(rows)}"


@pytest.mark.asyncio
async def test_kub_020_employee_with_module_exploit_prevented(client: AsyncClient):
    """KUB-020, second shape: the caller *can* legitimately see the asset register
    but still must not be able to dispose. Asserts state and side effects, not
    just the status code."""
    admin_h = await admin_headers(client, "admin_exploit2@testco.com")
    await make_user(client, admin_h, "attacker_mod@testco.com", role="employee")
    emp_h = await user_headers(client, "attacker_mod@testco.com")

    cat_id = await _child_category_id(client, admin_h)
    asset_id = await _capitalized_asset_for(
        "admin_exploit2@testco.com", cat_id, "SRV-KUB020-002"
    )

    # Sanity: this caller really does have read access to the register, so the
    # 403 below is about the role and not about the module.
    readable = await client.get(f"/api/v1/assets/{asset_id}", headers=emp_h)
    assert readable.status_code == 200

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
    assert "Insufficient permissions" in res.text
    await _assert_untouched(asset_id)
