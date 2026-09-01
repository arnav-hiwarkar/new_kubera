"""Root pytest configuration.

`app.config` refuses to load a configuration that still uses the placeholder
secrets shipped in `.env.example` (see `Settings._reject_insecure_secrets`). That
check exists to stop a real deployment from serving with a publicly-known
`JWT_SECRET_KEY` or an all-zero `ROOT_MASTER_KEK`.

The test suite runs against a throwaway database with throwaway secrets, so it
opts out of that check here — before any test module imports `app.config`. Only
pytest is affected; nothing else in the repository sets this variable.

Tests that need to exercise the validator itself construct `Settings` with the
variable removed via monkeypatch — see `unit_tests/test_config_secrets.py`.
"""
import os

os.environ.setdefault("KUBERA_ALLOW_INSECURE_DEFAULTS", "1")
