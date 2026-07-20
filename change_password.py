#!/usr/bin/env python3
"""Reset any account's password (operator tool).

Sets a new password for a company user OR an auditor, looked up by email. Uses
the app's own database connection and password hashing, so it must run INSIDE the
api container where the app and its .env are available:

    docker compose exec api python change_password.py                 # prompts for email
    docker compose exec api python change_password.py user@corp.com   # email as argument

The new password is entered twice at a hidden prompt (never passed on the command
line). If the email matches both a company user and an auditor, you choose which.
"""
import asyncio
import getpass
import sys

from app.database import async_session_factory
from app.services import account_admin


def prompt(label: str) -> str:
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\naborted")


def prompt_password() -> str:
    try:
        pw = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm new password: ")
    except (EOFError, KeyboardInterrupt):
        sys.exit("\naborted")
    if not pw:
        sys.exit("error: password cannot be empty")
    if pw != confirm:
        sys.exit("error: passwords did not match")
    return pw


async def run(email: str) -> None:
    async with async_session_factory() as db:
        matches = await account_admin.find_accounts(db, email)
        if not matches:
            sys.exit(f"error: no company user or auditor with email {email!r}")

        if len(matches) == 1:
            target = matches[0]
        else:
            print(f"\n{email} matches multiple accounts:")
            for i, m in enumerate(matches, 1):
                print(f"  [{i}] {m['principal_type']}  name={m['name']!r}  id={m['id']}")
            choice = prompt("Which one? (number): ")
            if not choice.isdigit() or not (1 <= int(choice) <= len(matches)):
                sys.exit("error: invalid choice")
            target = matches[int(choice) - 1]

        print(f"\nResetting password for {target['principal_type']} "
              f"{target['email']} (name={target['name']!r}).")
        password = prompt_password()

        await account_admin.set_password(db, target["principal_type"], target["id"], password)
        await db.commit()
        print(f"\n✓ Password updated for {target['email']}.")


def main() -> None:
    email = sys.argv[1].strip() if len(sys.argv) > 1 else prompt("Email of the account: ")
    if not email:
        sys.exit("error: email cannot be empty")
    asyncio.run(run(email))


if __name__ == "__main__":
    main()
