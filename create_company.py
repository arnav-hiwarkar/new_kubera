#!/usr/bin/env python3
"""Create a new company (operator/internal endpoint) via curl.

Reads DOMAIN and INTERNAL_API_KEY from the .env file sitting next to this
script, prompts for the company name and admin email, calls
``POST {DOMAIN}/api/v1/auth/companies`` with the internal API key, and prints
the one-shot activation key (shown exactly once) plus where to use it.

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

    domain = env.get("DOMAIN", "").rstrip("/")
    internal_key = env.get("INTERNAL_API_KEY", "")
    if not domain:
        sys.exit("error: DOMAIN is not set in .env")
    if not internal_key:
        sys.exit("error: INTERNAL_API_KEY is not set in .env")
    if not domain.startswith(("http://", "https://")):
        domain = "http://" + domain

    url = f"{domain}/api/v1/auth/companies"

    print(f"\nCreating a new company on {domain}\n")
    name = prompt("Company name : ")
    admin_email = prompt("Admin email  : ")

    body = json.dumps({"name": name, "admin_email": admin_email})

    # Ask curl to append the HTTP status on its own final line so we can split
    # it cleanly from the JSON body.
    result = subprocess.run(
        [
            "curl", "-s", "-S", "-w", "\n%{http_code}",
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
    print(f"  Activate here : {domain}/activate")
    print("  (The admin enters this key + the email above, then sets")
    print("   their own password. The key is shown only once.)")
    print("=" * 56 + "\n")


if __name__ == "__main__":
    main()
