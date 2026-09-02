import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import CompanyUser
from tests.conftest import create_test_company, get_company_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_user_writes_canonicalize_legacy_compliance_access(client: AsyncClient):
    await create_test_company(client, email="access-admin@a.com", password="Valid1!Pass")
    admin_headers = _headers(
        await get_company_token(client, email="access-admin@a.com", password="Valid1!Pass")
    )

    created = await client.post(
        "/api/v1/users",
        json={
            "email": "legacy-access@a.com",
            "password": "Valid1!Pass",
            "full_name": "Legacy Access",
            "role": "employee",
            "accessible_modules": [
                "dashboard",
                "compliance",
                "roc",
                "activity",
                "secretarial",
            ],
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["accessible_modules"] == [
        "dashboard",
        "roc",
        "secretarial",
        "activity",
    ]

    updated = await client.patch(
        f"/api/v1/users/{created.json()['id']}",
        json={
            "accessible_modules": [
                "secretarial",
                "compliance",
                "secretarial",
                "docvault",
            ]
        },
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["accessible_modules"] == [
        "secretarial",
        "roc",
        "docvault",
    ]


@pytest.mark.asyncio
async def test_split_compliance_access_migration_round_trip(
    client: AsyncClient, db: AsyncSession
):
    await create_test_company(client, email="migration-admin@a.com", password="Valid1!Pass")
    admin_headers = _headers(
        await get_company_token(client, email="migration-admin@a.com", password="Valid1!Pass")
    )

    cases = {
        "combined-plus@a.com": ["dashboard", "compliance", "activity"],
        "combined-only@a.com": ["compliance"],
        "neither@a.com": ["dashboard"],
        "canonical@a.com": ["roc", "secretarial", "roc"],
        "roc-only@a.com": ["roc"],
        "secretarial-only@a.com": ["secretarial"],
    }
    for email, modules in cases.items():
        response = await client.post(
            "/api/v1/users",
            json={
                "email": email,
                "password": "Valid1!Pass",
                "full_name": email,
                "role": "employee",
                # Write directly below so legacy and duplicate arrays reach the migration.
                "accessible_modules": [],
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        row = (
            await db.execute(select(CompanyUser).where(CompanyUser.id == response.json()["id"]))
        ).scalar_one()
        row.accessible_modules = modules
    await db.commit()

    migration_path = (
        Path(__file__).parents[1]
        / "alembic/versions/4f6a8b0c2d1e_split_compliance_module_access.py"
    )
    spec = importlib.util.spec_from_file_location("split_compliance_access_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def run_migration(sync_connection, direction: str):
        original_op = migration.op
        migration.op = Operations(MigrationContext.configure(sync_connection))
        try:
            getattr(migration, direction)()
        finally:
            migration.op = original_op

    connection = await db.connection()
    await connection.run_sync(run_migration, "upgrade")
    await db.commit()
    db.expire_all()

    upgraded = {
        row.email: row.accessible_modules
        for row in (
            await db.execute(select(CompanyUser).where(CompanyUser.email.in_(cases)))
        ).scalars()
    }
    assert upgraded["combined-plus@a.com"] == [
        "dashboard",
        "activity",
        "roc",
        "secretarial",
    ]
    assert upgraded["combined-only@a.com"] == ["roc", "secretarial"]
    assert upgraded["neither@a.com"] == ["dashboard"]
    assert upgraded["canonical@a.com"] == ["roc", "secretarial", "roc"]

    connection = await db.connection()
    await connection.run_sync(run_migration, "downgrade")
    await db.commit()
    db.expire_all()

    downgraded = {
        row.email: row.accessible_modules
        for row in (
            await db.execute(select(CompanyUser).where(CompanyUser.email.in_(cases)))
        ).scalars()
    }
    assert downgraded["combined-plus@a.com"] == ["dashboard", "activity", "compliance"]
    assert downgraded["combined-only@a.com"] == ["compliance"]
    assert downgraded["neither@a.com"] == ["dashboard"]
    assert downgraded["canonical@a.com"] == ["compliance"]
    assert downgraded["roc-only@a.com"] == ["compliance"]
    assert downgraded["secretarial-only@a.com"] == ["compliance"]
