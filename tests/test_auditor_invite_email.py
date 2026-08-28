from unittest.mock import patch, MagicMock
import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token, create_test_auditor


@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_invite_unregistered_auditor_dispatches_register_email(
    mock_send_task, client: AsyncClient
):
    mock_send_task.return_value = MagicMock(id="task-123")
    await create_test_company(client, name="AuditCo", email="admin@auditco.com")
    token = await get_company_token(client, email="admin@auditco.com")

    # Create engagement
    eng_res = await client.post(
        "/api/v1/auditease/engagements",
        json={"period_label": "FY 2025-26"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert eng_res.status_code == 201
    eng_id = eng_res.json()["id"]

    # Invite new unregistered auditor
    payload = {"email": "new_auditor@test.com", "area_permissions": None}
    res = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    mock_send_task.assert_called_once()
    message_dict = mock_send_task.call_args[0][0]
    kwargs = mock_send_task.call_args.kwargs
    assert "new_auditor@test.com" in message_dict["to"]
    assert message_dict["template_name"] == "auditor_invite.html"
    assert "auditor/register?email=new_auditor%40test.com" in message_dict["template_context"]["action_button"]["url"]
    assert "AuditCo" in message_dict["template_context"]["company_name"]
    assert "AuditCo" == message_dict["template_context"]["header_title"]
    assert kwargs.get("company_id") is not None
    assert kwargs.get("log_id") is not None


@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_invite_registered_auditor_dispatches_login_email(
    mock_send_task, client: AsyncClient
):
    mock_send_task.return_value = MagicMock(id="task-456")
    await create_test_company(client, name="AuditCo2", email="admin@auditco2.com")
    token = await get_company_token(client, email="admin@auditco2.com")

    # Create registered auditor
    await create_test_auditor(client, email="existing_auditor@test.com", password="password123")

    # Create engagement
    eng_res = await client.post(
        "/api/v1/auditease/engagements",
        json={"period_label": "FY 2024-25"},
        headers={"Authorization": f"Bearer {token}"},
    )
    eng_id = eng_res.json()["id"]

    # Invite existing auditor
    payload = {"email": "existing_auditor@test.com", "area_permissions": None}
    res = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    mock_send_task.assert_called_once()
    message_dict = mock_send_task.call_args[0][0]
    kwargs = mock_send_task.call_args.kwargs
    assert "existing_auditor@test.com" in message_dict["to"]
    assert "auditor/login" in message_dict["template_context"]["action_button"]["url"]
    assert kwargs.get("company_id") is not None
    assert kwargs.get("log_id") is not None


@pytest.mark.asyncio
@patch("app.services.email.tasks.send_email_async.delay")
async def test_invite_email_uses_custom_company_smtp_when_configured(
    mock_send_task, client: AsyncClient
):
    mock_send_task.return_value = MagicMock(id="task-789")
    await create_test_company(client, name="CustomAuditCo", email="admin@customaudit.com")
    token = await get_company_token(client, email="admin@customaudit.com")

    # Configure custom SMTP for company
    smtp_payload = {
        "host": "mail.customaudit.com",
        "port": 587,
        "user": "audit@customaudit.com",
        "password": "SecretPassword123",
        "use_tls": True,
        "use_ssl": False,
        "from_email": "audit@customaudit.com",
        "from_name": "Custom Audit Team",
    }
    await client.put("/api/v1/company/smtp", json=smtp_payload, headers={"Authorization": f"Bearer {token}"})

    # Create engagement
    eng_res = await client.post(
        "/api/v1/auditease/engagements",
        json={"period_label": "FY 2025-26"},
        headers={"Authorization": f"Bearer {token}"},
    )
    eng_id = eng_res.json()["id"]

    # Invite auditor
    payload = {"email": "auditor_custom@test.com", "area_permissions": None}
    res = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    mock_send_task.assert_called_once()
    kwargs = mock_send_task.call_args.kwargs
    assert kwargs.get("company_id") is not None
    assert kwargs.get("log_id") is not None
