"""`.dockerignore` must never again ship secrets or tenant data in an image.

The api image ends with `COPY . .`, so the build context IS the image. `.gitignore`
and `.dockerignore` drifted once: `.gitignore` excluded `.env.bak.*`, `data/` and
`.tmp_vault/`, `.dockerignore` did not, and the published image contained a live
SMTP password plus 3013 encrypted tenant documents.

These tests pin both directions — sensitive paths stay OUT, build-required paths
stay IN — because either mistake is silent. A leaked layer is permanent, and a
missing file only surfaces when a container fails to start.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERIGNORE = REPO_ROOT / ".dockerignore"

# Paths that must never enter the build context. Each is a real thing that has
# existed in this repository, not a hypothetical.
MUST_BE_EXCLUDED = [
    ".env",
    ".env.bak.20260831-175813",  # created by docs/SECURITY_HARDENING.md's runbook
    ".env.local",
    "data/vault/some-company-id/doc.enc",
    ".tmp_vault/09b6c2f2/doc.enc",
    ".vault_dev/09721225/doc.enc",
    "creds.txt",
    "server.key",
    "cert.pem",
    "m.txt",
    "kubera-migration-20260831/env",
    "db.dump",
    "vault.tar.gz",
    ".git/config",
    ".venv/bin/python",
    "docker-compose.override.yml",
    "celerybeat-schedule",
    ".maintenance.lock",
    "Kubera — Corporate Compliance.pdf",
    "ETHDC_Requirement list M26_v1.xlsx",
    "frontend/node_modules/react/index.js",
    "tests/conftest.py",
    "unit_tests/test_compose_exposure.py",
]

# Paths the api or gateway image genuinely needs. Excluding any of these breaks a
# container at runtime rather than at build time, which is why they are pinned.
MUST_BE_INCLUDED = [
    "app/main.py",
    "app/config.py",
    "alembic.ini",
    "alembic/env.py",
    "pyproject.toml",
    "uv.lock",
    # Operator scripts documented in README.md as `docker compose exec api python ...`
    "change_password.py",
    "delete_user.py",
    "send_email.py",
    # Run inside the api container per docs/SECURITY_HARDENING.md
    "ops/kubera-rotate-root-kek.py",
    # The gateway image builds from this same root context.
    "gateway/nginx.conf",
    "gateway/modes/app.conf",
    "gateway/initialize-runtime.sh",
    "maintenance/index.html",
]


def _patterns() -> list[str]:
    lines = DOCKERIGNORE.read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def is_excluded(path: str) -> bool:
    """Approximate Docker's build-context matching: last matching pattern wins,
    `!` re-includes, and a directory pattern excludes everything beneath it."""
    excluded = False
    for pattern in _patterns():
        negated = pattern.startswith("!")
        pat = pattern.lstrip("!").rstrip("/")
        if _matches(path, pat):
            excluded = not negated
    return excluded


def _matches(path: str, pat: str) -> bool:
    if fnmatch.fnmatch(path, pat):
        return True
    # A pattern matching any leading path segment excludes the whole subtree.
    parts = path.split("/")
    for i in range(1, len(parts) + 1):
        if fnmatch.fnmatch("/".join(parts[:i]), pat):
            return True
    # Bare filename patterns such as `__pycache__` match at any depth.
    return "/" not in pat and any(fnmatch.fnmatch(part, pat) for part in parts)


def test_dockerignore_exists():
    assert DOCKERIGNORE.is_file(), "a missing .dockerignore ships the entire repo"


def test_secrets_and_tenant_data_never_enter_the_build_context():
    leaked = [p for p in MUST_BE_EXCLUDED if not is_excluded(p)]
    assert not leaked, (
        "these would be baked into the image by `COPY . .`:\n  "
        + "\n  ".join(leaked)
    )


def test_build_required_files_are_not_excluded():
    missing = [p for p in MUST_BE_INCLUDED if is_excluded(p)]
    assert not missing, (
        "these are needed inside the image but .dockerignore excludes them:\n  "
        + "\n  ".join(missing)
    )


def test_env_example_is_still_available_to_the_image():
    """`.env.*` is excluded wholesale, so the negation for .env.example must hold."""
    assert not is_excluded(".env.example")


def test_every_secret_gitignore_entry_has_a_dockerignore_counterpart():
    """The specific drift that caused the leak: something .gitignore treats as
    secret that .dockerignore does not exclude.

    Compared functionally, not textually — `.env.*` in .dockerignore legitimately
    covers `.gitignore`'s `.env.bak` without repeating the literal string.
    """
    # marker in .gitignore -> a concrete path it is meant to catch
    secret_markers = {
        ".env": ".env",
        ".env.bak.*": ".env.bak.20260831-175813",
        ".env.local": ".env.local",
        "data/": "data/vault/company/doc.enc",
        ".tmp_vault/": ".tmp_vault/abc/doc.enc",
        ".vault_dev/": ".vault_dev/abc/doc.enc",
        "creds.txt": "creds.txt",
        "*.key": "server.key",
        "*.pem": "cert.pem",
        "m.txt": "m.txt",
        "docker-compose.override.yml": "docker-compose.override.yml",
        "kubera-migration-*": "kubera-migration-20260831/env",
        "*.dump": "db.dump",
        "*.tar.gz": "vault.tar.gz",
    }
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    for marker, example in secret_markers.items():
        assert marker in gitignore, (
            f"{marker!r} is no longer in .gitignore — if it stopped being secret, "
            f"remove it here too; if it was renamed, update this test"
        )
        assert is_excluded(example), (
            f".gitignore treats {marker!r} as secret, but .dockerignore does not "
            f"exclude {example!r} — `COPY . .` would bake it into the image"
        )
