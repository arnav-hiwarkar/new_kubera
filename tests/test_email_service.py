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


@pytest.fixture(autouse=True)
def mock_resolve_public_smtp_target():
    with patch("app.services.email.client.resolve_public_smtp_target") as mock_resolve:
        mock_resolve.return_value = "8.8.8.8"
        yield mock_resolve


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


def test_attachment_base64_serialization_roundtrip():
    """CRITICAL-1 regression: bytes must survive JSON serialization via model_dump/reconstruct."""
    original_content = b"\x00\x01\x02\xff binary data"
    att = EmailAttachment(
        filename="binary.dat",
        content=original_content,
        content_type="application/octet-stream",
    )
    dumped = att.model_dump()
    # model_dump should produce a base64 string, not raw bytes
    assert isinstance(dumped["content"], str)
    # Reconstruct from the dumped dict (simulates Celery deserialization)
    restored = EmailAttachment(**dumped)
    assert restored.content == original_content


@patch("smtplib.SMTP")
def test_socket_closed_on_auth_failure(mock_smtp_class, mock_config):
    """MEDIUM-1 regression: server.close() must be called if login() raises."""
    mock_smtp_instance = MagicMock()
    mock_smtp_instance.__enter__.return_value = mock_smtp_instance
    mock_smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad creds")
    mock_smtp_class.return_value = mock_smtp_instance

    service = EmailService(config=mock_config)
    with pytest.raises(EmailDeliveryError):
        service._get_connection()
    mock_smtp_instance.close.assert_called_once()


def test_invalid_template_name_raises(mock_config):
    """LOW-3 regression: invalid template_name should raise EmailDeliveryError."""
    service = EmailService(config=mock_config)
    message = EmailMessage(
        to=["test@example.com"],
        subject="Test",
        template_name="nonexistent_template.html",
    )
    with pytest.raises(EmailDeliveryError, match="not found"):
        service.build_mime_message(message)


def test_empty_to_list_rejected():
    """LOW-4 regression: empty to list should fail at schema validation."""
    with pytest.raises(Exception):
        EmailMessage(to=[], subject="Test", body_text="Hello")


def test_html_entity_unescaping():
    """MEDIUM-5 regression: HTML entities from autoescaped Jinja2 must be decoded."""
    from app.services.email.templates import extract_plain_text
    html = "<p>Price is &amp; &lt;100&gt; for &quot;items&quot;</p>"
    text = extract_plain_text(html)
    assert "&amp;" not in text
    assert "&lt;" not in text
    assert '& <100> for "items"' in text


def test_get_connection_uses_net_guard_and_pins_ip():
    from app.services.email.net_guard import BlockedSmtpTarget
    config = EmailConfig(host="smtp.example.com", port=587, user="u", password="p", use_tls=True)
    service = EmailService(config=config)
    
    with patch("app.services.email.client.resolve_public_smtp_target") as mock_resolve:
        mock_resolve.return_value = "8.8.8.8"
        with patch("app.services.email.client.smtplib.SMTP") as mock_smtp_class:
            mock_smtp_instance = MagicMock()
            mock_smtp_class.return_value = mock_smtp_instance
            
            # Use a dummy context for TLS
            with patch("app.services.email.client.ssl.create_default_context"):
                # We expect _get_connection to succeed if mocked properly
                server = service._get_connection()
                
                # Check that resolve was called
                mock_resolve.assert_called_once_with("smtp.example.com", 587)
                
                # Check that we connected to the IP, not the hostname
                mock_smtp_instance.connect.assert_called_once_with("8.8.8.8", 587)
                
                # Check that SNI hostname was preserved
                assert mock_smtp_instance._host == "smtp.example.com"

def test_get_connection_blocks_internal():
    from app.services.email.net_guard import BlockedSmtpTarget
    config = EmailConfig(host="127.0.0.1", port=587, user="u", password="p")
    service = EmailService(config=config)
    
    with patch("app.services.email.client.resolve_public_smtp_target") as mock_resolve:
        mock_resolve.side_effect = BlockedSmtpTarget("Blocked")
        with pytest.raises(EmailDeliveryError, match="Blocked"):
            service._get_connection()


def test_get_connection_ssl_pins_ip_and_sni():
    """Verify that SMTP_SSL (port 465) also pins the public IP and sets SNI."""
    config = EmailConfig(host="smtp.example.com", port=465, user="u", password="p", use_ssl=True, use_tls=False)
    service = EmailService(config=config)

    with patch("app.services.email.client.resolve_public_smtp_target") as mock_resolve:
        mock_resolve.return_value = "8.8.8.8"
        with patch("app.services.email.client.smtplib.SMTP_SSL") as mock_ssl_class:
            mock_ssl_instance = MagicMock()
            mock_ssl_instance.connect.return_value = (220, b"Ready")
            mock_ssl_class.return_value = mock_ssl_instance

            with patch("app.services.email.client.ssl.create_default_context"):
                server = service._get_connection()

                mock_resolve.assert_called_once_with("smtp.example.com", 465)
                mock_ssl_instance.connect.assert_called_once_with("8.8.8.8", 465)
                assert mock_ssl_instance._host == "smtp.example.com"


def test_get_connection_rejects_non_220_greeting():
    """Verify that a server greeting other than 220 raises SMTPConnectError and closes socket."""
    config = EmailConfig(host="smtp.example.com", port=587, user="u", password="p")
    service = EmailService(config=config)

    with patch("app.services.email.client.resolve_public_smtp_target", return_value="8.8.8.8"):
        with patch("app.services.email.client.smtplib.SMTP") as mock_smtp_class:
            mock_smtp_instance = MagicMock()
            mock_smtp_instance.connect.return_value = (421, b"Service not available")
            mock_smtp_class.return_value = mock_smtp_instance

            with pytest.raises(smtplib.SMTPConnectError):
                service._get_connection()

            mock_smtp_instance.close.assert_called_once()


def test_get_connection_closes_socket_on_connect_error():
    """Verify that if connect() raises an exception, server.close() is called."""
    config = EmailConfig(host="smtp.example.com", port=587, user="u", password="p")
    service = EmailService(config=config)

    with patch("app.services.email.client.resolve_public_smtp_target", return_value="8.8.8.8"):
        with patch("app.services.email.client.smtplib.SMTP") as mock_smtp_class:
            mock_smtp_instance = MagicMock()
            mock_smtp_instance.connect.side_effect = OSError("Connection refused")
            mock_smtp_class.return_value = mock_smtp_instance

            with pytest.raises(OSError, match="Connection refused"):
                service._get_connection()

            mock_smtp_instance.close.assert_called_once()


def test_verify_connection_payload_omits_raw_response(mock_config):
    """Ensure that verify_connection() return payload never contains raw server response banner."""
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.__enter__.return_value = mock_smtp_instance
        mock_smtp_instance.connect.return_value = (220, b"220 mail.example.com ESMTP Postfix")
        mock_smtp_instance.noop.return_value = (250, b"2.0.0 Ok")
        mock_smtp_class.return_value = mock_smtp_instance

        service = EmailService(config=mock_config)
        res = service.verify_connection()

        assert "response" not in res
        assert res["status"] == "ok"
        assert res["host"] == mock_config.host
        assert res["port"] == mock_config.port
