#!/usr/bin/env python3
"""Create a new company (operator/internal endpoint) via curl.

Reads the API base URL (API_BASE_URL, else DOMAIN) and INTERNAL_API_KEY from the
.env file sitting next to this script, prompts for the company name and admin
email, calls ``POST {base}/api/v1/auth/companies`` with the internal API key, and
prints the one-shot activation key (shown exactly once) plus where to use it.

Usage:
    python3 create_company.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")


def load_env(path):
    """Parse a simple KEY=VALUE .env file (ignores comments/blank lines)."""
    if not os.path.exists(path):
        sys.exit(f"error: no .env file found at {path}")
    env = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                env[key] = value
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


def prompt(label):
    try:
        value = input(label).strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\naborted")
    if not value:
        sys.exit("error: value cannot be empty")
    return value


def main():
    env = load_env(ENV_PATH)

    domain = api_base(env)
    # Where the admin actually opens the app. Always DOMAIN, never API_BASE_URL:
    # that may point straight at the API port, which serves no frontend.
    app_url = env.get("DOMAIN", "").rstrip("/") or domain
    if not app_url.startswith(("http://", "https://")):
        app_url = "http://" + app_url
    internal_key = env.get("INTERNAL_API_KEY", "")
    if not internal_key:
        sys.exit("error: INTERNAL_API_KEY is not set in .env")

    url = f"{domain}/api/v1/auth/companies"

    print(f"\nCreating a new company on {domain}\n")
    name = prompt("Company name : ")
    admin_email = prompt("Admin email  : ")

    body = json.dumps({"name": name, "admin_email": admin_email})

    # Ask curl to append the HTTP status on its own final line so we can split
    # it cleanly from the JSON body.
    result = subprocess.run(
        [
            "curl", "-s", "-S", "-L", "-w", "\n%{http_code}",
            "-X", "POST", url,
            "-H", "Content-Type: application/json",
            "-H", f"X-Internal-API-Key: {internal_key}",
            "-d", body,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"error: curl failed: {result.stderr.strip() or result.returncode}")

    raw = result.stdout.rsplit("\n", 1)
    payload, status = (raw[0], raw[1]) if len(raw) == 2 else (result.stdout, "")

    try:
        data = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        sys.exit(f"error: unexpected response (HTTP {status}):\n{payload}")

    if status != "201":
        detail = data.get("detail", data) if isinstance(data, dict) else data
        sys.exit(f"error: request failed (HTTP {status}): {detail}")

    company = data.get("company", {})
    admin = data.get("admin", {})

    print("\n" + "=" * 56)
    print("  COMPANY CREATED")
    print("=" * 56)
    print(f"  Company name  : {company.get('name')}")
    print(f"  Company ID    : {company.get('id')}")
    print(f"  Admin email   : {admin.get('email')}")
    print(f"  Admin role    : {admin.get('role')}")
    print("-" * 56)
    print(f"  ACTIVATION KEY: {data.get('activation_key')}")
    print(f"  Expires at    : {data.get('activation_expires_at')}")
    print("-" * 56)
    print(f"  Activate here : {app_url}/activate")
    print("  (The admin enters this key + the email above, then sets")
    print("   their own password. The key is shown only once.)")
    print("=" * 56 + "\n")


if __name__ == "__main__":
    main()
