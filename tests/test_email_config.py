from app.config import Settings


def test_smtp_default_settings(monkeypatch):
    for key in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_USE_TLS", "SMTP_USE_SSL", "SMTP_FROM_EMAIL", "SMTP_FROM_NAME", "SMTP_TIMEOUT"]:
        monkeypatch.delenv(key, raising=False)

    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://test:test@localhost:5432/test",
        JWT_SECRET_KEY="test-secret",
        ROOT_MASTER_KEK="0" * 64,
        INTERNAL_API_KEY="test-key",
    )
    assert settings.SMTP_HOST == ""
    assert settings.SMTP_PORT == 587
    assert settings.SMTP_USER == ""
    assert settings.SMTP_PASSWORD == ""
    assert settings.SMTP_USE_TLS is True
    assert settings.SMTP_USE_SSL is False
    assert settings.SMTP_FROM_EMAIL == "kubera@ethdc.in"
    assert settings.SMTP_FROM_NAME == "Kubera Compliance"
    assert settings.SMTP_TIMEOUT == 15


def test_smtp_custom_settings(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.ethdc.in")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "kubera@ethdc.in")
    monkeypatch.setenv("SMTP_PASSWORD", "secret123")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    monkeypatch.setenv("SMTP_USE_SSL", "true")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "admin@ethdc.in")
    monkeypatch.setenv("SMTP_FROM_NAME", "Kubera Admin")
    monkeypatch.setenv("SMTP_TIMEOUT", "30")

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@localhost:5432/test",
        JWT_SECRET_KEY="test-secret",
        ROOT_MASTER_KEK="0" * 64,
        INTERNAL_API_KEY="test-key",
    )
    assert settings.SMTP_HOST == "smtp.ethdc.in"
    assert settings.SMTP_PORT == 465
    assert settings.SMTP_USER == "kubera@ethdc.in"
    assert settings.SMTP_PASSWORD == "secret123"
    assert settings.SMTP_USE_TLS is False
    assert settings.SMTP_USE_SSL is True
    assert settings.SMTP_FROM_EMAIL == "admin@ethdc.in"
    assert settings.SMTP_FROM_NAME == "Kubera Admin"
    assert settings.SMTP_TIMEOUT == 30
