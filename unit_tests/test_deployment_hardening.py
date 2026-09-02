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


LIMITS_CONF = (REPO_ROOT / "gateway" / "limits.conf").read_text()
GATEWAY_DOCKERFILE = (REPO_ROOT / "gateway" / "Dockerfile").read_text()


class TestEdgeRateLimits:
    """KUB-003. The edge limiter is the backstop that keeps working when Redis
    is down, because app/rate_limit.py deliberately fails open. It was shipped
    keyed on $binary_remote_addr with no real_ip configuration, which — verified
    against the running stack, where the error log recorded `client: 172.19.0.3`
    for every throttled request — gave the entire internet one shared bucket.
    Ten requests from one client exhausted the 1r/s auth zone for everybody."""

    def test_the_zone_config_is_actually_shipped_into_the_image(self):
        assert "gateway/limits.conf /etc/nginx/conf.d/limits.conf" in GATEWAY_DOCKERFILE

    def test_real_client_addresses_are_recovered_before_anything_is_keyed_on_them(self):
        """Without this every limit_req_zone below keys on Caddy's address on the
        `edge` network, which is identical for every visitor."""
        assert "real_ip_header X-Forwarded-For" in LIMITS_CONF
        assert "set_real_ip_from" in LIMITS_CONF
        # Caddy SETS a single-value header (see TestEdgeHeaders), so the last
        # entry is the one trusted entry. Recursive search would walk past it.
        assert "real_ip_recursive off" in LIMITS_CONF

    @pytest.mark.parametrize("zone", ["api_general", "api_auth", "api_conn"])
    def test_the_zones_the_app_config_references_are_defined(self, zone):
        assert f"zone={zone}:10m" in LIMITS_CONF
        assert zone in APP_CONF

    def test_rejections_are_429_not_503(self):
        """503 reads as "the server broke" and is not what the SPA looks for when
        deciding to render the "try again in N minutes" notice."""
        assert "limit_req_status 429" in LIMITS_CONF
        assert "limit_conn_status 429" in LIMITS_CONF

    def test_the_strict_auth_zone_covers_every_credential_endpoint(self):
        for path in (
            "/api/v1/auth/company/login",
            "/api/v1/auth/company/activate",
            "/api/v1/auth/auditor/login",
            "/api/v1/auth/auditor/register",
        ):
            assert path in LIMITS_CONF, f"{path} escapes the strict auth bucket"

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/auth/company/me",
            "/api/v1/auth/auditor/me",
            "/api/v1/auth/company/refresh",
            "/api/v1/auth/auditor/refresh",
            "/api/v1/auth/companies",
        ],
    )
    def test_the_strict_auth_zone_does_not_cover_session_or_operator_routes(self, path):
        """1r/s is sized for password guessing. The SPA calls /me and /refresh on
        every boot and route guard, and ops/kubera-import.sh drives /companies in
        bulk — throttling those at 1r/s logs users out and breaks imports."""
        assert path not in strip_comments(LIMITS_CONF), (
            f"{path} is in the 1r/s auth bucket; it is normal traffic, not a guess"
        )

    def test_every_api_location_carries_a_limit(self):
        """`location = /api/v1/leads/interest` is an exact match, so it does not
        fall through to `location /api/` and needs the backstop named
        explicitly."""
        api_locations = [
            block for block in APP_CONF.split("\nlocation ") if block.startswith(("/api/", "= /api/"))
        ]
        assert len(api_locations) == 2, "an /api/ location was added or removed"
        for block in api_locations:
            assert "limit_req zone=" in block

    def test_throttled_requests_answer_with_the_json_shape_the_spa_parses(self):
        """frontend/src/api/http.ts reads `detail` out of every error body. With
        nginx's stock HTML error page the user sees "Request failed with status
        429" instead of the notice."""
        assert "location @ratelimited" in APP_CONF
        assert '{"detail":"Too many attempts. Please try again later."}' in APP_CONF
        assert "error_page 429 = @ratelimited" in APP_CONF
        assert "add_header Retry-After" in APP_CONF


class TestEnvExampleDoesNotDriftFromSettings:
    """`.env.example` documents the rate-limit knobs as commented-out lines so an
    operator can find and override them without reading app/config.py — but a
    commented-out example is prose, not something Settings validates. A default
    changed in one place and not the other is invisible until someone compares
    them by hand, which is exactly the kind of gap this whole KUB-003 fix was
    written to close elsewhere."""

    ENV_EXAMPLE = (REPO_ROOT / ".env.example").read_text()

    @pytest.mark.parametrize(
        "field",
        [
            "RATE_LIMIT_ENABLED",
            "LOGIN_RATE_LIMIT",
            "LOGIN_RATE_WINDOW",
            "ACTIVATE_RATE_LIMIT",
            "ACTIVATE_RATE_WINDOW",
            "LOGIN_IP_RATE_LIMIT",
            "LOGIN_IP_RATE_WINDOW",
            "REGISTER_RATE_LIMIT",
            "REGISTER_RATE_WINDOW",
            "REFRESH_RATE_LIMIT",
            "REFRESH_RATE_WINDOW",
        ],
    )
    def test_documented_default_matches_the_settings_default(self, field):
        import os
        import re

        os.environ.setdefault("KUBERA_ALLOW_INSECURE_DEFAULTS", "1")
        from app.config import Settings

        actual = Settings.model_fields[field].default
        # Matches `# FIELD=value` — the commented-out form used throughout the
        # rate-limiting block, so an uncommented / real override line for the
        # same field isn't mistaken for the documented default.
        m = re.search(rf"^#\s*{field}=(\S+)", self.ENV_EXAMPLE, re.MULTILINE)
        assert m, f"{field} has no commented-out example in .env.example"
        documented = m.group(1)
        if isinstance(actual, bool):
            assert documented.lower() == str(actual).lower()
        else:
            assert documented == str(actual)
