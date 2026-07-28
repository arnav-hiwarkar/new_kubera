"""Operator account administration: password reset, user soft-delete, company purge.

The logic lives here (not in the routers) so the FastAPI endpoints and the
repo-root operator scripts (`change_password.py`, `delete_user.py`) share exactly
one implementation. None of these helpers commit — the caller owns the
transaction (`get_db` auto-commits for endpoints; scripts commit explicitly).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.models.company import Company, CompanyUser
from app.models.auditor import Auditor
from app.models.docvault import Document, DocumentVersion, DocumentAccessOverride
from app.models.notification import Notification, RecipientType

COMPANY_USER = "company_user"
AUDITOR = "auditor"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def find_accounts(db: AsyncSession, email: str) -> list[dict]:
    """Every account matching this email, across both principal tables.

    Company-user and auditor emails are unique only within their own table, so the
    same address can exist as both — callers disambiguate on the returned list.

    Company-user email uniqueness only covers LIVE rows, so several soft-deleted
    rows can share an address with the live one. The live row wins; never assume a
    single match (`.scalar_one_or_none()` here would raise `MultipleResultsFound`).
    """
    e = email.strip().lower()
    matches: list[dict] = []

    cu = (
        await db.execute(
            select(CompanyUser)
            .where(func.lower(CompanyUser.email) == e)
            .order_by(CompanyUser.deleted_at.asc().nulls_first())
        )
    ).scalars().first()
    if cu is not None:
        matches.append({
            "principal_type": COMPANY_USER,
            "id": cu.id,
            "name": cu.full_name,
            "email": cu.email,
            "is_active": cu.is_active,
            "deleted_at": cu.deleted_at,
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
            "deleted_at": None,  # auditors are never soft-deleted
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
    """Soft-delete a company user: block login, keep the row (and its real email).

    Marking `deleted_at` blocks login and removes the row from the active-email
    uniqueness index (a partial unique index over `deleted_at IS NULL`), so a new
    account can reuse the same email while this row — and its `full_name` — survives
    so any file/record they created still shows their name. Direct reports are
    detached first because the self-referential manager FK has no cascade.
    """
    await db.execute(
        update(CompanyUser).where(CompanyUser.manager_id == user.id).values(manager_id=None)
    )
    user.is_active = False
    user.deleted_at = _now()


async def purge_company(db: AsyncSession, company: Company) -> list[str]:
    """Hard-delete a company and everything it owns. Returns the file paths to remove.

    Deleting the `companies` row cascades to every tenant-owned table (migrations
    `a2b3c4d5e6f7` + `c8d9e0f1a2b3`), so nothing of the company survives — including
    its users, so a fresh company can reuse the same name and admin email. Two
    tables are unreachable by cascade and are swept explicitly first:

    - `notifications` has no `company_id` and no FKs at all (`recipient_id` is a
      bare UUID discriminated by `recipient_type`).
    - `document_access_overrides.principal_id` is likewise a bare UUID. Rows keyed
      by a purged document cascade away; this catches any keyed by a purged user.

    Global rows are deliberately left alone: `auditors` (an auditor may serve other
    companies), seeded `ledger_groups`/`document_types` (`company_id IS NULL`), and
    `report_templates`.

    Callers own the transaction AND the filesystem: this returns the paths but never
    touches disk, so files are only removed once the delete has actually committed.
    """
    user_ids = (
        await db.execute(select(CompanyUser.id).where(CompanyUser.company_id == company.id))
    ).scalars().all()

    # Collect the on-disk pointers before the rows go away. Everything lives under
    # {VAULT_STORAGE_PATH}/{company_id}/, but return the recorded paths so a caller
    # can also clean up files written outside that tree by older code.
    paths = list(
        (
            await db.execute(
                select(DocumentVersion.storage_path)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(Document.company_id == company.id)
            )
        ).scalars().all()
    )
    if company.logo_path:
        paths.append(company.logo_path)

    if user_ids:
        # Nothing currently emits auditor-recipient notifications; extend this sweep
        # if that changes (the engagement id would come from the JSONB payload).
        await db.execute(
            delete(Notification).where(
                Notification.recipient_type == RecipientType.company_user,
                Notification.recipient_id.in_(user_ids),
            )
        )
        await db.execute(
            delete(DocumentAccessOverride).where(
                DocumentAccessOverride.principal_id.in_(user_ids)
            )
        )

    # A Core DELETE, not `db.delete(company)`: the ORM relationships (`Company.users`,
    # `Company.keys`) have no delete cascade configured, so the unit of work would try
    # to NULL out their NOT NULL `company_id` instead of letting the database cascade.
    await db.execute(delete(Company).where(Company.id == company.id))
    return paths
