"""Lightweight fixed-window rate limiting backed by Redis.

Throttles the unauthenticated auth endpoints on two axes:

  * `(ip, identifier)` — tight. Stops password guessing against one account.
  * `ip` alone — coarse, opt-in via `ip_limit`. Stops *spraying*: one password
    tried against many accounts. Rotating the submitted email gives an attacker
    a fresh `(ip, identifier)` bucket every request, so the tight counter alone
    is no defence against it (KUB-003).

Fails OPEN if Redis is unavailable — throttling must never take down auth — but
loudly, at ERROR with a traceback, because a Redis outage silently removes every
brute-force protection here. `gateway/limits.conf` is the backstop that keeps
working when this one is blind.
"""
import logging

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            get_settings().REDIS_URL, decode_responses=True
        )
    return _client


def _client_ip(request: Request) -> str:
    # Honor a proxy-set forwarded header when present (app runs behind Caddy,
    # which SETS rather than appends it — see the Caddyfile).
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _bump(r: aioredis.Redis, key: str, window_seconds: int) -> int:
    """Increment a fixed-window counter, setting its TTL on first use."""
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window_seconds)
    return count


async def _retry_after(r: aioredis.Redis, key: str, window_seconds: int) -> int:
    """Seconds until the window resets, as a positive integer.

    `TTL` returns -1 (key has no expiry) or -2 (key already gone) in races we
    cannot rule out, and a `Retry-After: 0` would render as "try again in 0
    minutes". Fall back to the full window, which is never an under-estimate.
    """
    ttl = await r.ttl(key)
    return ttl if ttl > 0 else window_seconds


async def enforce_rate_limit(
    request: Request,
    scope: str,
    identifier: str,
    *,
    limit: int,
    window_seconds: int,
    ip_limit: int | None = None,
    ip_window: int | None = None,
) -> None:
    """Count this attempt against `(ip, identifier)` and, if `ip_limit` is set,
    against `ip` alone. Raise 429 with `Retry-After` once either is exceeded."""
    if not get_settings().RATE_LIMIT_ENABLED:
        return

    ip = _client_ip(request)
    ip_window = ip_window or window_seconds
    # `id:` / `ip:` keep the two namespaces from colliding. Without a
    # discriminator, `rl:{scope}:{ip}:{identifier}` and `rl:{scope}:ip:{ip}`
    # overlap when `ip` is the literal string "ip", which is reachable by anyone
    # who can set X-Forwarded-For — and would let an attacker exhaust another
    # client's IP bucket by submitting that client's address as the email.
    id_key = f"rl:{scope}:id:{ip}:{identifier.strip().lower()}"
    ip_key = f"rl:{scope}:ip:{ip}"

    # Every Redis call lives inside this block. Deciding to reject is separate
    # from raising so that a store that dies mid-check (e.g. on the TTL lookup)
    # still fails open rather than surfacing a 500 from the auth endpoint.
    retry_after: int | None = None
    try:
        r = _redis()

        if await _bump(r, id_key, window_seconds) > limit:
            retry_after = await _retry_after(r, id_key, window_seconds)

        if ip_limit is not None:
            # Bump unconditionally, even when the tight counter already
            # rejected: an attacker must not be able to keep the coarse counter
            # at zero by parking on one identifier.
            if await _bump(r, ip_key, ip_window) > ip_limit and retry_after is None:
                retry_after = await _retry_after(r, ip_key, ip_window)
    except Exception:
        logger.error(
            "rate limit store unavailable; failing open for scope=%s",
            scope,
            exc_info=True,
        )
        return

    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
