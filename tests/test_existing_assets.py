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
