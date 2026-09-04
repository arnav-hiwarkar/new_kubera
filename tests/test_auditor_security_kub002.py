import urllib.parse
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func

from app.models.auditease import (
    AuditEngagement, AuditorEngagementGrant, PendingAuditorInvite,
    GrantStatus
)
from app.models.auditor import Auditor
from tests.conftest import create_test_company, get_company_token, TestSessionLocal
from tests.test_auditease import make_engagement


def _extract_token_from_mock(mock_send_task) -> str:
    """Helper to extract plaintext token from mock email task action url."""
    message_dict = mock_send_task.call_args[0][0]
    action_url = message_dict["template_context"]["action_button"]["url"]
    parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(action_url).query)
    return parsed_qs["token"][0]


# --------------------------------------------------------------------------
# 1. Anti-Test: Missing Token Registration (Takeover Attempt)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_anti_exploit_missing_token_registration_rejected(mock_email, client: AsyncClient):
    """An attacker knowing a pending invite email attempts self-registration without a token."""
    mock_email.return_value = MagicMock(id="task-1")
    await create_test_company(client, email="takeover_co@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='takeover_co@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)

    target_email = "target_victim@auditing.com"
    inv_res = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": target_email},
        headers=co_headers,
    )
    assert inv_res.status_code == 200

    # Attacker tries to register target_email without invite_token (missing field)
    resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": target_email,
            "password": "Valid1!Attacker",
            "name": "Attacker",
        },
    )
    assert resp.status_code == 422, f"Expected 422 for missing token, got {resp.status_code}: {resp.text}"

    # Verify no auditor account was created
    async with TestSessionLocal() as db:
        aud = (await db.execute(select(Auditor).where(func.lower(Auditor.email) == target_email))).scalar_one_or_none()
        assert aud is None


# --------------------------------------------------------------------------
# 2. Anti-Test: Invalid / Guessing Token Registration (Takeover Attempt)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_anti_exploit_invalid_token_rejected(mock_email, client: AsyncClient):
    """An attacker attempts to register by guessing an invite token."""
    mock_email.return_value = MagicMock(id="task-2")
    await create_test_company(client, email="guess_co@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='guess_co@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)

    target_email = "target_guess@auditing.com"
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": target_email},
        headers=co_headers,
    )

    # Attacker tries with guessed token
    resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": target_email,
            "password": "Valid1!Attacker",
            "name": "Attacker",
            "invite_token": "totally-fake-token-guess-12345",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired invitation details"

    async with TestSessionLocal() as db:
        aud = (await db.execute(select(Auditor).where(func.lower(Auditor.email) == target_email))).scalar_one_or_none()
        assert aud is None


# --------------------------------------------------------------------------
# 3. Anti-Test: Legacy Dead __pending__ Takeover Attempt
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_anti_exploit_dead_pending_takeover_blocked(client: AsyncClient):
    """If an existing auditor row has hashed_password='__pending__', registration
    must NOT overwrite it or allow takeover. It must strictly return 409 Conflict."""
    legacy_email = "legacy_pending@firm.com"
    async with TestSessionLocal() as db:
        legacy_auditor = Auditor(
            email=legacy_email,
            hashed_password="__pending__",
            name="Ghost Auditor",
        )
        db.add(legacy_auditor)
        await db.commit()

    resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": legacy_email,
            "password": "Valid1!Pass",
            "name": "Takeover Attempt",
            "invite_token": "some-token",
        },
    )
    assert resp.status_code == 409, f"Expected 409 Conflict, got {resp.status_code}: {resp.text}"
    assert resp.json()["detail"] == "Email already registered"

    # Verify password was NOT changed to the attacker's password
    async with TestSessionLocal() as db:
        aud = (await db.execute(select(Auditor).where(func.lower(Auditor.email) == legacy_email))).scalar_one()
        assert aud.hashed_password == "__pending__"
        assert aud.name == "Ghost Auditor"


# --------------------------------------------------------------------------
# 4. Anti-Test: Cross-Account Token Replay / Hijacking
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_anti_exploit_cross_account_token_hijack_fails(mock_email, client: AsyncClient):
    """An attacker attempts to use a token intended for victim@firm.com to register attacker@evil.com."""
    mock_email.return_value = MagicMock(id="task-4")
    await create_test_company(client, email="co_cross@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co_cross@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)

    victim_email = "victim_auditor@firm.com"
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": victim_email},
        headers=co_headers,
    )
    victim_token = _extract_token_from_mock(mock_email)

    # Attacker tries to register their own email using victim's token
    attacker_email = "attacker@evil.com"
    resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": attacker_email,
            "password": "Valid1!Attacker",
            "name": "Attacker",
            "invite_token": victim_token,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired invitation details"

    async with TestSessionLocal() as db:
        aud = (await db.execute(select(Auditor).where(func.lower(Auditor.email) == attacker_email))).scalar_one_or_none()
        assert aud is None


# --------------------------------------------------------------------------
# 5. Anti-Test: Replay / Single-Use of Token
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_anti_exploit_token_single_use_cannot_be_replayed(mock_email, client: AsyncClient):
    """Once a token is consumed during legitimate registration, it cannot be reused."""
    mock_email.return_value = MagicMock(id="task-5")
    await create_test_company(client, email="co_replay@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co_replay@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)

    aud_email = "legit_auditor@firm.com"
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": aud_email},
        headers=co_headers,
    )
    token = _extract_token_from_mock(mock_email)

    # First registration consumes the token
    reg1 = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": aud_email,
            "password": "Valid1!Pass",
            "name": "Legit Auditor",
            "invite_token": token,
        },
    )
    assert reg1.status_code == 201

    # Second registration attempt with the same email returns 409
    reg2_same_email = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": aud_email,
            "password": "Valid1!Pass",
            "name": "Legit Auditor",
            "invite_token": token,
        },
    )
    assert reg2_same_email.status_code == 409

    # Replay on another email returns 400 (token no longer exists in pending invites)
    reg2_diff_email = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": "replay_other@firm.com",
            "password": "Valid1!Pass",
            "name": "Other Auditor",
            "invite_token": token,
        },
    )
    assert reg2_diff_email.status_code == 400
    assert reg2_diff_email.json()["detail"] == "Invalid or expired invitation details"


# --------------------------------------------------------------------------
# 6. Anti-Test: Expired Token Registration Attempt
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_anti_exploit_expired_token_registration_rejected(mock_email, client: AsyncClient):
    """An invitation token older than 7 days must be rejected."""
    mock_email.return_value = MagicMock(id="task-6")
    await create_test_company(client, email="co_expire@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co_expire@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)

    expired_email = "expired_invite@firm.com"
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": expired_email},
        headers=co_headers,
    )
    token = _extract_token_from_mock(mock_email)

    # Force expiration in database
    async with TestSessionLocal() as db:
        invite = (await db.execute(select(PendingAuditorInvite).where(PendingAuditorInvite.email == expired_email))).scalar_one()
        invite.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await db.commit()

    resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": expired_email,
            "password": "Valid1!Pass",
            "name": "Expired Auditor",
            "invite_token": token,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired invitation details"


# --------------------------------------------------------------------------
# 7. Anti-Test: Error Uniformity Across Missing / Wrong / Expired (Anti-Enumeration)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_anti_exploit_non_enumeration_error_uniformity(mock_email, client: AsyncClient):
    """Missing invite, wrong token, and expired token must return identical responses:
    HTTP 400 with detail 'Invalid or expired invitation details'."""
    mock_email.return_value = MagicMock(id="task-7")
    await create_test_company(client, email="co_enum@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co_enum@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)

    # 1. Nonexistent email with random token
    res1 = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": "never_invited@nowhere.com",
            "password": "Valid1!Pass",
            "name": "Nobody",
            "invite_token": "random_token_12345",
        },
    )

    # 2. Invited email with wrong token
    invited_email = "invited_real@firm.com"
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": invited_email},
        headers=co_headers,
    )
    real_token = _extract_token_from_mock(mock_email)

    res2 = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": invited_email,
            "password": "Valid1!Pass",
            "name": "Real Auditor",
            "invite_token": "wrong_token_54321",
        },
    )

    # 3. Invited email with expired token
    async with TestSessionLocal() as db:
        invite = (await db.execute(select(PendingAuditorInvite).where(PendingAuditorInvite.email == invited_email))).scalar_one()
        invite.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db.commit()

    res3 = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": invited_email,
            "password": "Valid1!Pass",
            "name": "Real Auditor",
            "invite_token": real_token,
        },
    )

    expected_payload = {"detail": "Invalid or expired invitation details"}
    assert res1.status_code == 400 and res1.json() == expected_payload
    assert res2.status_code == 400 and res2.json() == expected_payload
    assert res3.status_code == 400 and res3.json() == expected_payload


# --------------------------------------------------------------------------
# 8. Functional Test: Multi-Invite Conversion on Single Registration
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_multi_invite_conversion_across_engagements(mock_email, client: AsyncClient):
    """An auditor invited to multiple engagements converts ALL pending invites
    upon registering with any one valid invite token."""
    mock_email.return_value = MagicMock(id="task-8")
    # Setup Company A and Engagement 1
    await create_test_company(client, email="co_a@test.com", password="Valid1!Pass")
    co_a_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co_a@test.com', password='Valid1!Pass')}"}
    eng1_id = await make_engagement(client, co_a_headers)

    # Setup Company B and Engagement 2
    await create_test_company(client, email="co_b@test.com", password="Valid1!Pass")
    co_b_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co_b@test.com', password='Valid1!Pass')}"}
    eng2_id = await make_engagement(client, co_b_headers)

    shared_auditor_email = "shared_partner@auditco.com"

    # Company A invites
    await client.post(
        f"/api/v1/auditease/engagements/{eng1_id}/auditors/invite",
        json={"email": shared_auditor_email},
        headers=co_a_headers,
    )
    token_a = _extract_token_from_mock(mock_email)

    # Company B invites
    await client.post(
        f"/api/v1/auditease/engagements/{eng2_id}/auditors/invite",
        json={"email": shared_auditor_email},
        headers=co_b_headers,
    )

    # Auditor registers using Company A's token
    reg_resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": shared_auditor_email,
            "password": "Valid1!Pass",
            "name": "Shared Partner",
            "invite_token": token_a,
        },
    )
    assert reg_resp.status_code == 201

    # Login and verify both engagements are present in auditor's list
    login_resp = await client.post(
        "/api/v1/auth/auditor/login",
        json={"email": shared_auditor_email, "password": "Valid1!Pass"},
    )
    assert login_resp.status_code == 200
    aud_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    engs_resp = await client.get("/api/v1/auditor/engagements", headers=aud_headers)
    assert engs_resp.status_code == 200
    aud_engs = engs_resp.json()
    assert len(aud_engs) == 2
    eng_ids = {e["id"] for e in aud_engs}
    assert eng1_id in eng_ids
    assert eng2_id in eng_ids

    # All pending invite records for this email are deleted
    async with TestSessionLocal() as db:
        remaining_pendings = (await db.execute(
            select(PendingAuditorInvite).where(func.lower(PendingAuditorInvite.email) == shared_auditor_email)
        )).scalars().all()
        assert len(remaining_pendings) == 0


# --------------------------------------------------------------------------
# 9. Functional Test: Customized Area Permissions Preservation
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_custom_area_permissions_preserved_on_conversion(mock_email, client: AsyncClient):
    """When an invite is sent with custom area permissions, those permissions
    are preserved on the resulting AuditorEngagementGrant after registration."""
    mock_email.return_value = MagicMock(id="task-9")
    await create_test_company(client, email="co_perms@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co_perms@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)

    restricted_email = "restricted_auditor@firm.com"
    custom_perms = {
        "trial_balance": True,
        "entries": False,
        "requirements": True,
        "queries": False,
        "documents": False,
    }

    inv_res = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": restricted_email, "area_permissions": custom_perms},
        headers=co_headers,
    )
    assert inv_res.status_code == 200
    token = _extract_token_from_mock(mock_email)

    reg_res = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": restricted_email,
            "password": "Valid1!Pass",
            "name": "Restricted Auditor",
            "invite_token": token,
        },
    )
    assert reg_res.status_code == 201

    async with TestSessionLocal() as db:
        grant = (await db.execute(
            select(AuditorEngagementGrant)
            .join(Auditor, Auditor.id == AuditorEngagementGrant.auditor_id)
            .where(Auditor.email == restricted_email)
        )).scalar_one()
        assert grant.area_permissions == custom_perms


# --------------------------------------------------------------------------
# 10. Functional Test: Case-Insensitive Email Collision & Token Matching
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_case_insensitive_email_collision_and_token_matching(mock_email, client: AsyncClient):
    """Inviting MixedCase@Firm.COM allows registration with lowercase mixedcase@firm.com,
    stores email normalized to lowercase, and prevents duplicate registration with any case."""
    mock_email.return_value = MagicMock(id="task-10")
    await create_test_company(client, email="co_case@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co_case@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)

    inv_res = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "MixedCase@Firm.COM"},
        headers=co_headers,
    )
    assert inv_res.status_code == 200
    token = _extract_token_from_mock(mock_email)

    # Register with lowercased email and matching token
    reg_res = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": "mixedcase@firm.com",
            "password": "Valid1!Pass",
            "name": "Mixed Auditor",
            "invite_token": token,
        },
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["email"] == "mixedcase@firm.com"

    # Duplicate registration attempt with UPPERCASE or mixed case fails with 409
    dup_res = await client.post(
        "/api/v1/auth/auditor/register",
        json={
            "email": "MIXEDCASE@FIRM.COM",
            "password": "Valid1!Pass",
            "name": "Mixed Auditor 2",
            "invite_token": "some-token",
        },
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["detail"] == "Email already registered"


# --------------------------------------------------------------------------
# 11. Anti-Test: token is bound to the exact email it was issued to
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_anti_exploit_token_is_bound_to_its_own_email(mock_email, client: AsyncClient):
    """A valid token issued for one address must not register any other address, in
    either direction — an attacker holding a genuine invite of their own cannot use it
    to claim a victim's invited email, and a stolen victim token cannot be redeemed
    under the attacker's own email."""
    mock_email.return_value = MagicMock(id="task-bind")
    await create_test_company(client, email="bind_co@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='bind_co@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)

    victim_email = "victim_bound@firm.com"
    attacker_email = "attacker_bound@evil.com"

    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": victim_email}, headers=co_headers,
    )
    victim_token = _extract_token_from_mock(mock_email)

    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": attacker_email}, headers=co_headers,
    )
    attacker_token = _extract_token_from_mock(mock_email)
    assert victim_token != attacker_token

    # Direction 1: attacker's own genuine token cannot claim the victim's email.
    res1 = await client.post(
        "/api/v1/auth/auditor/register",
        json={"email": victim_email, "password": "Valid1!Pass",
              "name": "Attacker", "invite_token": attacker_token},
    )
    assert res1.status_code == 400
    assert res1.json()["detail"] == "Invalid or expired invitation details"

    # Direction 2: the victim's token cannot be redeemed under the attacker's email.
    res2 = await client.post(
        "/api/v1/auth/auditor/register",
        json={"email": attacker_email, "password": "Valid1!Pass",
              "name": "Attacker", "invite_token": victim_token},
    )
    assert res2.status_code == 400
    assert res2.json()["detail"] == "Invalid or expired invitation details"

    # Neither account exists, and both invites survive intact for their real owners.
    async with TestSessionLocal() as db:
        assert (await db.execute(select(Auditor).where(
            func.lower(Auditor.email).in_([victim_email, attacker_email])
        ))).scalars().all() == []
        pend_emails = set((await db.execute(
            select(PendingAuditorInvite.email).where(PendingAuditorInvite.engagement_id == eng_id)
        )).scalars().all())
        assert pend_emails == {victim_email, attacker_email}

    # Each token still works for its own email.
    ok = await client.post(
        "/api/v1/auth/auditor/register",
        json={"email": victim_email, "password": "Valid1!Pass",
              "name": "Victim", "invite_token": victim_token},
    )
    assert ok.status_code == 201, ok.text


# --------------------------------------------------------------------------
# 12. A re-invite cannot create a duplicate pending row, and old tokens die
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_reinvite_upserts_single_row_and_invalidates_old_token(mock_email, client: AsyncClient):
    """Re-inviting refreshes in place (no duplicate rows, no 409), the superseded token
    stops working, and registration with the current token still succeeds."""
    mock_email.return_value = MagicMock(id="task-upsert")
    await create_test_company(client, email="upsert_co@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='upsert_co@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)
    target = "resend_target@firm.com"

    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
                      json={"email": target}, headers=co_headers)
    first_token = _extract_token_from_mock(mock_email)

    for _ in range(3):
        again = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
                                  json={"email": target}, headers=co_headers)
        assert again.status_code == 200, again.text
    latest_token = _extract_token_from_mock(mock_email)
    assert latest_token != first_token

    # Exactly one pending row survives the repeated invites.
    async with TestSessionLocal() as db:
        rows = (await db.execute(select(PendingAuditorInvite).where(
            PendingAuditorInvite.engagement_id == eng_id,
            PendingAuditorInvite.email == target,
        ))).scalars().all()
        assert len(rows) == 1

    # The superseded token is dead.
    stale = await client.post(
        "/api/v1/auth/auditor/register",
        json={"email": target, "password": "Valid1!Pass",
              "name": "Stale", "invite_token": first_token},
    )
    assert stale.status_code == 400

    # The current token works.
    ok = await client.post(
        "/api/v1/auth/auditor/register",
        json={"email": target, "password": "Valid1!Pass",
              "name": "Fresh", "invite_token": latest_token},
    )
    assert ok.status_code == 201, ok.text


# --------------------------------------------------------------------------
# 13. The DB refuses duplicate pending invites outright
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_duplicate_pending_invite_rejected_by_constraint(mock_email, client: AsyncClient):
    """uq_pending_invite_engagement_email is what stops a racing double-invite from
    wedging both re-invites and the auditor's registration."""
    from sqlalchemy.exc import IntegrityError
    from app.auth import hash_password
    from app.models.auditease import FULL_AREA_PERMISSIONS

    mock_email.return_value = MagicMock(id="task-dup")
    await create_test_company(client, email="dup_co@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='dup_co@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)
    target = "dup_target@firm.com"

    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
                      json={"email": target}, headers=co_headers)

    async with TestSessionLocal() as db:
        db.add(PendingAuditorInvite(
            engagement_id=eng_id,
            email=target,
            token_hash=hash_password("some-other-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            area_permissions=dict(FULL_AREA_PERMISSIONS),
        ))
        with pytest.raises(IntegrityError):
            await db.commit()


# --------------------------------------------------------------------------
# 14. A pasted token with surrounding whitespace is accepted
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_token_with_surrounding_whitespace_accepted(mock_email, client: AsyncClient):
    """Copy-pasting the invite code out of an email often carries a trailing newline;
    that must not read as an invalid token."""
    mock_email.return_value = MagicMock(id="task-ws")
    await create_test_company(client, email="ws_co@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='ws_co@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)
    target = "whitespace_target@firm.com"

    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
                      json={"email": target}, headers=co_headers)
    token = _extract_token_from_mock(mock_email)

    resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={"email": target, "password": "Valid1!Pass",
              "name": "Pasty", "invite_token": f"  {token}\n"},
    )
    assert resp.status_code == 201, resp.text


# --------------------------------------------------------------------------
# 15. Restricted invite permissions are reported honestly to the admin
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_pending_invite_listing_reports_restricted_permissions(mock_email, client: AsyncClient):
    """The auditors list must show what was actually granted on a pending invite, not a
    hardcoded full-access set — an admin uses this screen to verify the restriction."""
    mock_email.return_value = MagicMock(id="task-perm-list")
    await create_test_company(client, email="permlist_co@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='permlist_co@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)
    target = "restricted_pending@firm.com"

    restricted = {"trial_balance": True, "entries": False, "requirements": False,
                  "queries": False, "documents": False}
    inv = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": target, "area_permissions": restricted}, headers=co_headers,
    )
    assert inv.status_code == 200, inv.text

    listing = await client.get(
        f"/api/v1/auditease/engagements/{eng_id}/auditors", headers=co_headers
    )
    assert listing.status_code == 200, listing.text
    row = next(r for r in listing.json() if r["email"] == target)
    assert row["status"] == "pending"
    assert row["area_permissions"] == restricted


# --------------------------------------------------------------------------
# 16. Expired pending invites must not read as actionable "pending" forever
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_expired_pending_invite_reports_as_expired_not_pending(mock_email, client: AsyncClient):
    """An admin looking at the auditors list must be able to tell an invite has gone
    stale (past its 7-day TTL) rather than seeing it sit as 'pending' forever with no
    signal that the link the auditor has can no longer be redeemed."""
    mock_email.return_value = MagicMock(id="task-expiry-list")
    await create_test_company(client, email="expirylist_co@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='expirylist_co@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)
    target = "stale_invitee@firm.com"

    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
                      json={"email": target}, headers=co_headers)

    listing = await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors", headers=co_headers)
    row = next(r for r in listing.json() if r["email"] == target)
    assert row["status"] == "pending"
    assert row["expires_at"] is not None

    async with TestSessionLocal() as db:
        invite = (await db.execute(select(PendingAuditorInvite).where(
            PendingAuditorInvite.engagement_id == eng_id, PendingAuditorInvite.email == target
        ))).scalar_one()
        invite.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()

    listing2 = await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors", headers=co_headers)
    row2 = next(r for r in listing2.json() if r["email"] == target)
    assert row2["status"] == "expired"

    # Re-inviting refreshes it back to a live, non-expired pending row.
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
                      json={"email": target}, headers=co_headers)
    listing3 = await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors", headers=co_headers)
    row3 = next(r for r in listing3.json() if r["email"] == target)
    assert row3["status"] == "pending"
