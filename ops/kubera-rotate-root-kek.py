#!/usr/bin/env python3
"""Rotate ROOT_MASTER_KEK without re-encrypting a single document.

Kubera wraps keys in a hierarchy:

    ROOT_MASTER_KEK  ->  per-company KEK (company_keys.encrypted_kek)
                     ->  per-document DEK (encrypted under the company KEK)
                     ->  document ciphertext (encrypted under the DEK)

Only the first link involves the root KEK, so rotating it means re-wrapping one
row per company. Documents, DEKs and company KEKs themselves are untouched — the
same plaintext company KEK comes out, just sealed under a new root key.

Run this if a deployment ever ran with the all-zero .env.example placeholder KEK,
or any time you need to rotate the root key.

This script deliberately does NOT import `app`: app.config refuses to load an
insecure configuration, which is exactly the situation you are here to fix.

Usage (on the server, from the repository directory):

    # 1. See what would change — this is the default, nothing is written.
    docker compose run --rm --no-deps --entrypoint python api \\
        ops/kubera-rotate-root-kek.py --old-kek <current-hex> --new-kek <new-hex>

    # 2. Apply.
    docker compose run --rm --no-deps --entrypoint python api \\
        ops/kubera-rotate-root-kek.py --old-kek <current-hex> --new-kek <new-hex> --apply

    # 3. Put the new key in .env as ROOT_MASTER_KEK, then restart:
    docker compose up -d api worker beat

Generate a new key with:

    python -c "import secrets; print(secrets.token_hex(32))"

BACK UP THE DATABASE FIRST (ops/kubera-export.sh), and keep the OLD key until you
have confirmed a tenant document opens. Losing both keys means losing the vault.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

HEX64 = re.compile(r"\A[0-9a-fA-F]{64}\Z")


def die(message: str) -> None:
    print(f"[rotate-root-kek] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_kek(value: str, label: str) -> bytes:
    if not HEX64.match(value):
        die(f"{label} must be exactly 64 hexadecimal characters (32 bytes)")
    return bytes.fromhex(value)


async def rotate(old_kek: bytes, new_kek: bytes, apply: bool) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        die("DATABASE_URL is not set (run this inside the api container)")

    old_aes = AESGCM(old_kek)
    new_aes = AESGCM(new_kek)

    engine = create_async_engine(database_url, echo=False)
    try:
        async with engine.begin() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT ck.id, ck.company_id, ck.encrypted_kek, ck.kek_nonce, "
                        "       c.name "
                        "FROM company_keys ck "
                        "JOIN companies c ON c.id = ck.company_id "
                        "ORDER BY c.name"
                    )
                )
            ).all()

            if not rows:
                print("[rotate-root-kek] No company keys found — nothing to rotate.")
                return 0

            print(f"[rotate-root-kek] {len(rows)} company key(s) to re-wrap:\n")
            updates: list[tuple[bytes, bytes, object]] = []

            for row in rows:
                key_id, company_id, encrypted_kek, kek_nonce, company_name = row
                try:
                    raw_kek = old_aes.decrypt(bytes(kek_nonce), bytes(encrypted_kek), None)
                except InvalidTag:
                    die(
                        f"company {company_name!r} ({company_id}): its KEK does not "
                        "decrypt under --old-kek. Either the old key is wrong, or "
                        "companies were created under different root keys. Nothing "
                        "has been written."
                    )

                new_nonce = os.urandom(12)
                new_encrypted = new_aes.encrypt(new_nonce, raw_kek, None)

                # Prove the re-wrap round-trips before we consider writing it.
                if new_aes.decrypt(new_nonce, new_encrypted, None) != raw_kek:
                    die(f"company {company_name!r}: re-wrap verification failed")

                updates.append((new_encrypted, new_nonce, key_id))
                print(f"  ok  {company_name}  ({company_id})")

            if not apply:
                print(
                    "\n[rotate-root-kek] DRY RUN — every key re-wrapped and verified "
                    "in memory, nothing written.\n"
                    "                  Re-run with --apply to commit."
                )
                # Nothing was written: we simply never issued an UPDATE.
                return 0

            for new_encrypted, new_nonce, key_id in updates:
                await conn.execute(
                    text(
                        "UPDATE company_keys "
                        "SET encrypted_kek = :ek, kek_nonce = :n, updated_at = now() "
                        "WHERE id = :id"
                    ),
                    {"ek": new_encrypted, "n": new_nonce, "id": key_id},
                )

            print(
                f"\n[rotate-root-kek] Committed {len(updates)} re-wrapped key(s).\n"
                "\nNEXT STEPS — the application is now broken until you do this:\n"
                "  1. Set ROOT_MASTER_KEK in .env to the NEW key.\n"
                "  2. docker compose up -d api worker beat\n"
                "  3. Open a tenant document to confirm decryption works.\n"
                "  4. Only then destroy your copy of the old key.\n"
            )
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-wrap every company KEK under a new ROOT_MASTER_KEK.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--old-kek",
        required=True,
        help="Current root KEK, 64 hex chars (the value currently in .env).",
    )
    parser.add_argument(
        "--new-kek",
        required=True,
        help="Replacement root KEK, 64 hex chars.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the re-wrapped keys. Without this the script is a dry run.",
    )
    args = parser.parse_args()

    old_kek = parse_kek(args.old_kek, "--old-kek")
    new_kek = parse_kek(args.new_kek, "--new-kek")

    if old_kek == new_kek:
        die("--old-kek and --new-kek are identical")

    if args.apply:
        print(
            "[rotate-root-kek] APPLY mode. Have you taken a database backup "
            "(ops/kubera-export.sh)?\n"
        )

    return asyncio.run(rotate(old_kek, new_kek, args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
