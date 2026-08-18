"""Integration tests for asset disposals."""
from datetime import date
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.assets import Asset, AssetLifecycleStatus, AssetOperationalStatus
from app.models.asset_masters import AssetCategory
from app.models.company import CompanyUser
from app.models.financial_year import FinancialYear, FinancialYearStatus
from tests.asset_helpers import admin_headers, seed_masters
from tests.conftest import TestSessionLocal


@pytest.mark.asyncio
async def test_dispose_draft_asset_rejected(client: AsyncClient):
    """Disposing a draft asset must return 409 Conflict."""
    await seed_masters()
    email = "admin_disp_draft@testco.com"
    headers = await admin_headers(client, email)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        cat = (await session.execute(select(AssetCategory))).scalars().first()

        draft_asset = Asset(
            company_id=user.company_id,
            asset_name="Draft Asset Prototype",
            category_id=cat.id if cat else None,
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
    await seed_masters()
    email = "admin_disp_date@testco.com"
    headers = await admin_headers(client, email)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        cat = (await session.execute(select(AssetCategory))).scalars().first()

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Capitalized Laptop A",
            asset_code="LAP-001",
            category_id=cat.id if cat else None,
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
    await seed_masters()
    email = "admin_disp_closed@testco.com"
    headers = await admin_headers(client, email)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        cat = (await session.execute(select(AssetCategory))).scalars().first()

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
            category_id=cat.id if cat else None,
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
    await seed_masters()
    email = "admin_disp_noproc@testco.com"
    headers = await admin_headers(client, email)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        cat = (await session.execute(select(AssetCategory))).scalars().first()

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Capitalized Vehicle Y",
            asset_code="VEH-200",
            category_id=cat.id if cat else None,
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
    await seed_masters()
    email = "admin_disp_good@testco.com"
    headers = await admin_headers(client, email)

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        cat = (await session.execute(select(AssetCategory))).scalars().first()

        cap_asset = Asset(
            company_id=user.company_id,
            asset_name="Capitalized Laptop B",
            asset_code="LAP-002",
            category_id=cat.id if cat else None,
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
