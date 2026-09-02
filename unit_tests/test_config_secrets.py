"""Tests for the startup rejection of placeholder secrets.

The root conftest.py sets KUBERA_ALLOW_INSECURE_DEFAULTS=1 for the whole suite,
so every test here removes it first to exercise the real validator.
"""
from __future__ import annotations

import pytest

from app.config import InsecureConfigurationError, Settings

REDIS_PW = "b8f2c1d4e6a09371f5c2b8d4e6a09371f5c2b8d4e6a09371f5c2b8d4e6a09371"


def _good(**overrides) -> dict:
    """A configuration that should pass, so each test can spoil one field."""
    values = {
        "DATABASE_URL": "postgresql+asyncpg://kubera:a-real-database-password@postgres:5432/kubera",
        "REDIS_URL": f"redis://:{REDIS_PW}@redis:6379/0",
        "CELERY_BROKER_URL": f"redis://:{REDIS_PW}@redis:6379/0",
        "CELERY_RESULT_BACKEND": f"redis://:{REDIS_PW}@redis:6379/0",
        "JWT_SECRET_KEY": "d4e6a09371f5c2b8d4e6a09371f5c2b8d4e6a09371f5c2b8",
        "ROOT_MASTER_KEK": "a" * 64,
        "INTERNAL_API_KEY": "371f5c2b8d4e6a09371f5c2b8d4e6a09371f5c2b8d4e6a09",
    }
    values.update(overrides)
    return values


@pytest.fixture(autouse=True)
def _enforce_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KUBERA_ALLOW_INSECURE_DEFAULTS", raising=False)


def _build(**overrides) -> Settings:
    # _env_file=None keeps the developer's real .env out of the test.
    return Settings(_env_file=None, **_good(**overrides))


def test_a_fully_configured_environment_is_accepted() -> None:
    settings = _build()
    assert settings.ROOT_MASTER_KEK == "a" * 64


def test_escape_hatch_permits_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUBERA_ALLOW_INSECURE_DEFAULTS", "1")
    settings = _build(
        JWT_SECRET_KEY="change-me-to-a-random-64-char-string",
        ROOT_MASTER_KEK="0" * 64,
    )
    assert settings.ROOT_MASTER_KEK == "0" * 64


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        (
            "JWT_SECRET_KEY",
            "change-me-to-a-random-64-char-string",
            "JWT_SECRET_KEY is the .env.example placeholder",
        ),
        ("JWT_SECRET_KEY", "short", "at least 32 are required"),
        (
            "INTERNAL_API_KEY",
            "change-me-internal-key",
            "INTERNAL_API_KEY is the .env.example placeholder",
        ),
        ("ROOT_MASTER_KEK", "0" * 64, "all-zero .env.example placeholder"),
        ("ROOT_MASTER_KEK", "a" * 63, "exactly 64 hexadecimal characters"),
        ("ROOT_MASTER_KEK", "z" * 64, "exactly 64 hexadecimal characters"),
        (
            "DATABASE_URL",
            "postgresql+asyncpg://kubera:kubera_secret@postgres:5432/kubera",
            "DATABASE_URL uses the .env.example placeholder password",
        ),
        (
            "DATABASE_URL",
            "postgresql+asyncpg://kubera@postgres:5432/kubera",
            "DATABASE_URL has no password",
        ),
    ],
)
def test_placeholder_and_weak_secrets_are_rejected(
    field: str, value: str, expected_message: str
) -> None:
    with pytest.raises(InsecureConfigurationError) as excinfo:
        _build(**{field: value})
    assert expected_message in str(excinfo.value)


@pytest.mark.parametrize(
    "field", ["REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"]
)
def test_unauthenticated_redis_is_rejected(field: str) -> None:
    """Redis is the Celery broker and the rate-limit store — it must authenticate.

    Without this, removing the password from a single URL silently reopens task
    injection and unthrottled login brute-force.
    """
    with pytest.raises(InsecureConfigurationError) as excinfo:
        _build(**{field: "redis://redis:6379/0"})
    assert f"{field} has no password" in str(excinfo.value)


@pytest.mark.parametrize(
    "field", ["REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"]
)
def test_placeholder_redis_password_is_rejected(field: str) -> None:
    with pytest.raises(InsecureConfigurationError) as excinfo:
        _build(**{field: "redis://:change-me-redis-password@redis:6379/0"})
    assert f"{field} uses the .env.example placeholder password" in str(excinfo.value)


def test_all_problems_are_reported_at_once() -> None:
    """An operator should get the full list, not one error per restart."""
    with pytest.raises(InsecureConfigurationError) as excinfo:
        _build(
            JWT_SECRET_KEY="change-me-to-a-random-64-char-string",
            INTERNAL_API_KEY="change-me-internal-key",
            ROOT_MASTER_KEK="0" * 64,
            REDIS_URL="redis://redis:6379/0",
        )
    message = str(excinfo.value)
    for expected in ("JWT_SECRET_KEY", "INTERNAL_API_KEY", "ROOT_MASTER_KEK", "REDIS_URL"):
        assert expected in message


def test_every_placeholder_in_env_example_is_covered() -> None:
    """.env.example must not gain a new placeholder the validator does not know.

    Catches the failure mode where someone adds a `change-me-...` default and the
    startup check silently accepts it in production.
    """
    from pathlib import Path
    from urllib.parse import urlsplit

    from app.config import _PLACEHOLDER_SECRETS

    example = Path(__file__).resolve().parent.parent / ".env.example"
    unknown = []
    for line in example.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))

        # For a connection URL the validator inspects the embedded password, not
        # the whole string, so that is what has to be a known placeholder.
        if "://" in value:
            candidate = urlsplit(value).password
        else:
            candidate = value
        if not candidate:
            continue

        if "change-me" in candidate.lower() and candidate not in _PLACEHOLDER_SECRETS:
            unknown.append(f"{key} -> {candidate}")

    assert not unknown, (
        ".env.example has placeholder values the validator will not reject:\n  "
        + "\n  ".join(unknown)
        + "\nAdd them to _PLACEHOLDER_SECRETS in app/config.py."
    )
