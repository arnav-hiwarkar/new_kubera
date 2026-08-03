#!/usr/bin/env python3
"""Safely switch Kubera's edge gateway into and out of maintenance mode.

Usage:
    python3 maintenance.py on
    python3 maintenance.py status
    python3 maintenance.py off

Run this script on the Docker host from the repository directory.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence


HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / ".maintenance.lock"
RUNTIME_DIR = "/var/lib/kubera-maintenance"
MODE_TARGETS = {
    "app": "/etc/nginx/modes/app.conf",
    "maintenance": "/etc/nginx/modes/maintenance.conf",
}
COUNTDOWN_SECONDS = 10


class MaintenanceError(RuntimeError):
    """An operator-facing error that should not emit a traceback."""


def run(
    command: Sequence[str],
    *,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        kwargs = {"input": input_text} if input_text is not None else {"stdin": subprocess.DEVNULL}
        result = subprocess.run(
            list(command),
            cwd=HERE,
            text=True,
            capture_output=True,
            **kwargs,
        )
    except FileNotFoundError as exc:
        raise MaintenanceError(f"required command not found: {command[0]}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise MaintenanceError(detail or f"command failed: {' '.join(command)}")
    return result


def compose_command() -> list[str]:
    for candidate in (["docker", "compose"], ["docker-compose"]):
        try:
            result = run([*candidate, "version"], check=False)
        except MaintenanceError:
            continue
        if result.returncode == 0:
            return list(candidate)
    raise MaintenanceError("could not find Docker Compose; install Docker Compose v2 and try again")


class Gateway:
    def __init__(self, compose: Sequence[str] | None = None) -> None:
        self.compose = list(compose or compose_command())

    def exec(
        self,
        args: Sequence[str],
        *,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return run(
            [*self.compose, "exec", "-T", "gateway", *args],
            input_text=input_text,
            check=check,
        )

    def ensure_available(self) -> None:
        result = self.exec(["nginx", "-v"], check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise MaintenanceError(
                "the gateway container is not running"
                + (f": {detail}" if detail else "; run `docker compose up -d gateway caddy`")
            )

    def selected_mode(self) -> str:
        result = self.exec(["readlink", f"{RUNTIME_DIR}/active.conf"])
        target = result.stdout.strip()
        for mode, expected in MODE_TARGETS.items():
            if target == expected:
                return mode
        raise MaintenanceError(f"gateway has an unknown active configuration target: {target or '(empty)'}")

    def state(self) -> dict:
        result = self.exec(["cat", f"{RUNTIME_DIR}/state.json"])
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MaintenanceError("maintenance state is malformed JSON") from exc
        if not isinstance(value, dict) or value.get("mode") not in {"active", "closing"}:
            raise MaintenanceError("maintenance state has an unsupported shape")
        return value

    def write_state(self, state: dict) -> None:
        payload = json.dumps(state, separators=(",", ":")) + "\n"
        self.exec(
            [
                "sh",
                "-c",
                f"umask 022; cat > {RUNTIME_DIR}/state.json.next && "
                f"mv -f {RUNTIME_DIR}/state.json.next {RUNTIME_DIR}/state.json",
            ],
            input_text=payload,
        )

    def _point_to(self, mode: str) -> None:
        target = MODE_TARGETS[mode]
        self.exec(
            [
                "sh",
                "-c",
                f"ln -sfn {target} {RUNTIME_DIR}/active.conf.next && "
                f"mv -f {RUNTIME_DIR}/active.conf.next {RUNTIME_DIR}/active.conf",
            ]
        )

    def validate(self, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.exec(["nginx", "-t"], check=check)

    def reload(self, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.exec(["nginx", "-s", "reload"], check=check)

    def switch(self, mode: str) -> None:
        if mode not in MODE_TARGETS:
            raise ValueError(f"unsupported gateway mode: {mode}")
        previous = self.selected_mode()
        self._point_to(mode)
        validation = self.validate(check=False)
        if validation.returncode != 0:
            self._point_to(previous)
            detail = (validation.stderr or validation.stdout).strip()
            raise MaintenanceError(f"Nginx rejected the {mode} configuration; previous mode restored: {detail}")
        reloaded = self.reload(check=False)
        if reloaded.returncode != 0:
            self._point_to(previous)
            self.reload(check=False)
            detail = (reloaded.stderr or reloaded.stdout).strip()
            raise MaintenanceError(f"Nginx reload failed; previous mode restored: {detail}")
        if not self.wait_for_route(mode):
            self._point_to(previous)
            self.reload(check=False)
            self.wait_for_route(previous)
            raise MaintenanceError(
                f"the {mode} route did not begin serving after reload; previous mode restored"
            )

    def readiness(self) -> dict[str, tuple[bool, str]]:
        checks = {
            "frontend": ["wget", "-q", "-T", "5", "-O", "/dev/null", "http://frontend/index.html"],
            "api": ["wget", "-q", "-T", "5", "-O", "/dev/null", "http://api:8000/readyz"],
        }
        results: dict[str, tuple[bool, str]] = {}
        for name, command in checks.items():
            result = self.exec(command, check=False)
            detail = (result.stderr or result.stdout).strip()
            results[name] = (result.returncode == 0, detail)
        return results

    def _route_matches(self, mode: str) -> bool:
        if mode == "app":
            result = self.exec(
                ["wget", "-q", "-T", "2", "-O", "/dev/null", "http://127.0.0.1/"],
                check=False,
            )
            return result.returncode == 0

        result = self.exec(
            ["wget", "-q", "-T", "2", "-O", "-", "http://127.0.0.1/maintenance-state.json"],
            check=False,
        )
        if result.returncode != 0:
            return False
        try:
            state = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False
        return isinstance(state, dict) and state.get("mode") in {"active", "closing"}

    def wait_for_route(self, mode: str, timeout: float = 5.0) -> bool:
        """Allow a graceful reload's new workers a brief moment to accept traffic."""
        deadline = time.monotonic() + timeout
        while True:
            if self._route_matches(mode):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.25)

    def app_through_gateway(self, timeout: float = 5.0) -> bool:
        return self.wait_for_route("app", timeout)


@contextmanager
def operator_lock() -> Iterator[None]:
    with LOCK_PATH.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise MaintenanceError("another maintenance command is already running") from exc
        yield


def domain_url() -> str:
    env_path = HERE / ".env"
    domain = ""
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("DOMAIN="):
                domain = line.partition("=")[2].strip().strip("\"'")
                break
    if not domain:
        return "the configured Kubera domain"
    scheme = "http" if domain.startswith("localhost") else "https"
    return f"{scheme}://{domain}"


def iso_deadline(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    deadline = current + timedelta(seconds=COUNTDOWN_SECONDS)
    return deadline.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run_countdown(
    seconds: int = COUNTDOWN_SECONDS,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    output: Callable[[str], None] = print,
) -> None:
    deadline = monotonic() + seconds
    last_shown: int | None = None
    while True:
        remaining = max(0, math.ceil(deadline - monotonic()))
        if remaining == 0:
            break
        if remaining != last_shown:
            output(f"  Returning in {remaining}…")
            last_shown = remaining
        sleep(min(0.1, max(0.0, deadline - monotonic())))


def command_on(gateway: Gateway) -> int:
    gateway.ensure_available()
    gateway.write_state({"mode": "active"})
    gateway.switch("maintenance")
    print(f"Maintenance mode is ON at {domain_url()}.")
    print("The gateway is independent of the frontend and API; keep gateway and caddy running.")
    return 0


def command_off(gateway: Gateway) -> int:
    gateway.ensure_available()
    if gateway.selected_mode() == "app":
        print("Maintenance mode is already OFF; Kubera is serving the application.")
        return 0

    readiness = gateway.readiness()
    failed = [name for name, (healthy, _) in readiness.items() if not healthy]
    if failed:
        details = []
        for name in failed:
            detail = readiness[name][1]
            details.append(f"{name}{f' ({detail})' if detail else ''}")
        raise MaintenanceError(
            "refusing to restore Kubera because these services are not ready: " + ", ".join(details)
        )

    gateway.write_state({"mode": "closing", "ends_at": iso_deadline()})
    print("Frontend and API are ready. The public return countdown has started:")
    try:
        run_countdown()
    except KeyboardInterrupt:
        gateway.write_state({"mode": "active"})
        print("\nReturn cancelled. Maintenance mode remains ON.")
        return 130

    try:
        gateway.switch("app")
        if not gateway.app_through_gateway():
            raise MaintenanceError("the app did not respond through the gateway after switching")
    except MaintenanceError:
        gateway.switch("maintenance")
        gateway.write_state({"mode": "active"})
        raise

    gateway.write_state({"mode": "active"})
    print("Maintenance mode is OFF. Kubera is live.")
    return 0


def seconds_until(ends_at: object, now: datetime | None = None) -> int | None:
    if not isinstance(ends_at, str):
        return None
    try:
        parsed = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0, math.ceil((parsed - current).total_seconds()))


def command_status(gateway: Gateway) -> int:
    gateway.ensure_available()
    selected = gateway.selected_mode()
    state_error = ""
    try:
        state = gateway.state()
    except MaintenanceError as exc:
        state = {"mode": "invalid"}
        state_error = str(exc)

    display_mode = selected
    if selected == "maintenance" and state.get("mode") == "closing":
        display_mode = "closing"

    validation = gateway.validate(check=False)
    readiness = gateway.readiness()
    print(f"Mode:       {display_mode}")
    if display_mode == "closing":
        remaining = seconds_until(state.get("ends_at"))
        print(f"Countdown:  {remaining if remaining is not None else 'invalid'} seconds remaining")
    print(f"Nginx:      {'valid' if validation.returncode == 0 else 'INVALID'}")
    for name, (healthy, detail) in readiness.items():
        suffix = f" — {detail}" if detail and not healthy else ""
        print(f"{name.title() + ':':<12}{'ready' if healthy else 'NOT READY'}{suffix}")

    inconsistent = bool(state_error) or (selected == "app" and state.get("mode") == "closing")
    if inconsistent:
        print(f"Warning:     {state_error or 'stored countdown state does not match app routing'}")
    return 1 if validation.returncode != 0 or inconsistent else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Toggle Kubera zero-downtime maintenance mode")
    parser.add_argument("command", choices=("on", "off", "status"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with operator_lock():
            gateway = Gateway()
            if args.command == "on":
                return command_on(gateway)
            if args.command == "off":
                return command_off(gateway)
            return command_status(gateway)
    except MaintenanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
