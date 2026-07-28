#!/usr/bin/env python3
"""List all companies via the internal operator endpoint.

Reads the API base URL (API_BASE_URL, else DOMAIN) and INTERNAL_API_KEY from the
.env next to this script and calls ``GET {base}/api/v1/auth/companies``.

Usage:
    python3 list_companies.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")


def load_env(path):
    if not os.path.exists(path):
        sys.exit(f"error: no .env file found at {path}")
    env = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def api_base(env):
    """Base URL for the internal API: API_BASE_URL if set, else DOMAIN.

    On a local stack DOMAIN is `localhost`, where Caddy auto-upgrades http to https
    using its own internal CA — curl then rejects the certificate (error 60). Set
    API_BASE_URL=http://localhost:8000 to talk to the API's published port and skip
    TLS entirely. The process environment wins over .env.
    """
    base = (os.environ.get("API_BASE_URL") or env.get("API_BASE_URL", "")).rstrip("/")
    if not base:
        base = env.get("DOMAIN", "").rstrip("/")
    if not base:
        sys.exit("error: neither API_BASE_URL nor DOMAIN is set in .env")
    if not base.startswith(("http://", "https://")):
        base = "http://" + base
    return base


def main():
    env = load_env(ENV_PATH)
    domain = api_base(env)
    key = env.get("INTERNAL_API_KEY", "")
    if not key:
        sys.exit("error: INTERNAL_API_KEY is not set in .env")

    result = subprocess.run(
        [
            "curl", "-s", "-S", "-L", "-w", "\n%{http_code}",
            f"{domain}/api/v1/auth/companies",
            "-H", f"X-Internal-API-Key: {key}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"error: curl failed: {result.stderr.strip() or result.returncode}")

    body, _, status = result.stdout.rpartition("\n")
    try:
        data = json.loads(body) if body else []
    except json.JSONDecodeError:
        sys.exit(f"error: unexpected response (HTTP {status}):\n{body}")

    if status != "200":
        detail = data.get("detail", data) if isinstance(data, dict) else data
        sys.exit(f"error: request failed (HTTP {status}): {detail}")

    if not data:
        print("No companies found.")
        return

    print(f"\n{len(data)} company(ies) on {domain}\n")
    for c in data:
        flags = []
        if c.get("activation_pending"):
            flags.append("activation-pending")
        if not c.get("admin_active"):
            flags.append("admin-inactive")
        if c.get("profile_completed"):
            flags.append("profile-complete")
        print(f"  {c.get('name')}")
        print(f"    id          : {c.get('id')}")
        print(f"    admin email : {c.get('admin_email')}")
        print(f"    created     : {c.get('created_at')}")
        print(f"    status      : {', '.join(flags) if flags else '—'}")
        print()


if __name__ == "__main__":
    main()
