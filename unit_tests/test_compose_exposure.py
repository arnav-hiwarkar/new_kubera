"""Guards the network-exposure invariant of the production compose file.

The production stack must present exactly one internet-facing surface: Caddy on
80/443. Postgres and Redis published to 0.0.0.0 is how this repository used to be
configured, and it is the kind of regression that reappears silently — someone
adds a `ports:` entry to debug something and it ships.

These tests read docker-compose.yml only. The dev override
(docker-compose.override.yml) is gitignored and intentionally does publish
database ports on 127.0.0.1; it never exists on a server, so it is out of scope
here.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

# The only service allowed to publish to a wildcard address, and the only ports
# it may publish there.
PUBLIC_SERVICE = "caddy"
PUBLIC_PORTS = {"80", "443"}

# Services that must not be reachable from the host at all.
DATA_TIER = ("postgres", "redis")

LOOPBACK_PREFIXES = ("127.0.0.1:", "::1:", "localhost:")


@pytest.fixture(scope="module")
def compose() -> dict:
    with COMPOSE_FILE.open() as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def services(compose: dict) -> dict:
    return compose["services"]


def _published(service: dict) -> list[str]:
    """Normalise a service's `ports:` entries to strings.

    Compose accepts both the short syntax ("127.0.0.1:8000:8000") and the long
    mapping form ({target: 8000, published: 8000, host_ip: 127.0.0.1}).
    """
    entries = service.get("ports") or []
    normalised = []
    for entry in entries:
        if isinstance(entry, dict):
            host_ip = entry.get("host_ip")
            published = entry.get("published", "")
            normalised.append(f"{host_ip}:{published}" if host_ip else str(published))
        else:
            normalised.append(str(entry))
    return normalised


def _host_binding(entry: str) -> str:
    """Return the host-side address of a short-syntax port entry.

    "127.0.0.1:8000:8000" -> "127.0.0.1:8000"
    "5433:5432"           -> "5433"          (wildcard: no host IP given)
    "8000"                -> "8000"
    """
    return entry.rsplit(":", 1)[0] if entry.count(":") >= 1 else entry


@pytest.mark.parametrize("name", DATA_TIER)
def test_data_tier_publishes_no_ports(services: dict, name: str) -> None:
    """Postgres and Redis must be reachable only from inside the compose network.

    Nothing on a server needs a host port for these: every ops script uses
    `docker compose exec`. Use the dev override locally instead.
    """
    assert not services[name].get("ports"), (
        f"{name} publishes {services[name]['ports']} in the PRODUCTION compose file. "
        f"Move it to docker-compose.override.yml.example instead."
    )


def test_only_caddy_binds_to_a_wildcard_address(services: dict) -> None:
    """Every published port must be loopback-bound, except Caddy's 80/443."""
    offenders = []
    for name, service in services.items():
        if name == PUBLIC_SERVICE:
            continue
        for entry in _published(service):
            binding = _host_binding(entry)
            if not binding.startswith(LOOPBACK_PREFIXES):
                offenders.append(f"{name}: {entry}")

    assert not offenders, (
        "These services publish to all interfaces (0.0.0.0) and are therefore "
        "reachable from the internet:\n  " + "\n  ".join(offenders) + "\n"
        "Bind them to 127.0.0.1 (e.g. \"127.0.0.1:8000:8000\") or remove the "
        "ports entry. Note that a ufw/firewalld rule will NOT block these — "
        "Docker's DNAT runs before the filter INPUT chain."
    )


def test_caddy_publishes_only_http_and_https(services: dict) -> None:
    exposed = {_host_binding(e) for e in _published(services[PUBLIC_SERVICE])}
    assert exposed == PUBLIC_PORTS, (
        f"caddy publishes {sorted(exposed)}; only {sorted(PUBLIC_PORTS)} may face "
        f"the internet."
    )


def test_data_tier_is_isolated_from_the_edge_network(services: dict) -> None:
    """caddy, gateway and frontend must have no route to Postgres or Redis.

    A compromised edge container should not be able to open a socket to the
    database.
    """
    data_networks = set()
    for name in DATA_TIER:
        data_networks.update(services[name].get("networks") or [])
    assert data_networks, "postgres/redis must declare an explicit network"

    for name in (PUBLIC_SERVICE, "gateway", "frontend"):
        reachable = set(services[name].get("networks") or [])
        overlap = reachable & data_networks
        assert not overlap, (
            f"{name} shares network(s) {sorted(overlap)} with the data tier, so it "
            f"can reach Postgres/Redis directly."
        )


def test_redis_requires_a_password(services: dict) -> None:
    """Redis is the Celery broker and the rate-limit store; it must authenticate."""
    command = services["redis"].get("command")
    rendered = " ".join(command) if isinstance(command, list) else str(command or "")
    assert "--requirepass" in rendered, (
        "redis starts without --requirepass. Unauthenticated Redis means Celery "
        "task injection and a wipeable login rate-limiter."
    )


def test_every_service_url_uses_an_authenticated_redis(services: dict) -> None:
    """The compose-level Redis URLs must carry credentials."""
    keys = ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND")
    offenders = []
    for name, service in services.items():
        environment = service.get("environment") or {}
        if not isinstance(environment, dict):
            continue
        for key in keys:
            value = environment.get(key)
            if value and "@" not in value:
                offenders.append(f"{name}.{key} = {value}")

    assert not offenders, (
        "These Redis URLs have no credentials:\n  " + "\n  ".join(offenders)
    )


def test_production_api_does_not_hot_reload(services: dict) -> None:
    """--reload plus a source bind-mount is a development affordance.

    In production the code is baked into the image by `COPY . .`; mounting the
    host checkout over it means a deploy silently serves whatever is on disk.
    """
    for name in ("api", "worker", "beat"):
        volumes = services[name].get("volumes") or []
        assert ".:/code" not in volumes, (
            f"{name} bind-mounts the source tree in the production compose file"
        )

    command = services["api"].get("command") or ""
    assert "--reload" not in command, "api runs uvicorn --reload in production"
