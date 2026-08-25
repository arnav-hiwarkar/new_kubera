import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    INTERNAL_API_KEY, init_company, create_test_company, get_company_token,
    create_test_auditor, get_auditor_token,
)
from app.config import get_settings
from app.models.activity_log import ActivityLog
from app.models.auditease import (
    AuditEngagement, AuditEntry, AuditEntryLine, Query, QueryMessage,
    RequirementRequest, TrialBalanceAccount,
)
from app.models.company import Company, CompanyKey, CompanyUser
from app.models.docvault import Bucket, Document, DocumentVersion
from app.models.notification import Notification, RecipientType
from app.services import account_admin


async def _create_user(client, admin_token, *, email, password, full_name="Emp User", role="employee"):
    resp = await client.post(
        "/api/v1/users",
        json={"email": email, "password": password, "full_name": full_name, "role": role},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- Soft-delete user -----------------------------------------------------------

@pytest.mark.asyncio
async def test_soft_delete_user_disables_login_frees_email_keeps_row(
    client: AsyncClient, db: AsyncSession
):
    """Deleting a user must succeed even when they own data, disable their login,
    keep the row (with its real email + name), and free the email for reuse."""
    await create_test_company(client, name="SoftCo", email="admin@softco.com")
    admin_token = await get_company_token(client, email="admin@softco.com")

    emp = await _create_user(client, admin_token, email="emp@softco.com", password="emppass123")
    emp_id = uuid.UUID(emp["id"])
    company_id = uuid.UUID(emp["company_id"])

    # The employee can log in before deletion.
    login = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "emp@softco.com", "password": "emppass123"},
    )
    assert login.status_code == 200

    # Attach work the employee "owns": a bucket whose created_by FK (no ondelete)
    # would make a hard delete fail with a 409.
    db.add(Bucket(company_id=company_id, name="Emp Bucket", created_by=emp_id))
    await db.commit()

    # Soft-delete via the admin endpoint — must succeed despite the owned bucket.
    resp = await client.delete(
        f"/api/v1/users/{emp_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204, resp.text

    # Login is now blocked.
    login = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "emp@softco.com", "password": "emppass123"},
    )
    assert login.status_code == 401

    # The row survives: real email + name kept, marked deleted/inactive.
    row = (await db.execute(select(CompanyUser).where(CompanyUser.id == emp_id))).scalar_one()
    assert row.is_active is False
    assert row.deleted_at is not None
    assert row.full_name == "Emp User"
    assert row.email == "emp@softco.com"

    # The Directory listing must still load (regression: a soft-deleted row used to
    # 500 the whole list) and include the deleted user, marked deleted/inactive.
    listing = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert listing.status_code == 200, listing.text
    deleted_row = next(u for u in listing.json() if u["id"] == emp["id"])
    assert deleted_row["is_active"] is False
    assert deleted_row["deleted_at"] is not None

    # The attached bucket still points at the surviving row (name still resolvable).
    bucket = (await db.execute(select(Bucket).where(Bucket.created_by == emp_id))).scalar_one()
    assert bucket.created_by == emp_id

    # The email is free — a brand-new (live) user can reuse it.
    again = await _create_user(client, admin_token, email="emp@softco.com", password="newpass123", full_name="New Hire")
    assert again["id"] != emp["id"]


@pytest.mark.asyncio
async def test_deactivate_then_reactivate_user(client: AsyncClient):
    """Deactivate blocks login and is reversible; a deleted user can't be reactivated."""
    await create_test_company(client, name="DeactCo", email="admin@deactco.com")
    admin_token = await get_company_token(client, email="admin@deactco.com")
    hdr = {"Authorization": f"Bearer {admin_token}"}

    emp = await _create_user(client, admin_token, email="d@deactco.com", password="emppass123")
    emp_id = emp["id"]

    # Deactivate -> login blocked.
    r = await client.patch(f"/api/v1/users/{emp_id}/deactivate", headers=hdr)
    assert r.status_code == 200 and r.json()["is_active"] is False
    blocked = await client.post("/api/v1/auth/company/login", json={"email": "d@deactco.com", "password": "emppass123"})
    assert blocked.status_code == 401

    # Reactivate -> login works again.
    r = await client.patch(f"/api/v1/users/{emp_id}/reactivate", headers=hdr)
    assert r.status_code == 200 and r.json()["is_active"] is True
    ok = await client.post("/api/v1/auth/company/login", json={"email": "d@deactco.com", "password": "emppass123"})
    assert ok.status_code == 200

    # Delete, then reactivate must be refused (409).
    assert (await client.delete(f"/api/v1/users/{emp_id}", headers=hdr)).status_code == 204
    refused = await client.patch(f"/api/v1/users/{emp_id}/reactivate", headers=hdr)
    assert refused.status_code == 409


# --- Password reset -------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_password_company_user(client: AsyncClient, db: AsyncSession):
    await create_test_company(client, name="PwCo", email="admin@pwco.com", password="oldpass123")

    matches = await account_admin.find_accounts(db, "admin@pwco.com")
    assert len(matches) == 1 and matches[0]["principal_type"] == account_admin.COMPANY_USER
    await account_admin.set_password(db, matches[0]["principal_type"], matches[0]["id"], "brandnew123")
    await db.commit()

    # New password works; old one does not.
    ok = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "admin@pwco.com", "password": "brandnew123"},
    )
    assert ok.status_code == 200
    bad = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "admin@pwco.com", "password": "oldpass123"},
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_set_password_auditor(client: AsyncClient, db: AsyncSession):
    await create_test_auditor(client, email="aud@x.com", password="oldpass123")

    matches = await account_admin.find_accounts(db, "aud@x.com")
    assert len(matches) == 1 and matches[0]["principal_type"] == account_admin.AUDITOR
    await account_admin.set_password(db, matches[0]["principal_type"], matches[0]["id"], "brandnew123")
    await db.commit()

    ok = await client.post(
        "/api/v1/auth/auditor/login",
        json={"email": "aud@x.com", "password": "brandnew123"},
    )
    assert ok.status_code == 200


# --- Purge company --------------------------------------------------------------

INTERNAL_HEADERS = {"X-Internal-Api-Key": INTERNAL_API_KEY}

TB_CSV = (
    b"Code,Name,Opening,Debit,Credit,Closing\n"
    b"A1,Cash,100,50,0,150\n"
    b"L1,Loan,-100,0,50,-150\n"
)
TB_MAP = {
    "ledger_code": "Code", "ledger_name": "Name", "opening_balance": "Opening",
    "debit": "Debit", "credit": "Credit", "closing_balance": "Closing",
}


async def _purge(client: AsyncClient, company_id, confirm_name: str):
    return await client.request(
        "DELETE",
        f"/api/v1/auth/companies/{company_id}",
        json={"confirm_name": confirm_name},
        headers=INTERNAL_HEADERS,
    )


async def _build_tenant_data(client: AsyncClient, co_headers, aud_headers):
    """Populate one company with data in every table a purge has to reach. Returns
    the engagement + document ids."""
    eng_id = (
        await client.post(
            "/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co_headers
        )
    ).json()["id"]

    tb = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/trial-balance/import",
        data={"column_map": json.dumps(TB_MAP)},
        files={"file": ("tb.csv", TB_CSV, "text/csv")},
        headers=co_headers,
    )
    assert tb.status_code == 200, tb.text
    ledgers = tb.json()["accounts"]

    # A bucket + a document with two versions => two encrypted files on disk.
    bucket_id = (
        await client.post(
            "/api/v1/docvault/buckets", json={"name": "Financials"}, headers=co_headers
        )
    ).json()["id"]
    doc = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Ledger", "bucket_id": bucket_id},
        files={"file": ("v1.txt", b"version one", "text/plain")},
        headers=co_headers,
    )
    assert doc.status_code == 201, doc.text
    doc_id = doc.json()["id"]
    await client.post(
        f"/api/v1/docvault/documents/{doc_id}/versions",
        files={"file": ("v2.txt", b"version two", "text/plain")},
        headers=co_headers,
    )

    # Auditor side: grant, audit entry + lines, requirement fulfilled by the
    # document, and a query message attaching it. These are the FKs that used to
    # block a hard delete.
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "purgeaud@x.com"}, headers=co_headers,
    )
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    entry = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/entries",
        json={
            "description": "Adjusting entry",
            "lines": [
                {"ledger_id": ledgers[0]["id"], "side": "debit", "amount": 100},
                {"ledger_id": ledgers[1]["id"], "side": "credit", "amount": 100},
            ],
        },
        headers=aud_headers,
    )
    assert entry.status_code == 201, entry.text

    req = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"title": "Bank Statements", "description": "Provide them"},
        headers=aud_headers,
    )
    assert req.status_code == 200, req.text
    await client.patch(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req.json()['id']}/fulfill",
        json={"document_id": doc_id}, headers=co_headers,
    )

    query = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/queries",
        data={"initial_message": "What is this?"}, headers=aud_headers,
    )
    assert query.status_code == 200, query.text
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/queries/{query.json()['id']}/messages",
        data={"text": "Here it is", "attached_document_id": doc_id}, headers=co_headers,
    )

    return eng_id, doc_id


@pytest.mark.asyncio
async def test_purge_company_deletes_everything_and_frees_name_and_email(
    client: AsyncClient, db: AsyncSession
):
    """The operator delete is a hard delete: every tenant row and every encrypted
    file goes, and the same name + admin email can be used from scratch afterwards
    — including activation and login, which used to 500 on the duplicate rows."""
    data = await create_test_company(client, name="PurgeCo", email="purge@x.com", password="adminpass123")
    company_id = uuid.UUID(data["company"]["id"])
    admin_token = await get_company_token(client, email="purge@x.com", password="adminpass123")
    co_headers = {"Authorization": f"Bearer {admin_token}"}
    await _create_user(client, admin_token, email="u2@purgeco.com", password="u2pass123")

    await create_test_auditor(client, email="purgeaud@x.com", password="audpass123")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='purgeaud@x.com', password='audpass123')}"}

    eng_id, doc_id = await _build_tenant_data(client, co_headers, aud_headers)

    # A notification for a company user: no company_id and no FK, so only the
    # explicit sweep in purge_company reaches it.
    user_ids = (
        await db.execute(select(CompanyUser.id).where(CompanyUser.company_id == company_id))
    ).scalars().all()
    db.add(Notification(
        recipient_type=RecipientType.company_user,
        recipient_id=user_ids[0],
        type="test.event",
        payload={"engagement_id": eng_id},
    ))
    await db.commit()

    vault_dir = Path(get_settings().VAULT_STORAGE_PATH) / str(company_id)
    assert vault_dir.is_dir(), "uploads should have created the company's vault directory"

    resp = await _purge(client, company_id, "PurgeCo")
    assert resp.status_code == 204, resp.text

    # Nothing of the company is left in any table.
    db.expire_all()
    assert (await db.execute(select(Company).where(Company.id == company_id))).first() is None
    for model in (CompanyUser, CompanyKey, ActivityLog, Bucket, Document, AuditEngagement,
                  TrialBalanceAccount):
        remaining = (
            await db.execute(select(func.count()).select_from(model).where(model.company_id == company_id))
        ).scalar_one()
        assert remaining == 0, f"{model.__tablename__} still has {remaining} row(s)"
    for model, column in ((DocumentVersion, DocumentVersion.document_id),
                          (AuditEntry, AuditEntry.engagement_id),
                          (RequirementRequest, RequirementRequest.engagement_id),
                          (Query, Query.engagement_id)):
        assert (await db.execute(select(func.count()).select_from(model))).scalar_one() == 0, \
            f"{model.__tablename__} should be empty"
    assert (await db.execute(select(func.count()).select_from(AuditEntryLine))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(QueryMessage))).scalar_one() == 0
    assert (
        await db.execute(
            select(func.count()).select_from(Notification)
            .where(Notification.recipient_id.in_(user_ids))
        )
    ).scalar_one() == 0

    # The encrypted files are gone from disk.
    assert not vault_dir.exists(), "the company's vault directory should be removed"

    # The auditor account survives — it may serve other companies.
    aud_login = await client.post(
        "/api/v1/auth/auditor/login",
        json={"email": "purgeaud@x.com", "password": "audpass123"},
    )
    assert aud_login.status_code == 200

    # The company is no longer listed, and nobody can log in.
    listing = await client.get("/api/v1/auth/companies", headers=INTERNAL_HEADERS)
    assert all(c["id"] != str(company_id) for c in listing.json())
    for email, pw in (("purge@x.com", "adminpass123"), ("u2@purgeco.com", "u2pass123")):
        blocked = await client.post(
            "/api/v1/auth/company/login", json={"email": email, "password": pw}
        )
        assert blocked.status_code == 401, f"{email} should not be able to log in"

    # The whole point: same name, same admin email, fully usable from scratch.
    fresh = await create_test_company(
        client, name="PurgeCo", email="purge@x.com", password="newpass123"
    )
    assert uuid.UUID(fresh["company"]["id"]) != company_id
    token = await get_company_token(client, email="purge@x.com", password="newpass123")

    # ...and it starts empty — no documents or engagements from the old company.
    new_headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/docvault/documents", headers=new_headers)).json() == []
    assert (await client.get("/api/v1/auditease/engagements", headers=new_headers)).json() == []


@pytest.mark.asyncio
async def test_purge_company_wrong_name_and_unknown_id(client: AsyncClient):
    data = await create_test_company(client, name="GuardCo", email="guard@x.com")
    company_id = data["company"]["id"]

    assert (await _purge(client, company_id, "guardco")).status_code == 400
    assert (await _purge(client, uuid.uuid4(), "GuardCo")).status_code == 404
    # Still there, and still able to log in.
    assert (await client.post(
        "/api/v1/auth/company/login",
        json={"email": "guard@x.com", "password": "testpass123"},
    )).status_code == 200

    assert (await _purge(client, company_id, "GuardCo")).status_code == 204
    # Purging again is a 404 — the row is genuinely gone.
    assert (await _purge(client, company_id, "GuardCo")).status_code == 404


@pytest.mark.asyncio
async def test_purge_company_works_on_legacy_archived_company(
    client: AsyncClient, db: AsyncSession
):
    """Companies archived before the purge existed must still be removable, so their
    leftover soft-deleted user rows stop shadowing a reused email."""
    data = await create_test_company(client, name="LegacyCo", email="legacy@x.com")
    company_id = uuid.UUID(data["company"]["id"])

    # Reproduce the old archive_company state by hand.
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one()
    company.archived_at = datetime.now(timezone.utc)
    for user in (
        await db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    ).scalars().all():
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    assert (await _purge(client, company_id, "LegacyCo")).status_code == 204

    db.expire_all()
    assert (
        await db.execute(
            select(func.count()).select_from(CompanyUser)
            .where(func.lower(CompanyUser.email) == "legacy@x.com")
        )
    ).scalar_one() == 0

    # The freed email now activates and logs in instead of 500ing on duplicate rows.
    await create_test_company(client, name="LegacyCo", email="legacy@x.com", password="newpass123")
    assert (await client.post(
        "/api/v1/auth/company/login",
        json={"email": "legacy@x.com", "password": "newpass123"},
    )).status_code == 200


@pytest.mark.asyncio
async def test_activate_and_login_tolerate_soft_deleted_namesake(client: AsyncClient):
    """A soft-deleted user row must not shadow a live account with the same email:
    both lookups used to raise MultipleResultsFound and return a 500."""
    await create_test_company(client, name="ShadowCo", email="shadow@x.com", password="adminpass123")
    admin_token = await get_company_token(client, email="shadow@x.com", password="adminpass123")
    emp = await _create_user(client, admin_token, email="dup@x.com", password="emppass123")
    assert (await client.delete(
        f"/api/v1/users/{emp['id']}", headers={"Authorization": f"Bearer {admin_token}"}
    )).status_code == 204

    # Reuse the freed email as a new company's admin: activation and login must work
    # even though the soft-deleted row still holds the same address.
    data = await init_company(client, name="DupCo", email="dup@x.com")
    activate = await client.post(
        "/api/v1/auth/company/activate",
        json={
            "email": "dup@x.com",
            "activation_key": data["activation_key"],
            "password": "duppass123",
            "full_name": "Dup Admin",
        },
    )
    assert activate.status_code == 204, activate.text
    login = await client.post(
        "/api/v1/auth/company/login", json={"email": "dup@x.com", "password": "duppass123"}
    )
    assert login.status_code == 200, login.text
    assert login.json()["full_name"] == "Dup Admin"
