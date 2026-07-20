#!/usr/bin/env python3
"""Archive a company via the internal operator endpoint.

Archiving disables every login for the company and frees its name + admin email
so a fresh company can reuse them; the encrypted tenant data is retained (it is
unrecoverable once archived anyway). Reads DOMAIN and INTERNAL_API_KEY from the
.env next to this script, shows the current companies, asks which one to archive,
and requires you to retype its exact name as a safety rail before calling
``DELETE {DOMAIN}/api/v1/auth/companies/{id}``.

Usage:
    python3 delete_company.py
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


def curl(args):
    result = subprocess.run(
        ["curl", "-s", "-S", "-L", "-w", "\n%{http_code}", *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"error: curl failed: {result.stderr.strip() or result.returncode}")
    body, _, status = result.stdout.rpartition("\n")
    return body, status


def prompt(label):
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\naborted")


def main():
    env = load_env(ENV_PATH)
    domain = api_base(env)
    key = env.get("INTERNAL_API_KEY", "")
    if not key:
        sys.exit("error: INTERNAL_API_KEY is not set in .env")
    header = f"X-Internal-API-Key: {key}"

    body, status = curl([f"{domain}/api/v1/auth/companies", "-H", header])
    if status != "200":
        sys.exit(f"error: could not list companies (HTTP {status}): {body}")
    companies = json.loads(body) if body else []
    if not companies:
        print("No companies to delete.")
        return

    print(f"\nCompanies on {domain}:\n")
    for i, c in enumerate(companies, 1):
        flag = "  [ARCHIVED]" if c.get("archived") else ""
        print(f"  [{i}] {c.get('name')}  ({c.get('id')})  admin={c.get('admin_email')}{flag}")
    print()

    choice = prompt("Number (or company id) to archive: ")
    target = None
    if choice.isdigit() and 1 <= int(choice) <= len(companies):
        target = companies[int(choice) - 1]
    else:
        target = next((c for c in companies if c.get("id") == choice), None)
    if not target:
        sys.exit("error: no matching company")

    name = target["name"]
    if target.get("archived"):
        sys.exit(f"'{name}' is already archived.")
    print(f"\n⚠  This ARCHIVES '{name}': all its logins are disabled and its name + admin "
          f"email are freed for reuse. Encrypted data is retained.")
    typed = prompt(f"Retype the company name exactly to confirm: ")
    if typed != name:
        sys.exit("error: name did not match — aborted")

    body, status = curl([
        "-X", "DELETE", f"{domain}/api/v1/auth/companies/{target['id']}",
        "-H", header, "-H", "Content-Type: application/json",
        "-d", json.dumps({"confirm_name": typed}),
    ])
    if status == "204":
        print(f"\n✓ Archived '{name}'. Logins disabled; name + admin email freed for reuse.")
    else:
        detail = body
        try:
            detail = json.loads(body).get("detail", body)
        except (json.JSONDecodeError, AttributeError):
            pass
        sys.exit(f"error: archive failed (HTTP {status}): {detail}")


if __name__ == "__main__":
    main()
