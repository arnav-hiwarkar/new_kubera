"""Unit tests for the host-side maintenance operator command."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import maintenance


class FakeGateway:
    def __init__(self, *, mode="maintenance", readiness=None, through=True, events=None):
        self.mode = mode
        self._readiness = readiness or {"frontend": (True, ""), "api": (True, "")}
        self.through = through
        self.events = events if events is not None else []
        self.current_state = {"mode": "active"}

    def ensure_available(self):
        self.events.append("available")

    def selected_mode(self):
        return self.mode

    def write_state(self, state):
        self.current_state = state
        self.events.append(("state", state))

    def switch(self, mode):
        self.mode = mode
        self.events.append(("switch", mode))

    def readiness(self):
        self.events.append("readiness")
        return self._readiness

    def app_through_gateway(self):
        self.events.append("through")
        return self.through

    def state(self):
        return self.current_state

    def validate(self, check=True):
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class FakeEdge:
    def __init__(self, *, upstreams=None, reconciled=False, available=True, valid=True, events=None):
        self.upstreams = upstreams or {"gateway:80"}
        self.reconciled = reconciled
        self.available = available
        self.valid = valid
        self.events = events if events is not None else []

    def ensure_gateway_route(self):
        self.events.append("edge-reconcile")
        self.upstreams = {"gateway:80"}
        return self.reconciled

    def assert_gateway_route(self):
        self.events.append("edge-check")
        if self.upstreams != {"gateway:80"}:
            raise maintenance.MaintenanceError("edge mismatch")

    def ensure_available(self):
        self.events.append("edge-available")
        if not self.available:
            raise maintenance.MaintenanceError("Caddy unavailable")

    def active_upstreams(self):
        self.events.append("edge-active")
        return self.upstreams

    def validate(self, check=True):
        self.events.append("edge-validate")
        return SimpleNamespace(returncode=0 if self.valid else 1, stdout="", stderr="")


def test_command_on_resets_countdown_before_switch(monkeypatch, capsys):
    events = []
    gateway = FakeGateway(mode="app", events=events)
    edge = FakeEdge(events=events)
    monkeypatch.setattr(maintenance, "domain_url", lambda: "https://kubera.example")

    assert maintenance.command_on(gateway, edge) == 0
    assert events == [
        "available",
        "edge-reconcile",
        ("state", {"mode": "active"}),
        ("switch", "maintenance"),
        "edge-check",
    ]
    assert "https://kubera.example" in capsys.readouterr().out


def test_command_off_refuses_when_a_service_is_unhealthy():
    gateway = FakeGateway(readiness={"frontend": (True, ""), "api": (False, "connection refused")})

    with pytest.raises(maintenance.MaintenanceError, match="api"):
        maintenance.command_off(gateway, FakeEdge())

    assert gateway.mode == "maintenance"
    assert gateway.current_state == {"mode": "active"}


def test_command_off_publishes_countdown_then_switches(monkeypatch):
    events = []
    gateway = FakeGateway(events=events)
    edge = FakeEdge(events=events)
    monkeypatch.setattr(maintenance, "run_countdown", lambda: gateway.events.append("countdown"))
    monkeypatch.setattr(maintenance, "iso_deadline", lambda: "2026-08-03T12:00:10.000Z")

    assert maintenance.command_off(gateway, edge) == 0
    assert events == [
        "available",
        "edge-reconcile",
        "readiness",
        ("state", {"mode": "closing", "ends_at": "2026-08-03T12:00:10.000Z"}),
        "countdown",
        ("switch", "app"),
        "through",
        "edge-check",
        ("state", {"mode": "active"}),
    ]


def test_command_off_ctrl_c_cancels_return(monkeypatch):
    gateway = FakeGateway()

    def interrupted():
        raise KeyboardInterrupt

    monkeypatch.setattr(maintenance, "run_countdown", interrupted)
    assert maintenance.command_off(gateway, FakeEdge()) == 130
    assert gateway.mode == "maintenance"
    assert gateway.current_state == {"mode": "active"}


def test_failed_post_switch_check_restores_maintenance(monkeypatch):
    gateway = FakeGateway(through=False)
    monkeypatch.setattr(maintenance, "run_countdown", lambda: None)

    with pytest.raises(maintenance.MaintenanceError, match="did not respond"):
        maintenance.command_off(gateway, FakeEdge())

    assert gateway.mode == "maintenance"
    assert gateway.current_state == {"mode": "active"}


def test_gateway_switch_restores_previous_target_on_invalid_config(monkeypatch):
    gateway = maintenance.Gateway(compose=["docker", "compose"])
    pointed = []
    monkeypatch.setattr(gateway, "selected_mode", lambda: "app")
    monkeypatch.setattr(gateway, "_point_to", pointed.append)
    monkeypatch.setattr(
        gateway,
        "validate",
        lambda check=False: SimpleNamespace(returncode=1, stderr="bad config", stdout=""),
    )

    with pytest.raises(maintenance.MaintenanceError, match="previous mode restored"):
        gateway.switch("maintenance")
    assert pointed == ["maintenance", "app"]


def test_gateway_switch_restores_previous_target_on_reload_failure(monkeypatch):
    gateway = maintenance.Gateway(compose=["docker", "compose"])
    pointed = []
    reloads = iter(
        [
            SimpleNamespace(returncode=1, stderr="reload failed", stdout=""),
            SimpleNamespace(returncode=0, stderr="", stdout=""),
        ]
    )
    monkeypatch.setattr(gateway, "selected_mode", lambda: "app")
    monkeypatch.setattr(gateway, "_point_to", pointed.append)
    monkeypatch.setattr(
        gateway,
        "validate",
        lambda check=False: SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    monkeypatch.setattr(gateway, "reload", lambda check=False: next(reloads))

    with pytest.raises(maintenance.MaintenanceError, match="reload failed"):
        gateway.switch("maintenance")
    assert pointed == ["maintenance", "app"]


def test_gateway_write_state_uses_json_stdin(monkeypatch):
    gateway = maintenance.Gateway(compose=["docker", "compose"])
    captured = {}

    def fake_exec(args, *, input_text=None, check=True):
        captured["args"] = args
        captured["input"] = input_text
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(gateway, "exec", fake_exec)
    gateway.write_state({"mode": "closing", "ends_at": "soon"})
    assert json.loads(captured["input"]) == {"mode": "closing", "ends_at": "soon"}
    assert "state.json.next" in captured["args"][-1]


def test_iso_deadline_is_exactly_ten_seconds():
    now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    assert maintenance.iso_deadline(now) == "2026-08-03T12:00:10.000Z"


def test_countdown_can_run_against_fake_clock():
    clock = [100.0]
    shown = []

    def sleep(seconds):
        clock[0] += seconds

    maintenance.run_countdown(
        3,
        monotonic=lambda: clock[0],
        sleep=sleep,
        output=shown.append,
    )
    assert shown == ["  Returning in 3…", "  Returning in 2…", "  Returning in 1…"]


def test_seconds_until_rejects_malformed_deadline():
    assert maintenance.seconds_until("not-a-date") is None
    assert maintenance.seconds_until(None) is None


def test_parse_args_rejects_unknown_command():
    with pytest.raises(SystemExit):
        maintenance.parse_args(["maybe"])


def test_operator_lock_rejects_concurrent_command():
    with maintenance.operator_lock():
        with pytest.raises(maintenance.MaintenanceError, match="already running"):
            with maintenance.operator_lock():
                pass


def test_off_is_idempotent_when_app_is_already_live(capsys):
    events = []
    gateway = FakeGateway(mode="app", events=events)
    edge = FakeEdge(events=events)
    assert maintenance.command_off(gateway, edge) == 0
    assert events == ["available", "edge-reconcile", "readiness", "edge-check"]
    assert "already OFF" in capsys.readouterr().out


def test_extract_dials_walks_nested_caddy_config():
    config = {
        "apps": {
            "http": {
                "servers": {
                    "srv0": {
                        "routes": [
                            {"handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "gateway:80"}]}]},
                            {"handle": [{"upstreams": [{"dial": "metrics:9000"}]}]},
                        ]
                    }
                }
            }
        }
    }
    assert maintenance.extract_dials(config) == {"gateway:80", "metrics:9000"}


@pytest.mark.parametrize("payload", ["not json", "{}", '{"apps": []}'])
def test_parse_caddy_dials_rejects_malformed_or_missing_upstreams(payload):
    with pytest.raises(maintenance.MaintenanceError):
        maintenance.parse_caddy_dials(payload, "test config")


def test_edge_contract_requires_only_gateway():
    assert maintenance.edge_route_is_healthy({"gateway:80"})
    assert not maintenance.edge_route_is_healthy({"frontend:80"})
    assert not maintenance.edge_route_is_healthy({"gateway:80", "frontend:80"})
    assert not maintenance.edge_route_is_healthy(set())


def test_caddy_reconciliation_is_noop_when_active_route_is_correct(monkeypatch):
    edge = maintenance.CaddyEdge(compose=["docker", "compose"])
    events = []
    monkeypatch.setattr(edge, "ensure_available", lambda: events.append("available"))
    monkeypatch.setattr(edge, "active_upstreams", lambda: {"gateway:80"})
    monkeypatch.setattr(edge, "mounted_upstreams", lambda: events.append("mounted"))

    assert edge.ensure_gateway_route() is False
    assert events == ["available"]


def test_caddy_reconciliation_validates_reloads_and_waits(monkeypatch):
    edge = maintenance.CaddyEdge(compose=["docker", "compose"])
    events = []
    monkeypatch.setattr(edge, "ensure_available", lambda: events.append("available"))
    monkeypatch.setattr(edge, "active_upstreams", lambda: {"frontend:80"})
    monkeypatch.setattr(edge, "mounted_upstreams", lambda: events.append("mounted") or {"gateway:80"})
    monkeypatch.setattr(
        edge,
        "validate",
        lambda check=False: events.append("validate") or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        edge,
        "reload",
        lambda check=False: events.append("reload") or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(edge, "wait_for_gateway_route", lambda: events.append("wait") or True)

    assert edge.ensure_gateway_route() is True
    assert events == ["available", "mounted", "validate", "reload", "wait"]


def test_caddy_reconciliation_refuses_old_mounted_file(monkeypatch):
    edge = maintenance.CaddyEdge(compose=["docker", "compose"])
    monkeypatch.setattr(edge, "ensure_available", lambda: None)
    monkeypatch.setattr(edge, "active_upstreams", lambda: {"frontend:80"})
    monkeypatch.setattr(edge, "mounted_upstreams", lambda: {"frontend:80"})

    with pytest.raises(maintenance.MaintenanceError, match="mounted Caddyfile still bypasses"):
        edge.ensure_gateway_route()


def test_caddy_reconciliation_does_not_reload_invalid_file(monkeypatch):
    edge = maintenance.CaddyEdge(compose=["docker", "compose"])
    monkeypatch.setattr(edge, "ensure_available", lambda: None)
    monkeypatch.setattr(edge, "active_upstreams", lambda: {"frontend:80"})
    monkeypatch.setattr(edge, "mounted_upstreams", lambda: {"gateway:80"})
    monkeypatch.setattr(
        edge,
        "validate",
        lambda check=False: SimpleNamespace(returncode=1, stdout="", stderr="invalid directive"),
    )
    monkeypatch.setattr(edge, "reload", lambda check=False: pytest.fail("reload must not run"))

    with pytest.raises(maintenance.MaintenanceError, match="invalid directive"):
        edge.ensure_gateway_route()


def test_caddy_reconciliation_reports_reload_failure(monkeypatch):
    edge = maintenance.CaddyEdge(compose=["docker", "compose"])
    monkeypatch.setattr(edge, "ensure_available", lambda: None)
    monkeypatch.setattr(edge, "active_upstreams", lambda: {"frontend:80"})
    monkeypatch.setattr(edge, "mounted_upstreams", lambda: {"gateway:80"})
    monkeypatch.setattr(
        edge,
        "validate",
        lambda check=False: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        edge,
        "reload",
        lambda check=False: SimpleNamespace(returncode=1, stdout="", stderr="admin refused reload"),
    )

    with pytest.raises(maintenance.MaintenanceError, match="admin refused reload"):
        edge.ensure_gateway_route()


def test_caddy_reconciliation_reports_route_that_stays_stale(monkeypatch):
    edge = maintenance.CaddyEdge(compose=["docker", "compose"])
    monkeypatch.setattr(edge, "ensure_available", lambda: None)
    monkeypatch.setattr(edge, "active_upstreams", lambda: {"frontend:80"})
    monkeypatch.setattr(edge, "mounted_upstreams", lambda: {"gateway:80"})
    monkeypatch.setattr(
        edge,
        "validate",
        lambda check=False: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        edge,
        "reload",
        lambda check=False: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(edge, "wait_for_gateway_route", lambda: False)

    with pytest.raises(maintenance.MaintenanceError, match="Active: frontend:80"):
        edge.ensure_gateway_route()


def test_active_caddy_admin_error_is_actionable(monkeypatch):
    edge = maintenance.CaddyEdge(compose=["docker", "compose"])
    monkeypatch.setattr(
        edge,
        "exec",
        lambda args, check=False: SimpleNamespace(returncode=1, stdout="", stderr="connection refused"),
    )
    with pytest.raises(maintenance.MaintenanceError, match="active admin configuration"):
        edge.active_upstreams()


def test_status_reports_stale_edge_without_reloading(capsys):
    edge = FakeEdge(upstreams={"frontend:80"})
    result = maintenance.command_status(FakeGateway(mode="app"), edge)
    output = capsys.readouterr().out
    assert result == 1
    assert "MISMATCH" in output
    assert "frontend:80" in output
    assert "edge-reconcile" not in edge.events


def test_status_reports_healthy_edge(capsys):
    result = maintenance.command_status(FakeGateway(mode="app"), FakeEdge())
    output = capsys.readouterr().out
    assert result == 0
    assert "Edge route:  gateway:80" in output


def test_status_reports_unavailable_caddy(capsys):
    result = maintenance.command_status(FakeGateway(mode="maintenance"), FakeEdge(available=False))
    output = capsys.readouterr().out
    assert result == 1
    assert "UNKNOWN" in output
    assert "Caddy unavailable" in output
