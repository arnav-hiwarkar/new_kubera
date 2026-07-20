"""Operator account administration: password reset, user soft-delete, company archive.

The logic lives here (not in the routers) so the FastAPI endpoints and the
repo-root operator scripts (`change_password.py`, `delete_user.py`) share exactly
one implementation. None of these helpers commit — the caller owns the
transaction (`get_db` auto-commits for endpoints; scripts commit explicitly).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.models.company import Company, CompanyUser
from app.models.auditor import Auditor

COMPANY_USER = "company_user"
AUDITOR = "auditor"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def find_accounts(db: AsyncSession, email: str) -> list[dict]:
    """Every account matching this email, across both principal tables.

    Company-user and auditor emails are unique only within their own table, so the
    same address can exist as both — callers disambiguate on the returned list.
    """
    e = email.strip().lower()
    matches: list[dict] = []

    cu = (
        await db.execute(select(CompanyUser).where(func.lower(CompanyUser.email) == e))
    ).scalar_one_or_none()
    if cu is not None:
        matches.append({
            "principal_type": COMPANY_USER,
            "id": cu.id,
            "name": cu.full_name,
            "email": cu.email,
            "is_active": cu.is_active,
        })

    aud = (
        await db.execute(select(Auditor).where(func.lower(Auditor.email) == e))
    ).scalar_one_or_none()
    if aud is not None:
        matches.append({
            "principal_type": AUDITOR,
            "id": aud.id,
            "name": aud.name,
            "email": aud.email,
            "is_active": True,  # auditors have no active flag
        })

    return matches


async def set_password(db: AsyncSession, principal_type: str, account_id: uuid.UUID, new_password: str) -> None:
    """Overwrite an account's password hash. Raises ValueError if not found."""
    if not new_password:
        raise ValueError("password cannot be empty")

    if principal_type == COMPANY_USER:
        model = CompanyUser
    elif principal_type == AUDITOR:
        model = Auditor
    else:
        raise ValueError(f"unknown principal_type {principal_type!r}")

    row = (await db.execute(select(model).where(model.id == account_id))).scalar_one_or_none()
    if row is None:
        raise ValueError(f"{principal_type} {account_id} not found")
    row.hashed_password = hash_password(new_password)


async def soft_delete_company_user(db: AsyncSession, user: CompanyUser) -> None:
    """Soft-delete a company user: block login, free their email, keep the row.

    The row (and full_name) survives so any file/record they created still shows
    their name. The email is released to a collision-proof sentinel so a new
    account can reuse the original address. Direct reports are detached first
    because the self-referential manager FK has no cascade.
    """
    await db.execute(
        update(CompanyUser).where(CompanyUser.manager_id == user.id).values(manager_id=None)
    )
    user.is_active = False
    user.deleted_at = _now()
    user.email = f"deleted+{user.id}@deleted.invalid"


async def archive_company(db: AsyncSession, company: Company) -> None:
    """Archive a company: disable every login and free its admin email for reuse.

    Encrypted tenant data is intentionally retained (it is unrecoverable once
    archived anyway). The company name was never unique; the only reuse blocker is
    the globally-unique company-user email, so every user's email is freed here.
    Raises ValueError if the company is already archived.
    """
    if company.archived_at is not None:
        raise ValueError("company is already archived")

    company.archived_at = _now()
    users = (
        await db.execute(select(CompanyUser).where(CompanyUser.company_id == company.id))
    ).scalars().all()
    for u in users:
        u.is_active = False
        u.email = f"archived+{u.id}@archived.invalid"
