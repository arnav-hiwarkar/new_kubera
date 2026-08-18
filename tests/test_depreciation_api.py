"""Integration tests for Depreciation Runs and Endpoints."""
from datetime import date
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.assets import Asset, AssetLifecycleStatus, AssetOperationalStatus
from app.models.asset_masters import AssetCategory, ItAssetBlock
from app.models.company import CompanyUser
from tests.asset_helpers import admin_headers, seed_masters
from tests.conftest import TestSessionLocal


async def setup_depreciation_environment(client: AsyncClient, email: str = "admin_depapi@testco.com"):
    await seed_masters()
    headers = await admin_headers(client, email)

    # 1. Create Financial Year
    fy_res = await client.post(
        "/api/v1/financial-years",
        json={
            "label": "2024-25",
            "start_date": "2024-04-01",
            "end_date": "2025-03-31",
        },
        headers=headers,
    )
    assert fy_res.status_code == 201, fy_res.text
    fy_id = fy_res.json()["id"]

    # 2. Insert capitalized asset directly into DB for test
    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        cat = (await session.execute(select(AssetCategory))).scalars().first()
        it_block = (await session.execute(select(ItAssetBlock))).scalars().first()

        asset = Asset(
            company_id=user.company_id,
            asset_name="Server Rack",
            asset_code="SRV-001",
            category_id=cat.id if cat else None,
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
            it_block_id=it_block.id if it_block else None,
            it_dep_rate=Decimal("15.00"),
            it_put_to_use_date=date(2024, 4, 1),
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        asset_id = str(asset.id)

    return {
        "headers": headers,
        "fy_id": fy_id,
        "asset_id": asset_id,
    }


@pytest.mark.asyncio
async def test_depreciation_run_creation_and_calculation(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_calc@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Initial FY24-25 calculation"},
        headers=headers,
    )
    assert run_res.status_code == 201, run_res.text
    run_data = run_res.json()
    assert run_data["status"] == "draft"
    assert float(run_data["total_gross_block"]) == 100000.0
    assert float(run_data["total_depreciation"]) == 19000.0
    assert float(run_data["total_carrying_amount"]) == 81000.0


@pytest.mark.asyncio
async def test_depreciation_run_listing(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_list@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Listing test run"},
        headers=headers,
    )
    assert run_res.status_code == 201, run_res.text

    list_res = await client.get("/api/v1/depreciation/runs", headers=headers)
    assert list_res.status_code == 200, list_res.text
    assert len(list_res.json()) == 1


@pytest.mark.asyncio
async def test_depreciation_run_lines(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_lines@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]
    asset_id = ctx["asset_id"]

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Lines test run"},
        headers=headers,
    )
    assert run_res.status_code == 201, run_res.text
    run_id = run_res.json()["id"]

    lines_res = await client.get(f"/api/v1/depreciation/runs/{run_id}/lines", headers=headers)
    assert lines_res.status_code == 200, lines_res.text
    lines = lines_res.json()
    assert len(lines) == 1
    assert lines[0]["asset_id"] == asset_id
    assert float(lines[0]["depreciation_for_year"]) == 19000.0


@pytest.mark.asyncio
async def test_depreciation_run_it_lines(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_itlines@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "IT lines test run"},
        headers=headers,
    )
    assert run_res.status_code == 201, run_res.text
    run_id = run_res.json()["id"]

    it_lines_res = await client.get(f"/api/v1/depreciation/runs/{run_id}/it-lines", headers=headers)
    assert it_lines_res.status_code == 200, it_lines_res.text
    it_lines = it_lines_res.json()
    assert len(it_lines) >= 1


@pytest.mark.asyncio
async def test_depreciation_run_finalize(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_fin@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Finalize test run"},
        headers=headers,
    )
    assert run_res.status_code == 201, run_res.text
    run_id = run_res.json()["id"]

    fin_res = await client.post(f"/api/v1/depreciation/runs/{run_id}/finalize", headers=headers)
    assert fin_res.status_code == 200, fin_res.text
    assert fin_res.json()["status"] == "finalized"
    assert fin_res.json()["finalized_at"] is not None


@pytest.mark.asyncio
async def test_depreciation_run_cannot_delete_finalized(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_nodel@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Delete guard test run"},
        headers=headers,
    )
    assert run_res.status_code == 201, run_res.text
    run_id = run_res.json()["id"]

    fin_res = await client.post(f"/api/v1/depreciation/runs/{run_id}/finalize", headers=headers)
    assert fin_res.status_code == 200, fin_res.text

    del_res = await client.delete(f"/api/v1/depreciation/runs/{run_id}", headers=headers)
    assert del_res.status_code == 409, f"Expected 409 when deleting finalized run, got {del_res.status_code}: {del_res.text}"


@pytest.mark.asyncio
async def test_depreciation_three_year_slm_carry_forward(client: AsyncClient):
    """Three consecutive financial years depreciation on a single SLM asset.
    
    Asset: Cost 100,000, Residual 5% (5,000), Life 60 months (5 yrs), SLM.
    Expected closing accumulated depreciation:
      - Year 1: 19,000.00
      - Year 2: 38,000.00
      - Year 3: 57,000.00
    
    Expected to FAIL: Opening balances are not carried forward from previous FY, so Yr2 and Yr3 produce 19,000.
    """
    await seed_masters()
    email = "three_year_slm@testco.com"
    headers = await admin_headers(client, email)

    # Create three consecutive financial years
    fy1_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy1_res.status_code == 201, fy1_res.text
    fy1_id = fy1_res.json()["id"]

    fy2_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2025-26", "start_date": "2025-04-01", "end_date": "2026-03-31"},
        headers=headers,
    )
    assert fy2_res.status_code == 201, fy2_res.text
    fy2_id = fy2_res.json()["id"]

    fy3_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2026-27", "start_date": "2026-04-01", "end_date": "2027-03-31"},
        headers=headers,
    )
    assert fy3_res.status_code == 201, fy3_res.text
    fy3_id = fy3_res.json()["id"]

    # Create single asset available for use on the first day of FY1
    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        cat = (await session.execute(select(AssetCategory))).scalars().first()

        asset = Asset(
            company_id=user.company_id,
            asset_name="Industrial Generator",
            asset_code="GEN-001",
            category_id=cat.id if cat else None,
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)

    # 1. Year 1 calculation & finalization
    run1_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy1_id, "notes": "Year 1 calculation"},
        headers=headers,
    )
    assert run1_res.status_code == 201, run1_res.text
    run1_id = run1_res.json()["id"]

    fin1_res = await client.post(f"/api/v1/depreciation/runs/{run1_id}/finalize", headers=headers)
    assert fin1_res.status_code == 200, fin1_res.text

    lines1_res = await client.get(f"/api/v1/depreciation/runs/{run1_id}/lines", headers=headers)
    assert lines1_res.status_code == 200, lines1_res.text
    line1 = lines1_res.json()[0]
    assert float(line1["closing_accumulated_depreciation"]) == 19000.00

    # 2. Year 2 calculation & finalization
    run2_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy2_id, "notes": "Year 2 calculation"},
        headers=headers,
    )
    assert run2_res.status_code == 201, run2_res.text
    run2_id = run2_res.json()["id"]

    fin2_res = await client.post(f"/api/v1/depreciation/runs/{run2_id}/finalize", headers=headers)
    assert fin2_res.status_code == 200, fin2_res.text

    lines2_res = await client.get(f"/api/v1/depreciation/runs/{run2_id}/lines", headers=headers)
    assert lines2_res.status_code == 200, lines2_res.text
    line2 = lines2_res.json()[0]
    assert float(line2["closing_accumulated_depreciation"]) == 38000.00, (
        f"Year 2 expected closing accumulated depreciation 38000.00, got {line2['closing_accumulated_depreciation']}"
    )

    # 3. Year 3 calculation & finalization
    run3_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy3_id, "notes": "Year 3 calculation"},
        headers=headers,
    )
    assert run3_res.status_code == 201, run3_res.text
    run3_id = run3_res.json()["id"]

    fin3_res = await client.post(f"/api/v1/depreciation/runs/{run3_id}/finalize", headers=headers)
    assert fin3_res.status_code == 200, fin3_res.text

    lines3_res = await client.get(f"/api/v1/depreciation/runs/{run3_id}/lines", headers=headers)
    assert lines3_res.status_code == 200, lines3_res.text
    line3 = lines3_res.json()[0]
    assert float(line3["closing_accumulated_depreciation"]) == 57000.00, (
        f"Year 3 expected closing accumulated depreciation 57000.00, got {line3['closing_accumulated_depreciation']}"
    )


@pytest.mark.asyncio
async def test_it_block_wdv_carry_forward(client: AsyncClient):
    """For an IT block, FY2's opening_wdv must equal FY1's finalized closing_wdv.
    
    Expected to FAIL: Opening WDV is not carried forward across consecutive FY runs.
    """
    await seed_masters()
    email = "it_carry_forward@testco.com"
    headers = await admin_headers(client, email)

    # Create consecutive FYs
    fy1_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy1_res.status_code == 201, fy1_res.text
    fy1_id = fy1_res.json()["id"]

    fy2_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2025-26", "start_date": "2025-04-01", "end_date": "2026-03-31"},
        headers=headers,
    )
    assert fy2_res.status_code == 201, fy2_res.text
    fy2_id = fy2_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        cat = (await session.execute(select(AssetCategory))).scalars().first()
        it_block = (await session.execute(select(ItAssetBlock))).scalars().first()
        it_block_id_str = str(it_block.id)

        asset = Asset(
            company_id=user.company_id,
            asset_name="Core Switch",
            asset_code="NET-001",
            category_id=cat.id if cat else None,
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
            it_block_id=it_block.id if it_block else None,
            it_dep_rate=Decimal("15.00"),
            it_put_to_use_date=date(2024, 4, 1),
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)

    # 1. Run & finalize FY1
    run1_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy1_id, "notes": "FY1 calculation"},
        headers=headers,
    )
    assert run1_res.status_code == 201, run1_res.text
    run1_id = run1_res.json()["id"]

    fin1_res = await client.post(f"/api/v1/depreciation/runs/{run1_id}/finalize", headers=headers)
    assert fin1_res.status_code == 200, fin1_res.text

    it_lines1_res = await client.get(f"/api/v1/depreciation/runs/{run1_id}/it-lines", headers=headers)
    assert it_lines1_res.status_code == 200, it_lines1_res.text
    it_lines1 = it_lines1_res.json()
    it_line1 = next(l for l in it_lines1 if l["it_block_id"] == it_block_id_str)
    fy1_closing_wdv = float(it_line1["closing_wdv"])

    # 2. Run FY2
    run2_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy2_id, "notes": "FY2 calculation"},
        headers=headers,
    )
    assert run2_res.status_code == 201, run2_res.text
    run2_id = run2_res.json()["id"]

    it_lines2_res = await client.get(f"/api/v1/depreciation/runs/{run2_id}/it-lines", headers=headers)
    assert it_lines2_res.status_code == 200, it_lines2_res.text
    it_lines2 = it_lines2_res.json()
    it_line2 = next(l for l in it_lines2 if l["it_block_id"] == it_block_id_str)
    fy2_opening_wdv = float(it_line2["opening_wdv"])

    assert fy2_opening_wdv == fy1_closing_wdv, (
        f"FY2 opening_wdv ({fy2_opening_wdv}) does not match FY1 closing_wdv ({fy1_closing_wdv})"
    )
