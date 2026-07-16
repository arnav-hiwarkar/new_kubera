"""Lightweight fixed-window rate limiting backed by Redis.

Used to throttle the unauthenticated activation and login endpoints. Keyed by
client IP + a caller-supplied identifier (e.g. the submitted email). Fails OPEN
if Redis is unavailable — throttling must never take down auth.
"""
import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.config import get_settings

_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            get_settings().REDIS_URL, decode_responses=True
        )
    return _client


def _client_ip(request: Request) -> str:
    # Honor a proxy-set forwarded header when present (app runs behind Caddy).
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    request: Request,
    scope: str,
    identifier: str,
    *,
    limit: int,
    window_seconds: int,
) -> None:
    """Increment the counter for (scope, ip, identifier); raise 429 past `limit`."""
    if not get_settings().RATE_LIMIT_ENABLED:
        return

    ip = _client_ip(request)
    key = f"rl:{scope}:{ip}:{identifier.strip().lower()}"
    try:
        r = _redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, window_seconds)
    except Exception:
        # Redis unreachable — fail open.
        return

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )
