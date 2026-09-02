"""KUB-003 — anti-automation on the unauthenticated auth endpoints.

The counters live in Redis and `tests/conftest.py` flushes every `rl:*` key
after each test, so each test below starts with an empty budget. That flush is
also why these tests can assert on absolute counts.

Two things are being protected at once and the tests keep them apart:

  * the tight `(ip, email)` counter — password guessing against one account;
  * the coarse `ip` counter — the same password sprayed across many accounts,
    which rotates the email and so never touches the tight counter.

A limiter that rejects too much is an outage, so roughly half of what follows is
the other direction: that legitimate traffic under the limit is untouched, that
a second client is unaffected by the first, and that a dead Redis fails open.
"""
import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from httpx import AsyncClient

from app.config import get_settings
import app.rate_limit as rate_limit
from tests.conftest import create_test_auditor, init_company

settings = get_settings()

BAD_LOGIN = {"password": "not-the-password"}


def _ip(addr: str) -> dict[str, str]:
    """Present as a distinct client. `_client_ip` reads the first X-Forwarded-For
    entry, which Caddy pins to the real peer in production."""
    return {"X-Forwarded-For": addr}


def _email() -> str:
    return f"{uuid.uuid4().hex}@ratelimit.example.com"


# --------------------------------------------------------------------------
# The tight (ip, email) counter
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auditor_login_throttles_guessing_against_one_account(client: AsyncClient):
    """The KUB-003 headline: /auth/auditor/login had no limit at all."""
    email = _email()
    await create_test_auditor(client, email=email, password="correct-horse-battery")

    for attempt in range(settings.LOGIN_RATE_LIMIT):
        resp = await client.post(
            "/api/v1/auth/auditor/login", json={"email": email, **BAD_LOGIN}
        )
        assert resp.status_code == 401, f"attempt {attempt}: {resp.text}"

    resp = await client.post(
        "/api/v1/auth/auditor/login", json={"email": email, **BAD_LOGIN}
    )
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Too many attempts. Please try again later."


@pytest.mark.asyncio
async def test_lockout_survives_the_correct_password(client: AsyncClient):
    """Anti-test. Exhausting the budget must not leave a window where the right
    password still gets through — otherwise the limit only slows the attacker
    down until the moment they succeed."""
    email = _email()
    password = "correct-horse-battery"
    await create_test_auditor(client, email=email, password=password)

    for _ in range(settings.LOGIN_RATE_LIMIT):
        await client.post("/api/v1/auth/auditor/login", json={"email": email, **BAD_LOGIN})

    resp = await client.post(
        "/api/v1/auth/auditor/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_login_under_the_limit_is_untouched(client: AsyncClient):
    """A user who fumbles their password a few times and then gets it right must
    not be blocked."""
    email = _email()
    password = "correct-horse-battery"
    await create_test_auditor(client, email=email, password=password)

    for _ in range(settings.LOGIN_RATE_LIMIT - 1):
        resp = await client.post(
            "/api/v1/auth/auditor/login", json={"email": email, **BAD_LOGIN}
        )
        assert resp.status_code == 401

    resp = await client.post(
        "/api/v1/auth/auditor/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------
# The coarse per-IP counter — the part that was missing entirely
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_password_spraying_is_capped_per_ip(client: AsyncClient):
    """Every request uses a fresh email, so the (ip, email) counter never leaves
    1. Only the coarse counter can stop this."""
    for attempt in range(settings.LOGIN_IP_RATE_LIMIT):
        resp = await client.post(
            "/api/v1/auth/auditor/login", json={"email": _email(), **BAD_LOGIN}
        )
        assert resp.status_code == 401, f"attempt {attempt}: {resp.text}"

    resp = await client.post(
        "/api/v1/auth/auditor/login", json={"email": _email(), **BAD_LOGIN}
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_company_login_spraying_is_capped_per_ip(client: AsyncClient):
    for _ in range(settings.LOGIN_IP_RATE_LIMIT):
        resp = await client.post(
            "/api/v1/auth/company/login", json={"email": _email(), **BAD_LOGIN}
        )
        assert resp.status_code == 401

    resp = await client.post(
        "/api/v1/auth/company/login", json={"email": _email(), **BAD_LOGIN}
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_one_clients_lockout_does_not_reach_another(client: AsyncClient):
    """Anti-test for the shared-bucket failure mode. This is exactly the bug the
    gateway had: a limit keyed on something every visitor has in common lets one
    client lock out the whole world."""
    for _ in range(settings.LOGIN_IP_RATE_LIMIT + 1):
        await client.post(
            "/api/v1/auth/auditor/login",
            json={"email": _email(), **BAD_LOGIN},
            headers=_ip("198.51.100.7"),
        )

    resp = await client.post(
        "/api/v1/auth/auditor/login",
        json={"email": _email(), **BAD_LOGIN},
        headers=_ip("203.0.113.9"),
    )
    assert resp.status_code == 401, "an unrelated client inherited the lockout"


def _request(ip: str) -> Request:
    """A bare ASGI request carrying a forwarded-for header, for driving
    `enforce_rate_limit` without an endpoint's schema validation in the way."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"x-forwarded-for", ip.encode())],
            "client": ("127.0.0.1", 0),
        }
    )


@pytest.mark.asyncio
async def test_ip_budget_cannot_be_poisoned_through_the_identifier():
    """Anti-test for key-namespace collision, exercised against the limiter
    directly because `EmailStr` happens to reject the shape of identifier this
    needs. The two counters are `rl:{scope}:id:{ip}:{identifier}` and
    `rl:{scope}:ip:{ip}`; drop the `id:`/`ip:` discriminator and a caller who
    reports their address as "ip" and submits a victim's address as the
    identifier writes straight into the victim's coarse bucket. Not every call
    site takes an email — leads and the refresh endpoints pass other strings —
    so the namespaces have to be unambiguous rather than incidentally safe."""
    victim = "203.0.113.42"

    for _ in range(settings.LOGIN_IP_RATE_LIMIT + 5):
        try:
            await rate_limit.enforce_rate_limit(
                _request("ip"),
                "poison_probe",
                victim,
                limit=10_000,
                window_seconds=300,
                ip_limit=settings.LOGIN_IP_RATE_LIMIT,
                ip_window=300,
            )
        except HTTPException:
            pass  # the attacker's own bucket filling up is expected

    # The victim's first request of the window must still go through.
    await rate_limit.enforce_rate_limit(
        _request(victim),
        "poison_probe",
        "someone@ratelimit.example.com",
        limit=10,
        window_seconds=300,
        ip_limit=settings.LOGIN_IP_RATE_LIMIT,
        ip_window=300,
    )


@pytest.mark.asyncio
async def test_the_coarse_counter_still_advances_while_the_tight_one_rejects(
    client: AsyncClient,
):
    """Parking on one email must not be a way to keep the IP counter at zero: if
    429s stopped counting, an attacker could burn one account's budget for free
    and then start spraying with a full coarse budget."""
    email = _email()
    burned = settings.LOGIN_IP_RATE_LIMIT + 1
    for _ in range(burned):
        await client.post("/api/v1/auth/auditor/login", json={"email": email, **BAD_LOGIN})

    # Same IP, brand-new email: the tight counter is 1, so only the coarse one
    # can be responsible for this rejection.
    resp = await client.post(
        "/api/v1/auth/auditor/login", json={"email": _email(), **BAD_LOGIN}
    )
    assert resp.status_code == 429


# --------------------------------------------------------------------------
# Company activation — a one-shot key, not a password, but still guessable
# and still spannable across many stolen/guessed addresses from one IP
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_activation_is_capped_per_ip(client: AsyncClient):
    """The per-email counter (`ACTIVATE_RATE_LIMIT`) does nothing against someone
    trying one leaked key against a list of addresses — every attempt below uses
    a fresh, made-up email, so only the coarse IP counter can catch it."""
    for _ in range(settings.LOGIN_IP_RATE_LIMIT):
        resp = await client.post(
            "/api/v1/auth/company/activate",
            json={
                "email": _email(),
                "activation_key": "not-a-real-key",
                "password": "correct-horse-battery",
                "full_name": "Attacker",
            },
        )
        assert resp.status_code == 400, resp.text

    resp = await client.post(
        "/api/v1/auth/company/activate",
        json={
            "email": _email(),
            "activation_key": "not-a-real-key",
            "password": "correct-horse-battery",
            "full_name": "Attacker",
        },
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_a_real_activation_survives_unrelated_noise_on_the_same_ip(
    client: AsyncClient,
):
    """Anti-test: a legitimate admin activating their account must not be
    collateral damage from other traffic sharing their IP (a shared office NAT,
    or noise from the coarse counter's own budget) as long as they are under it."""
    data = await init_company(client, name="ActivateCo", email="admin@activateco.com")

    for _ in range(settings.LOGIN_IP_RATE_LIMIT - 1):
        await client.post(
            "/api/v1/auth/company/activate",
            json={
                "email": _email(),
                "activation_key": "wrong",
                "password": "correct-horse-battery",
                "full_name": "Someone Else",
            },
        )

    resp = await client.post(
        "/api/v1/auth/company/activate",
        json={
            "email": "admin@activateco.com",
            "activation_key": data["activation_key"],
            "password": "correct-horse-battery",
            "full_name": "Real Admin",
        },
    )
    assert resp.status_code == 204, resp.text


# --------------------------------------------------------------------------
# Registration and refresh
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auditor_registration_is_capped_per_ip(client: AsyncClient):
    """Distinct emails each time — this is account spam plus the KUB-002
    enumeration oracle, and only the coarse counter covers it."""
    for _ in range(settings.REGISTER_RATE_LIMIT):
        resp = await client.post(
            "/api/v1/auth/auditor/register",
            json={"email": _email(), "password": "Valid1!Pass!", "name": "Auditor"},
        )
        assert resp.status_code == 201, resp.text

    resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={"email": _email(), "password": "Valid1!Pass!", "name": "Auditor"},
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["company", "auditor"])
async def test_refresh_is_throttled(client: AsyncClient, identity: str):
    path = f"/api/v1/auth/{identity}/refresh"
    for _ in range(settings.REFRESH_RATE_LIMIT):
        resp = await client.post(path, json={"refresh_token": "not-a-token"})
        assert resp.status_code == 401, resp.text

    resp = await client.post(path, json={"refresh_token": "not-a-token"})
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_refresh_budget_clears_a_whole_tenant_signing_in_at_once(
    client: AsyncClient,
):
    """Anti-test against tuning refresh too tightly. Every tab of every user in a
    customer's office shares one NAT address and rehydrates on load; a 429 here
    is a forced logout, not a warning."""
    for _ in range(60):
        resp = await client.post(
            "/api/v1/auth/company/refresh",
            json={"refresh_token": "not-a-token"},
            headers=_ip("198.51.100.200"),
        )
        assert resp.status_code == 401


# --------------------------------------------------------------------------
# Retry-After — what the SPA renders
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_carries_a_usable_retry_after(client: AsyncClient):
    for _ in range(settings.LOGIN_RATE_LIMIT + 1):
        resp = await client.post(
            "/api/v1/auth/auditor/login", json={"email": "fixed@ratelimit.example.com", **BAD_LOGIN}
        )

    assert resp.status_code == 429
    retry_after = int(resp.headers["retry-after"])
    # Positive, or the UI renders "try again in 0 minutes"; never longer than the
    # window, or it tells the user to wait for a lock that has already lifted.
    assert 0 < retry_after <= settings.LOGIN_RATE_WINDOW


@pytest.mark.asyncio
async def test_retry_after_falls_back_to_the_window_when_the_ttl_is_gone(
    client: AsyncClient, monkeypatch
):
    """A key can lose its TTL (-1) or expire between INCR and TTL (-2). Redis
    reports those as negative numbers, and passing one through would produce
    `Retry-After: -2`."""
    for _ in range(settings.LOGIN_RATE_LIMIT):
        await client.post(
            "/api/v1/auth/auditor/login", json={"email": "ttl@ratelimit.example.com", **BAD_LOGIN}
        )

    real = rate_limit._redis()

    class NoTtl:
        def __getattr__(self, name):
            return getattr(real, name)

        async def ttl(self, key):
            return -2

    monkeypatch.setattr(rate_limit, "_redis", lambda: NoTtl())

    resp = await client.post(
        "/api/v1/auth/auditor/login", json={"email": "ttl@ratelimit.example.com", **BAD_LOGIN}
    )
    assert resp.status_code == 429
    assert int(resp.headers["retry-after"]) == settings.LOGIN_RATE_WINDOW


# --------------------------------------------------------------------------
# Availability: the limiter must never be the thing that breaks auth
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_survives_a_dead_redis_and_says_so(
    client: AsyncClient, monkeypatch, caplog
):
    """Fail-open is a deliberate trade-off (Redis runs `noeviction` at 200mb, so
    filling it is a realistic way to reach this state). It must be loud: a silent
    fail-open is an unprotected login endpoint nobody knows about."""

    class DeadRedis:
        async def incr(self, *a, **k):
            raise ConnectionError("redis is gone")

        async def expire(self, *a, **k):
            raise ConnectionError("redis is gone")

        async def ttl(self, *a, **k):
            raise ConnectionError("redis is gone")

    monkeypatch.setattr(rate_limit, "_redis", lambda: DeadRedis())

    with caplog.at_level("ERROR"):
        for _ in range(settings.LOGIN_IP_RATE_LIMIT + 5):
            resp = await client.post(
                "/api/v1/auth/auditor/login", json={"email": _email(), **BAD_LOGIN}
            )
            assert resp.status_code == 401, "the limiter turned a store outage into an outage"

    errors = [r for r in caplog.records if r.name == "app.rate_limit"]
    assert errors, "a fail-open went unrecorded"
    assert "failing open" in errors[0].getMessage()
    assert errors[0].exc_info is not None, "logged without the underlying error"


@pytest.mark.asyncio
async def test_a_store_that_dies_mid_check_does_not_500(
    client: AsyncClient, monkeypatch
):
    """Regression: the TTL lookup used to sit outside the try/except, so a Redis
    that survived INCR but not TTL raised out of the endpoint as a 500."""
    real = rate_limit._redis()

    class DiesOnTtl:
        def __getattr__(self, name):
            return getattr(real, name)

        async def ttl(self, key):
            raise ConnectionError("redis died between INCR and TTL")

    monkeypatch.setattr(rate_limit, "_redis", lambda: DiesOnTtl())

    for _ in range(settings.LOGIN_RATE_LIMIT + 2):
        resp = await client.post(
            "/api/v1/auth/auditor/login", json={"email": "mid@ratelimit.example.com", **BAD_LOGIN}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_the_kill_switch_works(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    try:
        for _ in range(settings.LOGIN_IP_RATE_LIMIT + 5):
            resp = await client.post(
                "/api/v1/auth/auditor/login", json={"email": "off@ratelimit.example.com", **BAD_LOGIN}
            )
            assert resp.status_code == 401
    finally:
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
