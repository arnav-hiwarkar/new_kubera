import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from app.config import get_settings
from app.models.base import Base
from app.database import get_db
from app.main import app

# Import all models so metadata is populated
from app.models.company import Company, CompanyKey, CompanyUser  # noqa
from app.models.auditor import Auditor  # noqa
from app.models.activity_log import ActivityLog  # noqa
from app.models.notification import Notification  # noqa

settings = get_settings()

# Use a separate test database (same server, different name)
_parts = settings.DATABASE_URL.rsplit("/", 1)
TEST_DB_URL = _parts[0] + "/kubera_test"

from sqlalchemy.pool import NullPool

engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables in test DB once per session."""
    from sqlalchemy.ext.asyncio import create_async_engine as cae

    admin_url = settings.DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin_engine = cae(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname='kubera_test'")
        )
        if not result.scalar():
            await conn.execute(text("CREATE DATABASE kubera_test"))
    await admin_engine.dispose()

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables():
    """Truncate all tables + reset rate-limit counters between tests."""
    yield
    async with engine.begin() as conn:
        # Truncate all tables in one statement to avoid FK issues
        table_names = [t.name for t in reversed(Base.metadata.sorted_tables)]
        if table_names:
            await conn.execute(text(f"TRUNCATE {', '.join(table_names)} CASCADE"))
    # Reset rate-limit counters so per-test attempt counts never accumulate
    # across tests (best-effort — the limiter fails open if Redis is absent).
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        keys = await r.keys("rl:*")
        if keys:
            await r.delete(*keys)
        await r.aclose()
    except Exception:
        pass


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


# === Helpers ===

INTERNAL_API_KEY = settings.INTERNAL_API_KEY


async def init_company(client: AsyncClient, name: str = "TestCo", email: str = "admin@testco.com") -> dict:
    """Operator-side: initialize a company shell + pending admin. Returns the
    init response JSON (includes the one-shot activation_key)."""
    resp = await client.post(
        "/api/v1/auth/companies",
        json={"name": name, "admin_email": email},
        headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
    )
    assert resp.status_code == 201, f"Failed to init company: {resp.text}"
    return resp.json()


async def activate_company(
    client: AsyncClient,
    email: str,
    activation_key: str,
    password: str = "testpass123",
    full_name: str = "Test Admin",
) -> None:
    """Admin-side: claim the pending account by setting a password."""
    resp = await client.post(
        "/api/v1/auth/company/activate",
        json={
            "email": email,
            "activation_key": activation_key,
            "password": password,
            "full_name": full_name,
        },
    )
    assert resp.status_code == 204, f"Failed to activate: {resp.text}"


async def create_test_company(
    client: AsyncClient,
    name: str = "TestCo",
    email: str = "admin@testco.com",
    password: str = "testpass123",
    full_name: str = "Test Admin",
) -> dict:
    """Init + activate a company so the admin can log in. Returns the init
    response JSON (company + admin + activation_key)."""
    data = await init_company(client, name=name, email=email)
    await activate_company(
        client, email=email, activation_key=data["activation_key"],
        password=password, full_name=full_name,
    )
    return data


async def get_company_token(client: AsyncClient, email: str = "admin@testco.com", password: str = "testpass123") -> str:
    """Login as company user, return access token."""
    resp = await client.post(
        "/api/v1/auth/company/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Failed to login: {resp.text}"
    return resp.json()["access_token"]


async def create_test_auditor(client: AsyncClient, email: str = "auditor@test.com", password: str = "testpass123", name: str = "Test Auditor") -> dict:
    """Register an auditor, return response JSON."""
    resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={"email": email, "password": password, "name": name},
    )
    assert resp.status_code == 201, f"Failed to register auditor: {resp.text}"
    return resp.json()


async def get_auditor_token(client: AsyncClient, email: str = "auditor@test.com", password: str = "testpass123") -> str:
    """Login as auditor, return access token."""
    resp = await client.post(
        "/api/v1/auth/auditor/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Failed to login auditor: {resp.text}"
    return resp.json()["access_token"]
