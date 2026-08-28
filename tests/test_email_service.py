import smtplib
from unittest.mock import MagicMock, patch
import pytest

from app.services.email.client import EmailService
from app.services.email.schemas import (
    EmailAttachment,
    EmailConfig,
    EmailDeliveryError,
    EmailMessage,
)


@pytest.fixture
def mock_config():
    return EmailConfig(
        host="smtp.ethdc.in",
        port=587,
        user="kubera@ethdc.in",
        password="secretpassword",
        use_tls=True,
        use_ssl=False,
        from_email="kubera@ethdc.in",
        from_name="Kubera Compliance",
        timeout=10,
    )


def test_build_mime_message(mock_config):
    service = EmailService(config=mock_config)
    message = EmailMessage(
        to=["recipient@example.com"],
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        subject="Test Notice",
        body_text="Hello World",
        body_html="<p>Hello World</p>",
        attachments=[
            EmailAttachment(filename="sample.txt", content=b"Sample content", content_type="text/plain")
        ],
    )
    mime = service.build_mime_message(message)
    assert mime["Subject"] == "Test Notice"
    assert mime["From"] == "Kubera Compliance <kubera@ethdc.in>"
    assert mime["To"] == "recipient@example.com"
    assert mime["Cc"] == "cc@example.com"
    assert "Message-ID" in mime


@patch("smtplib.SMTP")
def test_send_email_success(mock_smtp_class, mock_config):
    mock_smtp_instance = MagicMock()
    mock_smtp_instance.__enter__.return_value = mock_smtp_instance
    mock_smtp_class.return_value = mock_smtp_instance

    service = EmailService(config=mock_config)
    message = EmailMessage(
        to=["recipient@example.com"],
        subject="Test Success",
        body_text="This is a test body.",
    )
    result = service.send(message)

    assert result.success is True
    assert "recipient@example.com" in result.recipients
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("kubera@ethdc.in", "secretpassword")
    mock_smtp_instance.send_message.assert_called_once()


@patch("smtplib.SMTP_SSL")
def test_send_email_ssl(mock_ssl_class):
    mock_ssl_instance = MagicMock()
    mock_ssl_instance.__enter__.return_value = mock_ssl_instance
    mock_ssl_class.return_value = mock_ssl_instance

    ssl_config = EmailConfig(
        host="smtp.ethdc.in",
        port=465,
        user="kubera@ethdc.in",
        password="secretpassword",
        use_tls=False,
        use_ssl=True,
    )
    service = EmailService(config=ssl_config)
    message = EmailMessage(to=["recipient@example.com"], subject="SSL Test", body_text="Hello SSL")
    result = service.send(message)

    assert result.success is True
    mock_ssl_class.assert_called_once()
    mock_ssl_instance.login.assert_called_once_with("kubera@ethdc.in", "secretpassword")
    mock_ssl_instance.send_message.assert_called_once()


@patch("smtplib.SMTP")
def test_send_email_auth_failure(mock_smtp_class, mock_config):
    mock_smtp_instance = MagicMock()
    mock_smtp_instance.__enter__.return_value = mock_smtp_instance
    mock_smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
    mock_smtp_class.return_value = mock_smtp_instance

    service = EmailService(config=mock_config)
    message = EmailMessage(to=["recipient@example.com"], subject="Test", body_text="Hello")

    with pytest.raises(EmailDeliveryError, match="SMTP authentication failed"):
        service.send(message)


@patch("smtplib.SMTP")
def test_verify_connection(mock_smtp_class, mock_config):
    mock_smtp_instance = MagicMock()
    mock_smtp_instance.__enter__.return_value = mock_smtp_instance
    mock_smtp_instance.noop.return_value = (250, b"OK")
    mock_smtp_class.return_value = mock_smtp_instance

    service = EmailService(config=mock_config)
    res = service.verify_connection()

    assert res["status"] == "ok"
    assert res["host"] == "smtp.ethdc.in"
    assert res["port"] == 587
    assert res["user"] == "kubera@ethdc.in"
    assert "latency_ms" in res

