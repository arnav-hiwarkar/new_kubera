"""Tests for activity log and notifications — including cross-tenant-leak boundary tests."""
import pytest
from httpx import AsyncClient

from tests.conftest import (
    create_test_company,
    get_company_token,
    INTERNAL_API_KEY,
)


# === Activity Log ===


@pytest.mark.asyncio
async def test_activity_log_created_on_company_creation(client: AsyncClient):
    """Company creation should produce at least one activity log entry."""
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.get(
        "/api/v1/activity-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 1
    assert logs[0]["action"] == "company.created"


@pytest.mark.asyncio
async def test_activity_log_cross_tenant_leak(client: AsyncClient):
    """Company A must not see Company B's activity logs."""
    # Create company A
    await create_test_company(client, name="CompA", email="a@a.com", password="pass")
    token_a = await get_company_token(client, email="a@a.com", password="pass")

    # Create company B
    await create_test_company(client, name="CompB", email="b@b.com", password="pass")
    token_b = await get_company_token(client, email="b@b.com", password="pass")

    # Get logs for A
    resp_a = await client.get(
        "/api/v1/activity-log",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    logs_a = resp_a.json()

    # Get logs for B
    resp_b = await client.get(
        "/api/v1/activity-log",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    logs_b = resp_b.json()

    # Extract company IDs
    company_ids_a = {log["company_id"] for log in logs_a}
    company_ids_b = {log["company_id"] for log in logs_b}

    # No overlap
    assert company_ids_a.isdisjoint(company_ids_b)


# === Notifications ===


@pytest.mark.asyncio
async def test_notifications_empty(client: AsyncClient):
    """New user should have no notifications."""
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_notification_mark_read(client: AsyncClient):
    """Create a notification manually (via DB) and mark it read via API."""
    from app.models.notification import Notification, RecipientType
    from tests.conftest import override_get_db

    # Create company + user
    data = await create_test_company(client)
    token = await get_company_token(client)
    user_id = data["admin"]["id"]

    # Insert a notification directly
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.conftest import TestSessionLocal
    import uuid

    async with TestSessionLocal() as session:
        notif = Notification(
            recipient_type=RecipientType.company_user,
            recipient_id=uuid.UUID(user_id),
            type="test.notification",
            payload={"msg": "hello"},
        )
        session.add(notif)
        await session.commit()
        notif_id = notif.id

    # Get notifications
    resp = await client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["read_at"] is None

    # Mark read
    resp = await client.patch(
        f"/api/v1/notifications/{notif_id}/read",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["read_at"] is not None


@pytest.mark.asyncio
async def test_notification_cross_tenant_leak(client: AsyncClient):
    """User A must not see or mark-read User B's notifications."""
    import uuid
    from app.models.notification import Notification, RecipientType
    from tests.conftest import TestSessionLocal

    # Create two companies
    data_a = await create_test_company(client, name="A", email="a@a.com", password="pass")
    token_a = await get_company_token(client, email="a@a.com", password="pass")

    data_b = await create_test_company(client, name="B", email="b@b.com", password="pass")
    token_b = await get_company_token(client, email="b@b.com", password="pass")

    user_b_id = uuid.UUID(data_b["admin"]["id"])

    # Create notification for user B
    async with TestSessionLocal() as session:
        notif = Notification(
            recipient_type=RecipientType.company_user,
            recipient_id=user_b_id,
            type="test.leak",
            payload={"secret": "b_data"},
        )
        session.add(notif)
        await session.commit()
        notif_id = notif.id

    # User A should not see B's notification
    resp = await client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # User A should not be able to mark B's notification as read
    resp = await client.patch(
        f"/api/v1/notifications/{notif_id}/read",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404
