"""Deployment invariants that are easy to regress and expensive to notice.

Each test here corresponds to a defect that was live in production configuration
and verified against a running stack, not to a hypothetical.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())
SERVICES = COMPOSE["services"]
CADDYFILE = (REPO_ROOT / "Caddyfile").read_text()


def strip_comments(text: str, marker: str = "#") -> str:
    """Directive text only. These tests assert on what a file *does*, and several
    of the comments deliberately name the thing being avoided."""
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith(marker)
    )

GATEWAY_CONF = (REPO_ROOT / "gateway" / "nginx.conf").read_text()
APP_CONF = (REPO_ROOT / "gateway" / "modes" / "app.conf").read_text()

PYTHON_SERVICES = ["api", "worker", "beat"]


class TestVaultPathIsPinnedToTheVolume:
    """.env ships VAULT_STORAGE_PATH=./data/vault. Inside a container that
    resolves against WORKDIR /code, so the app would write tenant documents to
    /code/data/vault — the container's own filesystem — instead of the vault_data
    volume, losing every upload on the next `up -d --build`. It only ever worked
    because the old compose file bind-mounted `.:/code`, which production no
    longer does."""

    @pytest.mark.parametrize("service", PYTHON_SERVICES)
    def test_storage_paths_are_absolute_container_paths(self, service):
        env = SERVICES[service]["environment"]
        assert env["VAULT_STORAGE_PATH"] == "/data/vault"
        assert env["BACKUP_PATH"] == "/data/backups"

    @pytest.mark.parametrize("service", ["api", "worker"])
    def test_the_pinned_vault_path_is_where_the_volume_is_mounted(self, service):
        mounts = [v.split(":")[1] for v in SERVICES[service]["volumes"]]
        assert SERVICES[service]["environment"]["VAULT_STORAGE_PATH"] in mounts


class TestContainerPrivileges:
    @pytest.mark.parametrize("service", list(SERVICES))
    def test_no_new_privileges_everywhere(self, service):
        assert "no-new-privileges:true" in SERVICES[service].get("security_opt", [])

    @pytest.mark.parametrize("service", PYTHON_SERVICES)
    def test_application_containers_drop_all_capabilities(self, service):
        """api/worker/beat run as uid 10001 and need no privileged operation.
        They also hold the root KEK, so they are the containers where uid 0 would
        matter most."""
        assert SERVICES[service].get("cap_drop") == ["ALL"]
        assert "cap_add" not in SERVICES[service]

    @pytest.mark.parametrize("service", ["gateway", "frontend"])
    def test_nginx_keeps_only_the_capabilities_it_provably_needs(self, service):
        """Determined by removing them and watching the container fail: without
        CHOWN nginx exits on chown("/var/cache/nginx/client_temp")."""
        assert SERVICES[service]["cap_drop"] == ["ALL"]
        assert set(SERVICES[service]["cap_add"]) == {
            "NET_BIND_SERVICE", "SETUID", "SETGID", "CHOWN",
        }

    def test_dockerfile_runs_as_a_non_root_user(self):
        dockerfile = (REPO_ROOT / "Dockerfile").read_text()
        assert "USER kubera" in dockerfile
        # The chown must happen before any volume is attached, so that Docker
        # copies kubera ownership into a freshly created named volume.
        assert dockerfile.index("chown -R kubera:kubera") < dockerfile.index("USER kubera")


class TestResourceLimits:
    @pytest.mark.parametrize("service", list(SERVICES))
    def test_every_service_has_a_memory_limit(self, service):
        assert "mem_limit" in SERVICES[service], (
            f"{service} is unbounded; on a 4 GB host one runaway container "
            f"OOM-kills whatever the kernel picks, usually Postgres"
        )

    def test_total_reservation_leaves_headroom_on_a_4gb_host(self):
        def to_bytes(value: str) -> int:
            units = {"k": 1024, "m": 1024**2, "g": 1024**3}
            value = str(value).strip().lower()
            return int(float(value[:-1]) * units[value[-1]]) if value[-1] in units else int(value)

        total = sum(to_bytes(s["mem_limit"]) for s in SERVICES.values())
        assert total < 3.6 * 1024**3, f"limits total {total / 1024**3:.2f} GB, too tight on 4 GB"


class TestRedisBrokerSafety:
    def test_redis_never_evicts(self):
        """Redis is the Celery broker. An LRU policy silently discards queued
        tasks under memory pressure — emails and backups would disappear with no
        error. noeviction rejects the write instead, which fails loudly."""
        command = " ".join(SERVICES["redis"]["command"])
        assert "--maxmemory-policy noeviction" in command
        assert "--maxmemory " in command

    def test_redis_still_requires_a_password(self):
        assert "--requirepass" in " ".join(SERVICES["redis"]["command"])


class TestEdgeHeaders:
    def test_security_headers_are_set(self):
        for header in (
            "X-Frame-Options",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "Strict-Transport-Security",
        ):
            assert header in CADDYFILE

    def test_hsts_is_not_applied_to_localhost(self):
        """Pinning HTTPS for `localhost` affects every other project in a
        developer's browser and cannot be undone without clearing browser state."""
        assert "not host localhost" in CADDYFILE

    def test_no_csp_frame_ancestors(self):
        """A srcdoc iframe inherits its parent's CSP, and AssetReportsPage.tsx
        renders report previews in one, so `frame-ancestors` would blank the
        preview. X-Frame-Options is used instead — it never applies to srcdoc."""
        assert "frame-ancestors" not in strip_comments(CADDYFILE)

    def test_upstream_server_header_is_removed(self):
        assert "-Server" in CADDYFILE
        assert "server_tokens off" in GATEWAY_CONF

    def test_forwarded_for_is_replaced_not_appended(self):
        """app/rate_limit.py trusts the first X-Forwarded-For entry. That is only
        safe because Caddy overwrites the header for untrusted peers; pinning it
        here keeps the rate limiter correct if that default ever changes."""
        assert "header_up X-Forwarded-For {remote_host}" in CADDYFILE


class TestUploadPath:
    def test_gateway_does_not_impose_the_default_1mib_body_limit(self):
        """nginx defaults to client_max_body_size 1m, which 413'd every document
        over 1 MiB — including the 2 MB company logos the frontend allows."""
        assert "client_max_body_size 0" in GATEWAY_CONF

    def test_uploads_are_streamed_rather_than_buffered_whole(self):
        assert "proxy_request_buffering off" in APP_CONF


class TestCorsIsNeverWildcard:
    def test_settings_never_produce_a_wildcard_origin(self):
        import os

        os.environ["KUBERA_ALLOW_INSECURE_DEFAULTS"] = "1"
        from app.config import Settings

        base = dict(
            _env_file=None,
            DATABASE_URL="postgresql://u:p@h/d",
            JWT_SECRET_KEY="x" * 40,
            ROOT_MASTER_KEK="a" * 64,
            INTERNAL_API_KEY="y" * 40,
        )
        assert "*" not in Settings(**base).cors_origins()

    def test_main_does_not_pass_a_wildcard(self):
        """Starlette reflects the caller's Origin when the allow-list is `*` and
        credentials are enabled, which answered https://evil.example with its own
        origin and allow-credentials: true."""
        main = strip_comments((REPO_ROOT / "app" / "main.py").read_text())
        assert 'allow_origins=["*"]' not in main
        assert "cors_origins()" in main
