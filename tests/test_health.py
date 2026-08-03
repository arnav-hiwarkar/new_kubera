"""Contract tests for process health and dependency readiness."""

import pytest

from app.routers import health


@pytest.mark.asyncio
async def test_healthz_is_public_and_alive(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_reports_all_dependencies(client, monkeypatch):
    async def ok():
        return None

    monkeypatch.setattr(health, "check_database", ok)
    monkeypatch.setattr(health, "check_redis", ok)

    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }


@pytest.mark.asyncio
async def test_readyz_returns_503_when_database_is_unavailable(client, monkeypatch):
    async def fail():
        raise ConnectionError("database secret must not leak")

    async def ok():
        return None

    monkeypatch.setattr(health, "check_database", fail)
    monkeypatch.setattr(health, "check_redis", ok)

    response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable", "redis": "ok"},
    }


@pytest.mark.asyncio
async def test_readyz_returns_503_when_redis_is_unavailable(client, monkeypatch):
    async def fail():
        raise ConnectionError("redis secret must not leak")

    async def ok():
        return None

    monkeypatch.setattr(health, "check_database", ok)
    monkeypatch.setattr(health, "check_redis", fail)

    response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "redis": "unavailable"},
    }
