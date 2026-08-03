"""Unit tests for the host-side maintenance operator command."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import maintenance


class FakeGateway:
    def __init__(self, *, mode="maintenance", readiness=None, through=True):
        self.mode = mode
        self._readiness = readiness or {"frontend": (True, ""), "api": (True, "")}
        self.through = through
        self.events = []
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


def test_command_on_resets_countdown_before_switch(monkeypatch, capsys):
    gateway = FakeGateway(mode="app")
    monkeypatch.setattr(maintenance, "domain_url", lambda: "https://kubera.example")

    assert maintenance.command_on(gateway) == 0
    assert gateway.events == [
        "available",
        ("state", {"mode": "active"}),
        ("switch", "maintenance"),
    ]
    assert "https://kubera.example" in capsys.readouterr().out


def test_command_off_refuses_when_a_service_is_unhealthy():
    gateway = FakeGateway(readiness={"frontend": (True, ""), "api": (False, "connection refused")})

    with pytest.raises(maintenance.MaintenanceError, match="api"):
        maintenance.command_off(gateway)

    assert gateway.mode == "maintenance"
    assert gateway.current_state == {"mode": "active"}


def test_command_off_publishes_countdown_then_switches(monkeypatch):
    gateway = FakeGateway()
    monkeypatch.setattr(maintenance, "run_countdown", lambda: gateway.events.append("countdown"))
    monkeypatch.setattr(maintenance, "iso_deadline", lambda: "2026-08-03T12:00:10.000Z")

    assert maintenance.command_off(gateway) == 0
    assert gateway.events == [
        "available",
        "readiness",
        ("state", {"mode": "closing", "ends_at": "2026-08-03T12:00:10.000Z"}),
        "countdown",
        ("switch", "app"),
        "through",
        ("state", {"mode": "active"}),
    ]


def test_command_off_ctrl_c_cancels_return(monkeypatch):
    gateway = FakeGateway()

    def interrupted():
        raise KeyboardInterrupt

    monkeypatch.setattr(maintenance, "run_countdown", interrupted)
    assert maintenance.command_off(gateway) == 130
    assert gateway.mode == "maintenance"
    assert gateway.current_state == {"mode": "active"}


def test_failed_post_switch_check_restores_maintenance(monkeypatch):
    gateway = FakeGateway(through=False)
    monkeypatch.setattr(maintenance, "run_countdown", lambda: None)

    with pytest.raises(maintenance.MaintenanceError, match="did not respond"):
        maintenance.command_off(gateway)

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
    gateway = FakeGateway(mode="app")
    assert maintenance.command_off(gateway) == 0
    assert "already OFF" in capsys.readouterr().out
