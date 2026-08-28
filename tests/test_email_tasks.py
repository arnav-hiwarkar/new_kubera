from unittest.mock import MagicMock, patch
from app.services.email.schemas import EmailDeliveryResult
from app.services.email.tasks import send_email_async


@patch("app.services.email.tasks.EmailService")
def test_send_email_async_task(mock_service_class):
    mock_service_instance = MagicMock()
    mock_service_instance.send.return_value = EmailDeliveryResult(
        success=True,
        message_id="<test-msg-id@ethdc.in>",
        recipients=["user@example.com"],
        duration_ms=150.0,
    )
    mock_service_class.return_value = mock_service_instance

    payload = {
        "to": ["user@example.com"],
        "subject": "Background Notification",
        "body_text": "Processed asynchronously.",
    }
    result = send_email_async(payload)

    assert result["success"] is True
    assert result["message_id"] == "<test-msg-id@ethdc.in>"
    mock_service_instance.send.assert_called_once()
