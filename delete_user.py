#!/usr/bin/env python3
"""Soft-delete a company user (operator tool).

Disables the user's login and frees their email for reuse, but KEEPS the row so
any file or record they created still shows their name. Always succeeds, even
when the user owns tenant data. Uses the app's own database connection, so it
must run INSIDE the api container:

    docker compose exec api python delete_user.py                 # prompts for email
    docker compose exec api python delete_user.py user@corp.com   # email as argument

Guards against removing a company's last active admin and requires you to retype
the email to confirm.
"""
import asyncio
import sys

from sqlalchemy import select, func

from app.database import async_session_factory
from app.models.company import Company, CompanyUser, UserRole
from app.services import account_admin


def prompt(label: str) -> str:
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\naborted")


async def run(email: str) -> None:
    async with async_session_factory() as db:
        user = (
            await db.execute(
                select(CompanyUser).where(func.lower(CompanyUser.email) == email.lower())
            )
        ).scalar_one_or_none()
        if user is None:
            sys.exit(f"error: no company user with email {email!r}")

        company = await db.get(Company, user.company_id)

        print("\nMatched user:")
        print(f"  email   : {user.email}")
        print(f"  name    : {user.full_name}")
        print(f"  role    : {user.role.value if hasattr(user.role, 'value') else user.role}")
        print(f"  active  : {'yes' if user.is_active else 'no'}")
        print(f"  company : {company.name if company else user.company_id}")
        print(f"  id      : {user.id}")

        if user.deleted_at is not None:
            sys.exit("\nThis user is already deleted — nothing to do.")

        # Guard: don't strand a company without an active admin.
        if user.role == UserRole.admin and user.is_active:
            active_admins = (
                await db.execute(
                    select(func.count()).select_from(CompanyUser).where(
                        CompanyUser.company_id == user.company_id,
                        CompanyUser.role == UserRole.admin,
                        CompanyUser.is_active.is_(True),
                    )
                )
            ).scalar_one()
            if active_admins <= 1:
                print(f"\n⚠  This is the ONLY active admin of "
                      f"'{company.name if company else user.company_id}'.")
                print("   Deleting it leaves the company with no one who can manage it.")
                if prompt("   Type 'DELETE LAST ADMIN' to proceed anyway: ") != "DELETE LAST ADMIN":
                    sys.exit("aborted")

        print("\n⚠  This deletes the user above: their login is disabled and their email is "
              "freed, but files keep showing their name.")
        if prompt("Retype the email exactly to confirm: ") != user.email:
            sys.exit("error: email did not match — aborted")

        await account_admin.soft_delete_company_user(db, user)
        await db.commit()
        print(f"\n✓ Deleted {email}. Login disabled; email freed for reuse.")


def main() -> None:
    email = sys.argv[1].strip() if len(sys.argv) > 1 else prompt("Email of the user to delete: ")
    if not email:
        sys.exit("error: email cannot be empty")
    asyncio.run(run(email))


if __name__ == "__main__":
    main()
