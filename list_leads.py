#!/usr/bin/env python3
"""List incoming lead inquiries via the internal operator endpoint.

Reads the API base URL (API_BASE_URL, else DOMAIN) and INTERNAL_API_KEY from the
.env next to this script and calls ``GET {base}/api/v1/owner/leads``.

Usage:
    python3 list_leads.py
    python3 list_leads.py --status new
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

    status_arg = ""
    if len(sys.argv) > 2 and sys.argv[1] == "--status":
        status_arg = f"?status={sys.argv[2]}"

    result = subprocess.run(
        [
            "curl", "-s", "-S", "-L", "-w", "\n%{http_code}",
            f"{domain}/api/v1/owner/leads{status_arg}",
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
        print("No leads found.")
        return

    print(f"\n{len(data)} lead(s) found on {domain}:\n")
    for item in data:
        print(f"  [{item.get('status', 'new').upper()}] {item.get('email')}")
        print(f"    id         : {item.get('id')}")
        if item.get("company_name"):
            print(f"    company    : {item.get('company_name')}")
        if item.get("phone"):
            print(f"    phone      : {item.get('phone')}")
        if item.get("entities_count"):
            print(f"    entities   : {item.get('entities_count')}")
        if item.get("notes"):
            print(f"    notes      : {item.get('notes')}")
        print(f"    submitted  : {item.get('created_at')}")
        print()


if __name__ == "__main__":
    main()
