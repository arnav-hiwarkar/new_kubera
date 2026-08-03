"""Unauthenticated process health and internal dependency readiness checks."""

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.database import engine


router = APIRouter(tags=["health"])


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_redis() -> None:
    client = aioredis.from_url(get_settings().REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    finally:
        await client.aclose()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz():
    checks: dict[str, str] = {}
    for name, check in (("database", check_database), ("redis", check_redis)):
        try:
            await check()
        except Exception:
            checks[name] = "unavailable"
        else:
            checks[name] = "ok"

    ready = all(value == "ok" for value in checks.values())
    payload = {"status": "ready" if ready else "not_ready", "checks": checks}
    if ready:
        return payload
    return JSONResponse(status_code=503, content=payload)
