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
