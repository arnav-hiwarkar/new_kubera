import os
import re
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Placeholder values shipped in .env.example. They are public in this repository,
# so a deployment still using one is not "unconfigured" — it is compromised from
# the moment it boots. The API refuses to start rather than serve with them.
#
# These secrets are reachable through port 443, which is intentionally open to the
# internet, so closing the database ports does nothing to protect them.
_PLACEHOLDER_SECRETS = {
    "change-me-to-a-random-64-char-string",
    "change-me-internal-key",
    "change-me-redis-password",
    "kubera_secret",
    "0" * 64,
}

_HEX64 = re.compile(r"\A[0-9a-fA-F]{64}\Z")

# Set to 1 for CI and throwaway test environments only. Never on a server.
_ESCAPE_HATCH = "KUBERA_ALLOW_INSECURE_DEFAULTS"

_GENERATE = "generate one with: openssl rand -hex 32"


class InsecureConfigurationError(RuntimeError):
    """Raised at startup when a placeholder or missing secret would be used."""


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Auth
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Encryption
    ROOT_MASTER_KEK: str  # 32-byte hex string (64 hex chars)

    # Internal API key
    INTERNAL_API_KEY: str

    # Rate limiting (activation + login)
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT: int = 10
    LOGIN_RATE_WINDOW: int = 300
    ACTIVATE_RATE_LIMIT: int = 10
    ACTIVATE_RATE_WINDOW: int = 900

    # Storage
    VAULT_STORAGE_PATH: str = "/data/vault"
    BACKUP_PATH: str = "/data/backups"
    # Nightly backups are pruned past this age. The vault tarball is a full copy
    # every night, so without pruning the disk fills and Postgres fails to write.
    BACKUP_RETENTION_DAYS: int = 14

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # Domain
    DOMAIN: str = "localhost"
    LANDING_DOMAIN: str = "kuberacompliance.com"

    # CORS. Empty means "derive from DOMAIN and LANDING_DOMAIN", which is what a
    # server should use — the SPA is served from the same origin as the API, so
    # cross-origin access is never needed in production. Set this explicitly only
    # for local development (e.g. the Vite dev server on http://localhost:5173).
    CORS_ALLOWED_ORIGINS: str = ""

    # SMTP / Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_FROM_EMAIL: str = "kubera@ethdc.in"
    SMTP_FROM_NAME: str = "Kubera Compliance"
    SMTP_TIMEOUT: int = 15

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _reject_insecure_secrets(self) -> "Settings":
        if os.environ.get(_ESCAPE_HATCH) == "1":
            return self

        problems: list[str] = []

        if self.JWT_SECRET_KEY in _PLACEHOLDER_SECRETS:
            problems.append(f"JWT_SECRET_KEY is the .env.example placeholder — {_GENERATE}")
        elif len(self.JWT_SECRET_KEY) < 32:
            problems.append(
                f"JWT_SECRET_KEY is only {len(self.JWT_SECRET_KEY)} characters; "
                f"at least 32 are required — {_GENERATE}"
            )

        if self.INTERNAL_API_KEY in _PLACEHOLDER_SECRETS:
            problems.append(f"INTERNAL_API_KEY is the .env.example placeholder — {_GENERATE}")
        elif len(self.INTERNAL_API_KEY) < 32:
            problems.append(
                f"INTERNAL_API_KEY is only {len(self.INTERNAL_API_KEY)} characters; "
                f"at least 32 are required — {_GENERATE}"
            )

        if not _HEX64.match(self.ROOT_MASTER_KEK):
            problems.append(
                "ROOT_MASTER_KEK must be exactly 64 hexadecimal characters (32 bytes) — "
                'generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        elif self.ROOT_MASTER_KEK.lower() in _PLACEHOLDER_SECRETS:
            problems.append(
                "ROOT_MASTER_KEK is the all-zero .env.example placeholder — "
                'generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )

        problems.extend(self._database_problems())
        problems.extend(self._redis_problems())

        if problems:
            raise InsecureConfigurationError(
                "Refusing to start with an insecure configuration:\n  - "
                + "\n  - ".join(problems)
                + f"\n\nFix these in .env. To bypass in CI or a throwaway test "
                f"environment only, set {_ESCAPE_HATCH}=1."
            )
        return self

    def _database_problems(self) -> list[str]:
        password = urlsplit(self.DATABASE_URL).password
        if password is None:
            return ["DATABASE_URL has no password"]
        if password in _PLACEHOLDER_SECRETS:
            return [f"DATABASE_URL uses the .env.example placeholder password — {_GENERATE}"]
        return []

    def _redis_problems(self) -> list[str]:
        # Redis is the Celery broker and the login/activation rate-limit store.
        # Unauthenticated access means task injection and unthrottled credential
        # brute-force, so every Redis URL must carry a real password.
        problems: list[str] = []
        urls = {
            "REDIS_URL": self.REDIS_URL,
            "CELERY_BROKER_URL": self.CELERY_BROKER_URL,
            "CELERY_RESULT_BACKEND": self.CELERY_RESULT_BACKEND,
        }
        for name, url in urls.items():
            password = urlsplit(url).password
            if not password:
                problems.append(
                    f"{name} has no password. Redis requires authentication — set "
                    f"REDIS_PASSWORD in .env and use redis://:<password>@host:6379/0"
                )
            elif password in _PLACEHOLDER_SECRETS:
                problems.append(
                    f"{name} uses the .env.example placeholder password — {_GENERATE}"
                )
        return problems

    def cors_origins(self) -> list[str]:
        """Explicit allow-list of browser origins.

        Never returns "*". Starlette echoes the caller's Origin back when the
        allow-list is a wildcard, so `allow_origins=["*"]` with
        `allow_credentials=True` told every website on the internet that its own
        origin was permitted, with credentials."""
        if self.CORS_ALLOWED_ORIGINS.strip():
            return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]
        origins: list[str] = []
        app_host = (self.DOMAIN or "").strip()
        if app_host:
            origins.append(f"https://{app_host}")
        # The landing domain is an apex, and gateway/modes/app.conf already treats
        # `www.` as an alias for it, so both spellings are legitimate origins.
        landing = (self.LANDING_DOMAIN or "").strip()
        if landing:
            origins += [f"https://{landing}", f"https://www.{landing}"]
        return sorted(set(origins))


@lru_cache()
def get_settings() -> Settings:
    return Settings()
