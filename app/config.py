from pydantic_settings import BaseSettings
from functools import lru_cache


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

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # Domain
    DOMAIN: str = "localhost"

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


@lru_cache()
def get_settings() -> Settings:
    return Settings()
