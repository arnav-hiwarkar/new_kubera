#!/usr/bin/env python3
"""Permanently delete a company via the internal operator endpoint.

This is a hard delete. Everything the company owns is destroyed: its users,
DocVault buckets/documents and the encrypted files on disk, audit engagements and
entries, compliance records, assets, sales, KRAs and activity logs. Afterwards a
brand-new company can be created with the same name and the same admin email.

Reads the API base URL (API_BASE_URL, else DOMAIN) and INTERNAL_API_KEY from the
.env next to this script, shows the current companies, asks which one to delete,
and requires you to retype its exact name and then type PURGE before calling
``DELETE {base}/api/v1/auth/companies/{id}``.

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
        # Legacy: companies archived before delete became a real purge. Deleting
        # them for real is how their leftover rows finally go away.
        flag = "  [ARCHIVED — purge to remove]" if c.get("archived") else ""
        print(f"  [{i}] {c.get('name')}  ({c.get('id')})  admin={c.get('admin_email')}{flag}")
    print()

    choice = prompt("Number (or company id) to delete: ")
    target = None
    if choice.isdigit() and 1 <= int(choice) <= len(companies):
        target = companies[int(choice) - 1]
    else:
        target = next((c for c in companies if c.get("id") == choice), None)
    if not target:
        sys.exit("error: no matching company")

    name = target["name"]
    print(f"\n⚠  This PERMANENTLY DELETES '{name}' and everything it owns:")
    print("     • every user account in the company")
    print("     • every DocVault bucket, document and encrypted file on disk")
    print("     • every audit engagement, trial balance, entry, requirement and query")
    print("     • compliance records, assets, sales, KRAs and activity logs")
    print("   Auditor accounts themselves are kept (they may serve other companies).")
    print("   This cannot be undone. The name + admin email become free to reuse.")
    typed = prompt("Retype the company name exactly to confirm: ")
    if typed != name:
        sys.exit("error: name did not match — aborted")
    if prompt("Type PURGE to delete it for good: ") != "PURGE":
        sys.exit("aborted")

    body, status = curl([
        "-X", "DELETE", f"{domain}/api/v1/auth/companies/{target['id']}",
        "-H", header, "-H", "Content-Type: application/json",
        "-d", json.dumps({"confirm_name": typed}),
    ])
    if status == "204":
        print(f"\n✓ Deleted '{name}' and all of its data. The name + admin email are free to reuse.")
    else:
        detail = body
        try:
            detail = json.loads(body).get("detail", body)
        except (json.JSONDecodeError, AttributeError):
            pass
        sys.exit(f"error: delete failed (HTTP {status}): {detail}")


if __name__ == "__main__":
    main()
