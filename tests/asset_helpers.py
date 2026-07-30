"""Shared helpers for the fixed-asset register tests.

`clean_tables` in conftest truncates every table after each test, which also wipes
the globally-seeded reference rows (asset categories / IT blocks) that the
migration installs in production. Tests that need them re-seed per test.
"""
from httpx import AsyncClient

from tests.conftest import TestSessionLocal, create_test_company, get_company_token


async def seed_masters() -> None:
    """Install the global (company_id IS NULL) Schedule II + Appendix I rows."""
    from app.services.asset_seed import seed_global_asset_reference_data

    async with TestSessionLocal() as session:
        await seed_global_asset_reference_data(session)
        await session.commit()


async def set_company_gstin(email: str, gstin: str) -> None:
    """Set the GSTIN on the company owning `email`, so place-of-supply resolution
    has a home state. PUT /company/profile wants a whole profile; this is narrower."""
    from sqlalchemy import func, select, update

    from app.models.company import Company, CompanyUser

    async with TestSessionLocal() as session:
        company_id = (
            await session.execute(
                select(CompanyUser.company_id).where(func.lower(CompanyUser.email) == email.lower())
            )
        ).scalar_one()
        await session.execute(
            update(Company).where(Company.id == company_id).values(gstin=gstin)
        )
        await session.commit()


async def admin_headers(client: AsyncClient, email: str) -> dict:
    """Create + activate a company and return that admin's auth headers."""
    await create_test_company(client, email=email, password="pass1234")
    token = await get_company_token(client, email=email, password="pass1234")
    return {"Authorization": f"Bearer {token}"}


async def make_user(client: AsyncClient, admin_h: dict, email: str, role: str = "employee") -> dict:
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": "pass1234",
            "full_name": email.split("@")[0],
            "role": role,
            # Asset endpoints check module access server-side, so grant it.
            "accessible_modules": ["assets"],
        },
        headers=admin_h,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def user_headers(client: AsyncClient, email: str) -> dict:
    token = await get_company_token(client, email=email, password="pass1234")
    return {"Authorization": f"Bearer {token}"}
