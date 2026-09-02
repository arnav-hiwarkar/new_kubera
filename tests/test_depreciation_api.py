"""Integration tests for Depreciation Runs and Endpoints."""
from datetime import date
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.assets import Asset, AssetLifecycleStatus, AssetOperationalStatus
from app.models.company import CompanyUser
from app.models.depreciation import DepreciationRun
from tests.asset_helpers import admin_headers
from tests.conftest import TestSessionLocal


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
async def test_cannot_write_in_closed_financial_year(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="closed_fy@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    # 1. Close the financial year
    close_res = await client.post(f"/api/v1/financial-years/{fy_id}/close", headers=headers)
    assert close_res.status_code == 200

    # 2. Try to create a depreciation run in closed FY -> 409
    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Should fail"},
        headers=headers,
    )
    assert run_res.status_code == 409
    assert "closed" in run_res.json()["detail"].lower()

    # 3. Reopen FY to create a run, then close it again to test finalize/delete/reopen
    await client.post(f"/api/v1/financial-years/{fy_id}/reopen", json={"reason": "reopening for test"}, headers=headers)
    
    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Draft run"},
        headers=headers,
    )
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]

    # Close FY again
    await client.post(f"/api/v1/financial-years/{fy_id}/close", headers=headers)

    # 4. Try to finalize draft run while FY is closed -> 409
    fin_res = await client.post(f"/api/v1/depreciation/runs/{run_id}/finalize", headers=headers)
    assert fin_res.status_code == 409
    assert "closed" in fin_res.json()["detail"].lower()

    # 5. Try to delete draft run while FY is closed -> 409
    del_res = await client.delete(f"/api/v1/depreciation/runs/{run_id}", headers=headers)
    assert del_res.status_code == 409
    assert "closed" in del_res.json()["detail"].lower()

    # 6. Reopen FY, finalize run, close FY again
    await client.post(f"/api/v1/financial-years/{fy_id}/reopen", json={"reason": "reopening to finalize"}, headers=headers)
    fin_ok = await client.post(f"/api/v1/depreciation/runs/{run_id}/finalize", headers=headers)
    assert fin_ok.status_code == 200

    await client.post(f"/api/v1/financial-years/{fy_id}/close", headers=headers)

    # 7. Try to reopen finalized run while FY is closed -> 409
    reopen_closed = await client.post(
        f"/api/v1/depreciation/runs/{run_id}/reopen",
        json={"reason": "reopening run in closed year"},
        headers=headers,
    )
    assert reopen_closed.status_code == 409
    assert "closed" in reopen_closed.json()["detail"].lower()


@pytest.mark.asyncio
async def test_employee_cannot_finalize_depreciation_run(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_finalize_admin@testco.com")
    admin_headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    # Create draft run as admin
    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Draft to finalize"},
        headers=admin_headers,
    )
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]

    # Create employee with assets module
    emp_res = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "dep_emp_assets@testco.com",
            "password": "Valid1!Pass",
            "full_name": "Assets Employee",
            "role": "employee",
            "accessible_modules": ["assets"],
        },
    )
    assert emp_res.status_code == 201

    login_res = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "dep_emp_assets@testco.com", "password": "Valid1!Pass"},
    )
    assert login_res.status_code == 200
    emp_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Employee can see runs
    list_res = await client.get("/api/v1/depreciation/runs", headers=emp_headers)
    assert list_res.status_code == 200

    # Employee cannot finalize run -> 403
    fin_res = await client.post(f"/api/v1/depreciation/runs/{run_id}/finalize", headers=emp_headers)
    assert fin_res.status_code == 403


@pytest.mark.asyncio
async def test_finalize_depreciation_run_creates_audit_log(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_fin_log@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Finalize log test"},
        headers=headers,
    )
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]

    fin_res = await client.post(f"/api/v1/depreciation/runs/{run_id}/finalize", headers=headers)
    assert fin_res.status_code == 200

    log_res = await client.get(
        "/api/v1/activity-log",
        params={"entity_type": "depreciation_run", "entity_id": run_id},
        headers=headers,
    )
    assert log_res.status_code == 200
    logs = log_res.json()
    fin_log = next((l for l in logs if l["action"] == "depreciation.run.finalized"), None)
    assert fin_log is not None
    assert fin_log["entity_id"] == run_id


@pytest.mark.asyncio
async def test_employee_without_assets_module_cannot_access_depreciation(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_no_assets_admin@testco.com")
    admin_headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    # Create employee with NO assets module
    emp_res = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "dep_no_assets@testco.com",
            "password": "Valid1!Pass",
            "full_name": "No Assets User",
            "role": "employee",
            "accessible_modules": ["docvault"],
        },
    )
    assert emp_res.status_code == 201

    login_res = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "dep_no_assets@testco.com", "password": "Valid1!Pass"},
    )
    assert login_res.status_code == 200
    emp_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Blocked on list runs
    r1 = await client.get("/api/v1/depreciation/runs", headers=emp_headers)
    assert r1.status_code == 403

    # Blocked on create run
    r2 = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Fail"},
        headers=emp_headers,
    )
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_reopen_depreciation_run_whitespace_reason_rejected(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_reopen_spaces@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Draft to finalize then reopen"},
        headers=headers,
    )
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]

    fin_res = await client.post(f"/api/v1/depreciation/runs/{run_id}/finalize", headers=headers)
    assert fin_res.status_code == 200

    # Attempt to reopen with whitespace-only reason -> 422
    reopen_spaces = await client.post(
        f"/api/v1/depreciation/runs/{run_id}/reopen",
        json={"reason": "   "},
        headers=headers,
    )
    assert reopen_spaces.status_code == 422


@pytest.mark.asyncio
async def test_delete_depreciation_run_creates_audit_log(client: AsyncClient):
    ctx = await setup_depreciation_environment(client, email="dep_del_log@testco.com")
    headers = ctx["headers"]
    fy_id = ctx["fy_id"]

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Draft to delete"},
        headers=headers,
    )
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]

    del_res = await client.delete(f"/api/v1/depreciation/runs/{run_id}", headers=headers)
    assert del_res.status_code == 204

    log_res = await client.get(
        "/api/v1/activity-log",
        params={"entity_type": "depreciation_run", "entity_id": run_id},
        headers=headers,
    )
    assert log_res.status_code == 200
    logs = log_res.json()
    del_log = next((l for l in logs if l["action"] == "depreciation.run.deleted"), None)
    assert del_log is not None
    assert del_log["entity_id"] == run_id


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
    email = "three_year_slm@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

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

        asset = Asset(
            company_id=user.company_id,
            asset_name="Industrial Generator",
            asset_code="GEN-001",
            category_id=uuid.UUID(cat_id),
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
    email = "it_carry_forward@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    blocks = (await client.get("/api/v1/asset-masters/it-blocks", headers=headers)).json()
    block_id = next(b["id"] for b in blocks if b["code"] == "PM-15")
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

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

        asset = Asset(
            company_id=user.company_id,
            asset_name="Core Switch",
            asset_code="NET-001",
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
    it_line1 = next(l for l in it_lines1 if l["it_block_id"] == block_id)
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
    it_line2 = next(l for l in it_lines2 if l["it_block_id"] == block_id)
    fy2_opening_wdv = float(it_line2["opening_wdv"])

    assert fy2_opening_wdv == fy1_closing_wdv, (
        f"FY2 opening_wdv ({fy2_opening_wdv}) does not match FY1 closing_wdv ({fy1_closing_wdv})"
    )


@pytest.mark.asyncio
async def test_depreciation_residual_floor_stops_depreciation(client: AsyncClient):
    """Asset reaches its residual floor at Year 5 (NBV 5,000) and Year 6 charge is 0."""
    email = "res_floor@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    # Create 6 consecutive financial years
    fy_ids = []
    for y in range(2024, 2030):
        start_year = y
        end_year = y + 1
        fy_res = await client.post(
            "/api/v1/financial-years",
            json={
                "label": f"{start_year}-{str(end_year)[-2:]}",
                "start_date": f"{start_year}-04-01",
                "end_date": f"{end_year}-03-31",
            },
            headers=headers,
        )
        assert fy_res.status_code == 201, fy_res.text
        fy_ids.append(fy_res.json()["id"])

    # Create 100k SLM asset with 60m life and 5% residual
    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        asset = Asset(
            company_id=user.company_id,
            asset_name="Turbine Generator",
            asset_code="TURB-001",
            category_id=uuid.UUID(cat_id),
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

    # Run and finalize Years 1 through 6
    last_line = None
    for idx, fy_id in enumerate(fy_ids, start=1):
        run_res = await client.post(
            "/api/v1/depreciation/runs",
            json={"financial_year_id": fy_id, "notes": f"Year {idx} calculation"},
            headers=headers,
        )
        assert run_res.status_code == 201, run_res.text
        run_id = run_res.json()["id"]

        fin_res = await client.post(f"/api/v1/depreciation/runs/{run_id}/finalize", headers=headers)
        assert fin_res.status_code == 200, fin_res.text

        lines_res = await client.get(f"/api/v1/depreciation/runs/{run_id}/lines", headers=headers)
        assert lines_res.status_code == 200, lines_res.text
        last_line = lines_res.json()[0]

        if idx == 5:
            # Year 5 closing NBV is exactly 5000, closing accumulated dep is 95000
            assert float(last_line["closing_carrying_amount"]) == 5000.00
            assert float(last_line["closing_accumulated_depreciation"]) == 95000.00
            assert float(last_line["depreciation_for_year"]) == 19000.00
        elif idx == 6:
            # Year 6 charge is 0, closing NBV remains 5000
            assert float(last_line["depreciation_for_year"]) == 0.00
            assert float(last_line["closing_carrying_amount"]) == 5000.00
            assert float(last_line["closing_accumulated_depreciation"]) == 95000.00


@pytest.mark.asyncio
async def test_depreciation_null_useful_life_raises(client: AsyncClient):
    """An asset with NULL useful life raises an error on depreciation run."""
    email = "null_life@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy_res.status_code == 201, fy_res.text
    fy_id = fy_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        asset = Asset(
            company_id=user.company_id,
            asset_name="Invalid Life Machine",
            asset_code="INV-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=None,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
        )
        session.add(asset)
        await session.commit()

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Null life test run"},
        headers=headers,
    )
    assert run_res.status_code == 422, f"Expected 422 for null useful life, got {run_res.status_code}: {run_res.text}"
    assert "useful life" in run_res.text.lower()


@pytest.mark.asyncio
async def test_depreciation_wdv_zero_residual_raises_422(client: AsyncClient):
    """WDV depreciation with 0% residual raises 422 Unprocessable Entity."""
    email = "wdv_zero_res@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy_res.status_code == 201, fy_res.text
    fy_id = fy_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        asset = Asset(
            company_id=user.company_id,
            asset_name="WDV Zero Res Machine",
            asset_code="WDV-ZRES-01",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("0.00"),
            residual_value=Decimal("0.00"),
            dep_method="wdv",
            original_cost=Decimal("100000.00"),
        )
        session.add(asset)
        await session.commit()

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "WDV Zero Res Run"},
        headers=headers,
    )
    assert run_res.status_code == 422, f"Expected 422 for WDV zero residual, got {run_res.status_code}: {run_res.text}"


@pytest.mark.asyncio
async def test_depreciation_pre_cutover_missing_wdv_raises_422(client: AsyncClient):
    """Pre-cutover asset without opening WDV raises 422 Unprocessable Entity."""
    email = "pre_cutover_err@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    blocks = (await client.get("/api/v1/asset-masters/it-blocks", headers=headers)).json()
    block_id = next(b["id"] for b in blocks if b["code"] == "PM-15")
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy_res.status_code == 201, fy_res.text
    fy_id = fy_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        asset = Asset(
            company_id=user.company_id,
            asset_name="Cutover Machine Without WDV",
            asset_code="CUT-001",
            category_id=uuid.UUID(cat_id),
            it_block_id=uuid.UUID(block_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2023, 4, 1),
            available_for_use_date=date(2023, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
            is_pre_cutover=True,
            opening_wdv=None,
            opening_it_wdv=None,
        )
        session.add(asset)
        await session.commit()

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Pre cutover error run"},
        headers=headers,
    )
    assert run_res.status_code == 422, f"Expected 422 for pre-cutover without WDV, got {run_res.status_code}: {run_res.text}"


@pytest.mark.asyncio
async def test_income_tax_block_will_not_borrow_the_book_wdv(client: AsyncClient):
    """A missing tax WDV must fail, not fall back to the books figure.

    Book and tax written-down values essentially never agree in India — different
    rates, block-wise rather than asset-wise, additional depreciation. Substituting
    one for the other produced a wrong block opening base, and therefore a wrong
    deduction, with nothing on the report to say so.
    """
    email = "it_no_borrow@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    blocks = (await client.get("/api/v1/asset-masters/it-blocks", headers=headers)).json()
    block_id = next(b["id"] for b in blocks if b["code"] == "PM-15")
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy_res.status_code == 201, fy_res.text
    fy_id = fy_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        session.add(
            Asset(
                company_id=user.company_id,
                asset_name="Books WDV Only",
                asset_code="BWO-001",
                category_id=uuid.UUID(cat_id),
                it_block_id=uuid.UUID(block_id),
                lifecycle_status=AssetLifecycleStatus.capitalized,
                operational_status=AssetOperationalStatus.in_use,
                capitalization_date=date(2023, 4, 1),
                available_for_use_date=date(2023, 4, 1),
                it_put_to_use_date=date(2023, 4, 1),
                useful_life_months=60,
                residual_pct=Decimal("5.00"),
                dep_method="slm",
                original_cost=Decimal("100000.00"),
                is_pre_cutover=True,
                opening_accumulated_depreciation=Decimal("19000.00"),
                opening_wdv=Decimal("81000.00"),   # books figure present
                opening_it_wdv=None,               # tax figure absent
            )
        )
        await session.commit()

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id},
        headers=headers,
    )
    assert run_res.status_code == 422, (
        f"Expected 422 rather than silently using the book WDV, got "
        f"{run_res.status_code}: {run_res.text}"
    )
    assert "Opening WDV (tax)" in run_res.text or "opening Income Tax WDV" in run_res.text


@pytest.mark.asyncio
async def test_pre_cutover_run_uses_the_entered_opening_wdv(client: AsyncClient):
    """End to end: the WDV entered on the form is what the asset depreciates from.

    The field was required by validation and then discarded — the engine derived the
    carrying amount from cost instead. Here the asset was impaired, so the two
    deliberately disagree: cost 100,000 less accumulated 40,000 would give 60,000,
    but the stated carrying amount is 50,000.
    """
    email = "cutover_wdv_used@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    blocks = (await client.get("/api/v1/asset-masters/it-blocks", headers=headers)).json()
    block_id = next(b["id"] for b in blocks if b["code"] == "PM-15")
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy_res.status_code == 201, fy_res.text
    fy_id = fy_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        session.add(
            Asset(
                company_id=user.company_id,
                asset_name="Impaired Press",
                asset_code="IMP-001",
                category_id=uuid.UUID(cat_id),
                it_block_id=uuid.UUID(block_id),
                lifecycle_status=AssetLifecycleStatus.capitalized,
                operational_status=AssetOperationalStatus.in_use,
                capitalization_date=date(2021, 4, 1),
                available_for_use_date=date(2021, 4, 1),
                it_put_to_use_date=date(2021, 4, 1),
                useful_life_months=60,
                residual_pct=Decimal("5.00"),
                dep_method="wdv",
                original_cost=Decimal("100000.00"),
                is_pre_cutover=True,
                opening_accumulated_depreciation=Decimal("40000.00"),
                opening_wdv=Decimal("50000.00"),
                opening_it_wdv=Decimal("48000.00"),
            )
        )
        await session.commit()

    run_res = await client.post(
        "/api/v1/depreciation/runs", json={"financial_year_id": fy_id}, headers=headers
    )
    assert run_res.status_code == 201, run_res.text

    lines = await client.get(
        f"/api/v1/depreciation/runs/{run_res.json()['id']}/lines", headers=headers
    )
    assert lines.status_code == 200, lines.text
    line = lines.json()[0]

    assert float(line["opening_carrying_amount"]) == 50000.00, (
        "the entered opening WDV must be the carrying amount, not cost less accumulated"
    )
    # 50,000 x 0.4507 = 22,535.00. Deriving from cost would have charged 27,042.00.
    assert float(line["depreciation_for_year"]) == 22535.00
    assert float(line["closing_carrying_amount"]) == 27465.00



@pytest.mark.asyncio
async def test_depreciation_zero_residual_pct(client: AsyncClient):
    """Asset with 0% residual depreciates to zero rather than assuming 5%."""
    email = "zero_res@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy_res.status_code == 201, fy_res.text
    fy_id = fy_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        asset = Asset(
            company_id=user.company_id,
            asset_name="Zero Residual Asset",
            asset_code="ZRES-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("0.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
        )
        session.add(asset)
        await session.commit()

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "Zero residual test run"},
        headers=headers,
    )
    assert run_res.status_code == 201, run_res.text
    run_id = run_res.json()["id"]

    lines_res = await client.get(f"/api/v1/depreciation/runs/{run_id}/lines", headers=headers)
    assert lines_res.status_code == 200, lines_res.text
    line = lines_res.json()[0]
    # 100,000 / 5 = 20,000.00
    assert float(line["residual_value"]) == 0.00
    assert float(line["depreciation_for_year"]) == 20000.00
    assert float(line["closing_carrying_amount"]) == 80000.00


@pytest.mark.asyncio
async def test_depreciation_wdv_routing(client: AsyncClient):
    """WDV asset routes properly to WDV calculation branch."""
    email = "wdv_route@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy_res.status_code == 201, fy_res.text
    fy_id = fy_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        asset = Asset(
            company_id=user.company_id,
            asset_name="WDV Plant Equipment",
            asset_code="WDV-001",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 4, 1),
            available_for_use_date=date(2024, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="wdv",
            original_cost=Decimal("100000.00"),
        )
        session.add(asset)
        await session.commit()

    run_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "WDV route test run"},
        headers=headers,
    )
    assert run_res.status_code == 201, run_res.text
    run_id = run_res.json()["id"]

    lines_res = await client.get(f"/api/v1/depreciation/runs/{run_id}/lines", headers=headers)
    assert lines_res.status_code == 200, lines_res.text
    line = lines_res.json()[0]
    assert line["method"] == "WDV"
    assert float(line["depreciation_for_year"]) == 45070.00
    assert float(line["effective_rate_pct"]) == 45.07


@pytest.mark.asyncio
async def test_multiple_draft_runs_prior_fy_returns_409(client: AsyncClient):
    """B4: Multiple draft runs in prior FY must return 409 Conflict when running next FY, not 500 MultipleResultsFound."""
    email = "admin_multidraft@testco.com"
    headers = await admin_headers(client, email)

    # 1. Create FY1 and FY2
    fy1_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2023-24", "start_date": "2023-04-01", "end_date": "2024-03-31"},
        headers=headers,
    )
    assert fy1_res.status_code == 201, fy1_res.text
    fy1_id = fy1_res.json()["id"]

    fy2_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy2_res.status_code == 201, fy2_res.text
    fy2_id = fy2_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        # Insert 2 draft runs for FY1 directly
        run1 = DepreciationRun(
            company_id=user.company_id,
            financial_year_id=fy1_id,
            status="draft",
            notes="Draft run 1",
        )
        run2 = DepreciationRun(
            company_id=user.company_id,
            financial_year_id=fy1_id,
            status="draft",
            notes="Draft run 2",
        )
        session.add_all([run1, run2])
        await session.commit()

    # 2. Attempt a run for FY2 -> should raise 409, not 500
    run_fy2_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy2_id, "notes": "FY2 run attempt"},
        headers=headers,
    )
    assert run_fy2_res.status_code == 409, f"Expected 409, got {run_fy2_res.status_code}: {run_fy2_res.text}"


@pytest.mark.asyncio
async def test_depreciation_run_finalized_uniqueness_rejected(client: AsyncClient):
    """H1 / F2: Two finalized runs for the same (company_id, financial_year_id) are rejected with 409."""
    email = "admin_uniq_run@testco.com"
    headers = await admin_headers(client, email)

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    assert fy_res.status_code == 201
    fy_id = fy_res.json()["id"]

    # Create and finalize first run
    run1_res = await client.post(
        "/api/v1/depreciation/runs",
        json={"financial_year_id": fy_id, "notes": "First run"},
        headers=headers,
    )
    assert run1_res.status_code == 201
    run1_id = run1_res.json()["id"]

    fin1_res = await client.post(f"/api/v1/depreciation/runs/{run1_id}/finalize", headers=headers)
    assert fin1_res.status_code == 200

    # Create second run directly or via DB
    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        run2 = DepreciationRun(
            company_id=user.company_id,
            financial_year_id=fy_id,
            status="draft",
            notes="Second run",
        )
        session.add(run2)
        await session.commit()
        await session.refresh(run2)
        run2_id = run2.id

    # Attempt to finalize second run -> should return 409 Conflict
    fin2_res = await client.post(f"/api/v1/depreciation/runs/{run2_id}/finalize", headers=headers)
    assert fin2_res.status_code == 409, f"Expected 409, got {fin2_res.status_code}: {fin2_res.text}"


@pytest.mark.asyncio
async def test_prior_fy_disposal_in_live_block_still_depreciates(client: AsyncClient):
    """H1 / F7: A block holding 1 asset disposed 2 years ago and 1 live asset still depreciates normally and is NOT flagged all_assets_disposed."""
    email = "live_block_disp@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    blocks = (await client.get("/api/v1/asset-masters/it-blocks", headers=headers)).json()
    block_id = next(b["id"] for b in blocks if b["code"] == "PM-15")
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    # Create 3 FYs: 2022-23, 2023-24, 2024-25
    fy1_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2022-23", "start_date": "2022-04-01", "end_date": "2023-03-31"},
        headers=headers,
    )
    fy1_id = fy1_res.json()["id"]

    fy2_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2023-24", "start_date": "2023-04-01", "end_date": "2024-03-31"},
        headers=headers,
    )
    fy2_id = fy2_res.json()["id"]

    fy3_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    fy3_id = fy3_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()

        # Asset 1: Disposed in FY 2022-23
        a1 = Asset(
            company_id=user.company_id,
            asset_name="Old Server",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.disposed,
            operational_status=AssetOperationalStatus.in_storage,
            capitalization_date=date(2022, 4, 1),
            useful_life_months=36,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("50000.00"),
            it_block_id=uuid.UUID(block_id),
            it_dep_rate=Decimal("15.00"),
            it_put_to_use_date=date(2022, 4, 1),
            disposal_date=date(2022, 10, 1),
            disposal_type="sale",
            sale_proceeds=Decimal("20000.00"),
            disposed_by=user.id,
        )
        # Asset 2: Live asset capitalized in FY 2022-23
        a2 = Asset(
            company_id=user.company_id,
            asset_name="Live Server",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2022, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
            it_block_id=uuid.UUID(block_id),
            it_dep_rate=Decimal("15.00"),
            it_put_to_use_date=date(2022, 4, 1),
        )
        session.add_all([a1, a2])
        await session.commit()

    # Finalize FY1
    r1 = await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy1_id}, headers=headers)
    assert r1.status_code == 201
    await client.post(f"/api/v1/depreciation/runs/{r1.json()['id']}/finalize", headers=headers)

    # Finalize FY2
    r2 = await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy2_id}, headers=headers)
    assert r2.status_code == 201
    await client.post(f"/api/v1/depreciation/runs/{r2.json()['id']}/finalize", headers=headers)

    # Run FY3
    r3 = await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy3_id}, headers=headers)
    assert r3.status_code == 201
    r3_id = r3.json()["id"]

    it_lines_res = await client.get(f"/api/v1/depreciation/runs/{r3_id}/it-lines", headers=headers)
    assert it_lines_res.status_code == 200
    it_lines = it_lines_res.json()
    block_line = next(l for l in it_lines if l["it_block_id"] == block_id)

    # Must have depreciation > 0 and NOT all_assets_disposed / capital loss
    assert float(block_line["total_depreciation"]) > 0
    assert float(block_line["closing_wdv"]) > 0
    assert not block_line["has_stcl"]


@pytest.mark.asyncio
async def test_f9_gate_scenario_1_fy2_with_fy1_draft_returns_409(client: AsyncClient):
    """H1 / F9 scenario 1: FY2 with FY1 in draft -> returns 409."""
    email = "f9_sc1@testco.com"
    headers = await admin_headers(client, email)

    fy1_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2023-24", "start_date": "2023-04-01", "end_date": "2024-03-31"},
        headers=headers,
    )
    fy1_id = fy1_res.json()["id"]

    fy2_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    fy2_id = fy2_res.json()["id"]

    # Create draft run in FY1
    r1 = await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy1_id}, headers=headers)
    assert r1.status_code == 201

    # Attempt run in FY2 -> 409
    r2 = await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy2_id}, headers=headers)
    assert r2.status_code == 409
    assert "must be finalized" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_f9_gate_scenario_2_fy1_finalized_then_fy2_succeeds(client: AsyncClient):
    """H1 / F9 scenario 2: FY1 finalized, then FY2 -> succeeds and carries forward."""
    email = "f9_sc2@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    fy1_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2023-24", "start_date": "2023-04-01", "end_date": "2024-03-31"},
        headers=headers,
    )
    fy1_id = fy1_res.json()["id"]

    fy2_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    fy2_id = fy2_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        asset = Asset(
            company_id=user.company_id,
            asset_name="Office AC",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2023, 4, 1),
            useful_life_months=60,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("60000.00"),
        )
        session.add(asset)
        await session.commit()

    # Finalize FY1
    r1 = await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy1_id}, headers=headers)
    assert r1.status_code == 201
    fin1 = await client.post(f"/api/v1/depreciation/runs/{r1.json()['id']}/finalize", headers=headers)
    assert fin1.status_code == 200, fin1.text

    # Run FY2 -> succeeds (201)
    r2 = await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy2_id}, headers=headers)
    assert r2.status_code == 201

    # ...and actually carries forward. The docstring claimed this; nothing checked it.
    # 60000 cost, 5% residual (3000) => 57000 base over 60 months = 11400/yr.
    lines1 = await client.get(f"/api/v1/depreciation/runs/{r1.json()['id']}/lines", headers=headers)
    assert lines1.status_code == 200, lines1.text
    line1 = lines1.json()[0]
    assert float(line1["closing_accumulated_depreciation"]) == 11400.00

    lines2 = await client.get(f"/api/v1/depreciation/runs/{r2.json()['id']}/lines", headers=headers)
    assert lines2.status_code == 200, lines2.text
    line2 = lines2.json()[0]
    assert float(line2["opening_accumulated_depreciation"]) == float(
        line1["closing_accumulated_depreciation"]
    ), "FY2 must open where FY1 closed"
    assert float(line2["closing_accumulated_depreciation"]) == 22800.00


@pytest.mark.asyncio
async def test_f9_gate_scenario_3_first_ever_fy_runs_cleanly(client: AsyncClient):
    """H1 / F9 scenario 3: A company's first-ever FY, no prior year -> runs cleanly, not blocked."""
    email = "f9_sc3@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    fy_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    fy_id = fy_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        asset = Asset(
            company_id=user.company_id,
            asset_name="First Laptop",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2024, 6, 1),
            useful_life_months=36,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("75000.00"),
        )
        session.add(asset)
        await session.commit()

    # Run FY -> 201 created without errors
    r = await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy_id}, headers=headers)
    assert r.status_code == 201

    # A 201 alone would also be returned by a run that silently computed nothing.
    # Assert it actually depreciated, and opened at zero as a first year must.
    lines = await client.get(f"/api/v1/depreciation/runs/{r.json()['id']}/lines", headers=headers)
    assert lines.status_code == 200, lines.text
    assert len(lines.json()) == 1, "expected one asset line"
    line = lines.json()[0]
    assert float(line["opening_accumulated_depreciation"]) == 0.00
    assert float(line["depreciation_for_year"]) > 0


@pytest.mark.asyncio
async def test_f9_gate_scenario_4_pre_cutover_asset_runs_cleanly(client: AsyncClient):
    """H1 / F9 scenario 4: A pre-cutover asset with opening figures and no prior run -> runs cleanly."""
    email = "f9_sc4@testco.com"
    headers = await admin_headers(client, email)

    # Take ids from the API so they are guaranteed company-owned.
    cats = (await client.get("/api/v1/asset-masters/categories", headers=headers)).json()
    cat_id = next(c["id"] for c in cats if c["parent_id"] is not None)

    # Create prior FY and current FY, but NO prior run
    fy1_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2023-24", "start_date": "2023-04-01", "end_date": "2024-03-31"},
        headers=headers,
    )
    fy2_res = await client.post(
        "/api/v1/financial-years",
        json={"label": "2024-25", "start_date": "2024-04-01", "end_date": "2025-03-31"},
        headers=headers,
    )
    fy2_id = fy2_res.json()["id"]

    async with TestSessionLocal() as session:
        user = (await session.execute(select(CompanyUser).where(CompanyUser.email == email))).scalar_one()
        # Pre-cutover asset capitalized before fy2_start
        asset = Asset(
            company_id=user.company_id,
            asset_name="Pre-cutover Plant",
            category_id=uuid.UUID(cat_id),
            lifecycle_status=AssetLifecycleStatus.capitalized,
            operational_status=AssetOperationalStatus.in_use,
            capitalization_date=date(2022, 1, 1),
            is_pre_cutover=True,
            opening_accumulated_depreciation=Decimal("20000.00"),
            useful_life_months=120,
            residual_pct=Decimal("5.00"),
            dep_method="slm",
            original_cost=Decimal("100000.00"),
        )
        session.add(asset)
        await session.commit()

    # Running FY2 should succeed (201) because asset is pre-cutover
    r = await client.post("/api/v1/depreciation/runs", json={"financial_year_id": fy2_id}, headers=headers)
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"

    # The point of a pre-cutover asset is that its opening balance is *used* rather
    # than recomputed. A run that ignored it would also return 201, so check the
    # figure actually carried in.
    lines = await client.get(f"/api/v1/depreciation/runs/{r.json()['id']}/lines", headers=headers)
    assert lines.status_code == 200, lines.text
    line = lines.json()[0]
    assert float(line["opening_accumulated_depreciation"]) == 20000.00, (
        "pre-cutover opening accumulated depreciation was not honoured"
    )


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
    # setup_depreciation_environment already created this company's "2024-25";
    # the duplicate-label rule (409) forbids creating it twice.
    fy_new = ctx["fy_id"]

    # Runs chain oldest-first: the F9 gate refuses a later year while its
    # predecessor's run is still a draft, so finalize each as we go.
    r_old = (await client.post("/api/v1/depreciation/runs",
                               json={"financial_year_id": fy_old}, headers=headers)).json()["id"]
    assert (
        await client.post(f"/api/v1/depreciation/runs/{r_old}/finalize", headers=headers)
    ).status_code == 200
    r_new = (await client.post("/api/v1/depreciation/runs",
                               json={"financial_year_id": fy_new}, headers=headers)).json()["id"]
    assert (
        await client.post(f"/api/v1/depreciation/runs/{r_new}/finalize", headers=headers)
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




@pytest.mark.asyncio
async def test_line_response_carries_a_calc_trace(client: AsyncClient):
    """A computed run's lines explain themselves without a second request."""
    env = await setup_depreciation_environment(client, "admin_trace_line@testco.com")
    headers, fy_id = env["headers"], env["fy_id"]

    run = await client.post(
        "/api/v1/depreciation/runs", json={"financial_year_id": fy_id}, headers=headers
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]

    lines = await client.get(f"/api/v1/depreciation/runs/{run_id}/lines", headers=headers)
    assert lines.status_code == 200, lines.text
    line = lines.json()[0]

    trace = line["calc_trace"]
    assert trace is not None
    assert trace["is_projection"] is False
    assert trace["computed_at"] is not None
    assert "Schedule II" in trace["title"]

    keys = [s["key"] for s in trace["steps"]]
    assert "depreciable_base" in keys
    assert "depreciation_for_year" in keys

    # The invariant, end to end: what the drawer will show equals what the row shows.
    charge = next(s for s in trace["steps"] if s["key"] == "depreciation_for_year")
    assert charge["emphasis"] is True
    assert charge["result"] == f"{Decimal(line['depreciation_for_year']):,.2f}"


@pytest.mark.asyncio
async def test_it_line_response_carries_a_calc_trace(client: AsyncClient):
    env = await setup_depreciation_environment(client, "admin_trace_itline@testco.com")
    headers, fy_id = env["headers"], env["fy_id"]

    run = await client.post(
        "/api/v1/depreciation/runs", json={"financial_year_id": fy_id}, headers=headers
    )
    run_id = run.json()["id"]

    it_lines = await client.get(f"/api/v1/depreciation/runs/{run_id}/it-lines", headers=headers)
    assert it_lines.status_code == 200, it_lines.text
    # Only the asset's own block carries figures; find it by a non-zero pool.
    with_figures = [l for l in it_lines.json() if Decimal(l["balance_before_depreciation"]) > 0]
    assert with_figures, "expected at least one block with a balance"
    trace = with_figures[0]["calc_trace"]

    assert trace is not None
    assert "Income Tax" in trace["title"]
    keys = [s["key"] for s in trace["steps"]]
    assert "balance_before_depreciation" in keys
    assert "total_depreciation" in keys


@pytest.mark.asyncio
async def test_explain_returns_a_projection_before_any_run(client: AsyncClient):
    """The drawer is useful during data entry, not only after a run."""
    env = await setup_depreciation_environment(client, "admin_explain_pre@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": asset_id, "financial_year_id": fy_id},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()

    ca = body["companies_act"]
    assert ca["is_projection"] is True
    assert ca["computed_at"] is None
    keys = [s["key"] for s in ca["steps"]]
    assert "depreciable_base" in keys
    assert "depreciation_for_year" in keys

    # The asset in the fixture is in the PM-15 block, so the tax book is present too.
    assert body["income_tax"] is not None
    assert body["income_tax"]["is_projection"] is True
    it_keys = [s["key"] for s in body["income_tax"]["steps"]]
    assert "asset_contribution" in it_keys


@pytest.mark.asyncio
async def test_projection_matches_the_recorded_run(client: AsyncClient):
    """The strongest guarantee in the feature: same assembly, same engine, same steps."""
    env = await setup_depreciation_environment(client, "admin_explain_match@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    run = await client.post(
        "/api/v1/depreciation/runs", json={"financial_year_id": fy_id}, headers=headers
    )
    run_id = run.json()["id"]
    lines = await client.get(f"/api/v1/depreciation/runs/{run_id}/lines", headers=headers)
    recorded = next(l for l in lines.json() if l["asset_id"] == asset_id)["calc_trace"]

    projected = (
        await client.post(
            "/api/v1/depreciation/explain",
            json={"asset_id": asset_id, "financial_year_id": fy_id},
            headers=headers,
        )
    ).json()["companies_act"]

    # Everything except the projection markers must be identical.
    assert projected["title"] == recorded["title"]
    assert projected["basis"] == recorded["basis"]
    assert projected["steps"] == recorded["steps"]
    assert recorded["is_projection"] is False
    assert projected["is_projection"] is True


@pytest.mark.asyncio
async def test_explain_surfaces_the_engine_validation_message(client: AsyncClient):
    """Incomplete inputs are explained, not hidden behind a generic failure."""
    env = await setup_depreciation_environment(client, "admin_explain_422@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    # Strip the useful life the way an unfinished data-entry session would leave it.
    async with TestSessionLocal() as session:
        asset = await session.get(Asset, uuid.UUID(asset_id))
        asset.useful_life_months = None
        await session.commit()

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": asset_id, "financial_year_id": fy_id},
        headers=headers,
    )
    assert res.status_code == 422, res.text
    assert "useful life" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_explain_omits_the_tax_book_without_a_block(client: AsyncClient):
    env = await setup_depreciation_environment(client, "admin_explain_noblock@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    async with TestSessionLocal() as session:
        asset = await session.get(Asset, uuid.UUID(asset_id))
        asset.it_block_id = None
        await session.commit()

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": asset_id, "financial_year_id": fy_id},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["income_tax"] is None


@pytest.mark.asyncio
async def test_explain_with_draft_prior_year_run_returns_409(client: AsyncClient):
    """A prior year stuck in draft blocks projections exactly as it blocks runs."""
    env = await setup_depreciation_environment(client, "admin_explain_draft@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    fy_prior = (
        await client.post(
            "/api/v1/financial-years",
            json={"label": "2023-24", "start_date": "2023-04-01", "end_date": "2024-03-31"},
            headers=headers,
        )
    ).json()["id"]
    r = await client.post(
        "/api/v1/depreciation/runs", json={"financial_year_id": fy_prior}, headers=headers
    )
    assert r.status_code == 201

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": asset_id, "financial_year_id": fy_id},
        headers=headers,
    )
    assert res.status_code == 409, res.text
    assert "must be finalized" in res.json()["detail"]


@pytest.mark.asyncio
async def test_explain_with_unrun_prior_year_returns_409(client: AsyncClient):
    """Assets capitalized before the year need the prior run's opening balances."""
    env = await setup_depreciation_environment(client, "admin_explain_norun@testco.com")
    headers, fy_id, asset_id = env["headers"], env["fy_id"], env["asset_id"]

    await client.post(
        "/api/v1/financial-years",
        json={"label": "2023-24", "start_date": "2023-04-01", "end_date": "2024-03-31"},
        headers=headers,
    )

    # Move capitalization into the prior year so opening balances are required.
    async with TestSessionLocal() as session:
        asset = await session.get(Asset, uuid.UUID(asset_id))
        asset.capitalization_date = date(2023, 10, 1)
        asset.available_for_use_date = date(2023, 10, 1)
        await session.commit()

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": asset_id, "financial_year_id": fy_id},
        headers=headers,
    )
    assert res.status_code == 409, res.text
    assert "No depreciation run exists" in res.json()["detail"]


@pytest.mark.asyncio
async def test_explain_is_tenant_scoped(client: AsyncClient):
    """Another company's asset id must not resolve."""
    mine = await setup_depreciation_environment(client, "admin_explain_mine@testco.com")
    theirs = await setup_depreciation_environment(client, "admin_explain_theirs@testco.com")

    res = await client.post(
        "/api/v1/depreciation/explain",
        json={"asset_id": theirs["asset_id"], "financial_year_id": mine["fy_id"]},
        headers=mine["headers"],
    )
    assert res.status_code == 404, res.text
