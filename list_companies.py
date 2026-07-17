#!/usr/bin/env python3
"""List all companies via the internal operator endpoint.

Reads DOMAIN and INTERNAL_API_KEY from the .env next to this script and calls
``GET {DOMAIN}/api/v1/auth/companies``.

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
    domain = env.get("DOMAIN", "").rstrip("/")
    if not domain:
        sys.exit("error: DOMAIN is not set in .env")
    if not domain.startswith(("http://", "https://")):
        domain = "http://" + domain
    return domain


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
