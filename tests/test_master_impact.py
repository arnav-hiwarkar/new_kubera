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
