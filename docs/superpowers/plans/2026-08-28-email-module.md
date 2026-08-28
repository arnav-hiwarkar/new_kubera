# Email Module & CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated, secure, fast email service module and standalone operator CLI (`send_email.py`) with support for rich branded HTML templates, attachments, direct SMTP / STARTTLS, Celery background queuing, and multi-tenant extensible configuration defaulting to `kubera@ethdc.in`.

**Architecture:** A three-layer architecture consisting of a configuration and schema layer (`app/config.py`, `app/services/email/schemas.py`), a core transport and Jinja2 templating service (`app/services/email/client.py`, `app/services/email/templates.py`), an asynchronous Celery background task (`app/services/email/tasks.py`), and a standalone operator CLI script (`send_email.py`).

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2 / pydantic-settings, smtplib / ssl / email.mime, Jinja2, Celery 5.5, Redis, pytest.

## Global Constraints

- Sender address defaults to `kubera@ethdc.in` loaded from environment variables (`SMTP_FROM_EMAIL`).
- SMTP relay connections must support both STARTTLS (port 587) and direct SSL (port 465).
- All templates must provide both responsive HTML and fallback plain-text rendering.
- Code style must match existing codebase conventions (clean docstrings, typing hints, Pydantic models, standalone CLI script patterns like `create_company.py`).

---

### Task 1: SMTP Settings & Configuration

**Files:**
- Modify: `app/config.py:38-45`
- Modify: `.env.example:50-54`
- Test: `tests/test_email_config.py`

**Interfaces:**
- Consumes: Environment variables via Pydantic `BaseSettings`.
- Produces: `Settings` attributes (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_USE_SSL`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_TIMEOUT`).

- [ ] **Step 1: Write the failing test for email configuration**

```python
# tests/test_email_config.py
from app.config import Settings


def test_smtp_default_settings():
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@localhost:5432/test",
        JWT_SECRET_KEY="test-secret",
        ROOT_MASTER_KEK="0" * 64,
        INTERNAL_API_KEY="test-key",
    )
    assert settings.SMTP_HOST == ""
    assert settings.SMTP_PORT == 587
    assert settings.SMTP_USER == ""
    assert settings.SMTP_PASSWORD == ""
    assert settings.SMTP_USE_TLS is True
    assert settings.SMTP_USE_SSL is False
    assert settings.SMTP_FROM_EMAIL == "kubera@ethdc.in"
    assert settings.SMTP_FROM_NAME == "Kubera Compliance"
    assert settings.SMTP_TIMEOUT == 15


def test_smtp_custom_settings(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.ethdc.in")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "kubera@ethdc.in")
    monkeypatch.setenv("SMTP_PASSWORD", "secret123")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    monkeypatch.setenv("SMTP_USE_SSL", "true")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "admin@ethdc.in")
    monkeypatch.setenv("SMTP_FROM_NAME", "Kubera Admin")
    monkeypatch.setenv("SMTP_TIMEOUT", "30")

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@localhost:5432/test",
        JWT_SECRET_KEY="test-secret",
        ROOT_MASTER_KEK="0" * 64,
        INTERNAL_API_KEY="test-key",
    )
    assert settings.SMTP_HOST == "smtp.ethdc.in"
    assert settings.SMTP_PORT == 465
    assert settings.SMTP_USER == "kubera@ethdc.in"
    assert settings.SMTP_PASSWORD == "secret123"
    assert settings.SMTP_USE_TLS is False
    assert settings.SMTP_USE_SSL is True
    assert settings.SMTP_FROM_EMAIL == "admin@ethdc.in"
    assert settings.SMTP_FROM_NAME == "Kubera Admin"
    assert settings.SMTP_TIMEOUT == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_email_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'SMTP_HOST'`

- [ ] **Step 3: Update `app/config.py` and `.env.example`**

In `app/config.py`:
```python
    # SMTP / Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_FROM_EMAIL: str = "kubera@ethdc.in"
    SMTP_FROM_NAME: str = "Kubera Compliance"
    SMTP_TIMEOUT: int = 15
```

In `.env.example`:
```ini
# === SMTP / Email ===
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_FROM_EMAIL=kubera@ethdc.in
SMTP_FROM_NAME=Kubera Compliance
SMTP_TIMEOUT=15
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_email_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py .env.example tests/test_email_config.py
git commit -m "feat(email): add SMTP configuration settings"
```

---

### Task 2: Email Schemas and Jinja2 Templating Engine

**Files:**
- Create: `app/services/email/__init__.py`
- Create: `app/services/email/schemas.py`
- Create: `app/services/email/templates/base.html`
- Create: `app/services/email/templates/branded_message.html`
- Create: `app/services/email/templates.py`
- Test: `tests/test_email_templates.py`

**Interfaces:**
- Consumes: `EmailConfig` and `EmailMessage` models.
- Produces: `render_email_template(template_name: str, context: dict) -> str`, `extract_plain_text(html_str: str) -> str`.

- [ ] **Step 1: Write the failing tests for email schemas and templating**

```python
# tests/test_email_templates.py
from app.services.email.schemas import EmailAttachment, EmailConfig, EmailMessage
from app.services.email.templates import extract_plain_text, render_email_template


def test_email_models():
    config = EmailConfig(
        host="smtp.ethdc.in",
        port=587,
        user="kubera@ethdc.in",
        password="pwd",
        from_email="kubera@ethdc.in",
        from_name="Kubera",
    )
    assert config.host == "smtp.ethdc.in"
    assert config.use_tls is True

    attachment = EmailAttachment(
        filename="report.pdf",
        content=b"%PDF-1.4 test content",
        content_type="application/pdf",
    )
    assert attachment.filename == "report.pdf"

    message = EmailMessage(
        to=["test@example.com"],
        subject="Test Subject",
        body_text="Hello Plain Text",
        attachments=[attachment],
    )
    assert message.to == ["test@example.com"]
    assert len(message.attachments) == 1


def test_render_branded_template():
    html = render_email_template(
        "branded_message.html",
        {
            "headline": "System Notification",
            "paragraphs": ["Welcome to Kubera.", "Your compliance module is ready."],
            "action_button": {
                "label": "Open Dashboard",
                "url": "https://app.kuberacompliance.com",
            },
            "footer_note": "This is an automated system email from Kubera.",
        },
    )
    assert "System Notification" in html
    assert "Welcome to Kubera." in html
    assert "Open Dashboard" in html
    assert "https://app.kuberacompliance.com" in html
    assert "Kubera Compliance" in html


def test_extract_plain_text():
    html = "<h1>Welcome</h1><p>Hello world.</p><a href='https://example.com'>Click Here</a>"
    text = extract_plain_text(html)
    assert "Welcome" in text
    assert "Hello world." in text
    assert "Click Here" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_email_templates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.email'`

- [ ] **Step 3: Implement `schemas.py`, `templates.py`, and HTML template files**

`app/services/email/schemas.py`:
```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class EmailAttachment(BaseModel):
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


class EmailMessage(BaseModel):
    to: List[str]
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    reply_to: Optional[str] = None
    attachments: Optional[List[EmailAttachment]] = None
    template_name: Optional[str] = None
    template_context: Optional[Dict[str, Any]] = None


class EmailConfig(BaseModel):
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str = "kubera@ethdc.in"
    from_name: str = "Kubera Compliance"
    timeout: int = 15


class EmailDeliveryResult(BaseModel):
    success: bool
    message_id: str
    recipients: List[str]
    duration_ms: float
    error: Optional[str] = None


class EmailDeliveryError(Exception):
    """Raised when an email fails to send via SMTP."""
    pass
```

`app/services/email/templates/base.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ subject | default("Kubera Notification") }}</title>
  <style>
    body {
      margin: 0;
      padding: 0;
      background-color: #f4f6f8;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #1e293b;
      line-height: 1.6;
    }
    .wrapper {
      width: 100%;
      background-color: #f4f6f8;
      padding: 40px 16px;
    }
    .container {
      max-width: 600px;
      margin: 0 auto;
      background: #ffffff;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 4px 12px rgba(0,0,0,0.06);
      border: 1px solid #e2e8f0;
    }
    .header {
      background-color: #0f172a;
      padding: 24px 32px;
      text-align: left;
    }
    .header h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
      color: #ffffff;
      letter-spacing: 0.5px;
    }
    .content {
      padding: 32px;
    }
    .button-container {
      margin: 28px 0;
      text-align: left;
    }
    .button {
      display: inline-block;
      padding: 12px 24px;
      background-color: #2563eb;
      color: #ffffff !important;
      text-decoration: none;
      font-weight: 600;
      border-radius: 6px;
      font-size: 15px;
    }
    .footer {
      background-color: #f8fafc;
      padding: 20px 32px;
      font-size: 12px;
      color: #64748b;
      border-top: 1px solid #e2e8f0;
      line-height: 1.5;
    }
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <h1>Kubera Compliance</h1>
      </div>
      <div class="content">
        {% block content %}{% endblock %}
      </div>
      <div class="footer">
        {% block footer %}
          <p style="margin: 0 0 4px 0;"><strong>Kubera Corporate Compliance</strong></p>
          <p style="margin: 0;">{{ footer_note | default("This email was sent by Kubera on behalf of ethdc.in. If you have questions, please contact support.") }}</p>
        {% endblock %}
      </div>
    </div>
  </div>
</body>
</html>
```

`app/services/email/templates/branded_message.html`:
```html
{% extends "base.html" %}

{% block content %}
  {% if headline %}
    <h2 style="margin-top: 0; color: #0f172a; font-size: 18px; font-weight: 600;">{{ headline }}</h2>
  {% endif %}

  {% for paragraph in paragraphs %}
    <p style="margin-bottom: 16px; color: #334155;">{{ paragraph }}</p>
  {% endfor %}

  {% if action_button and action_button.url and action_button.label %}
    <div class="button-container">
      <a href="{{ action_button.url }}" class="button" target="_blank">{{ action_button.label }}</a>
    </div>
  {% endif %}
{% endblock %}
```

`app/services/email/templates.py`:
```python
import os
import re
from typing import Any, Dict, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_email_template(template_name: str, context: Optional[Dict[str, Any]] = None) -> str:
    ctx = context or {}
    template = env.get_template(template_name)
    return template.render(**ctx)


def extract_plain_text(html_content: str) -> str:
    """Strip tags and format cleanly for fallback text email body."""
    text = re.sub(r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h1>|</h2>|</h3>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<a[^>]*href=[\"'](.*?)[\"'][^>]*>(.*?)</a>", r"\2 (\1)", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()
```

`app/services/email/__init__.py`:
```python
from app.services.email.schemas import (
    EmailAttachment,
    EmailConfig,
    EmailDeliveryError,
    EmailDeliveryResult,
    EmailMessage,
)
from app.services.email.templates import extract_plain_text, render_email_template

__all__ = [
    "EmailAttachment",
    "EmailConfig",
    "EmailDeliveryError",
    "EmailDeliveryResult",
    "EmailMessage",
    "extract_plain_text",
    "render_email_template",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_email_templates.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/email tests/test_email_templates.py
git commit -m "feat(email): add email schemas, Jinja2 template engine, and responsive layouts"
```

---

### Task 3: Core SMTP Client Transport & Delivery Service

**Files:**
- Create: `app/services/email/client.py`
- Modify: `app/services/email/__init__.py`
- Test: `tests/test_email_service.py`

**Interfaces:**
- Consumes: `EmailConfig`, `EmailMessage`, `EmailDeliveryResult`, `EmailDeliveryError`, `app.config.get_settings`.
- Produces: `EmailService.send(message: EmailMessage) -> EmailDeliveryResult`, `EmailService.verify_connection() -> Dict[str, Any]`.

- [ ] **Step 1: Write the failing tests for EmailService transport**

```python
# tests/test_email_service.py
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
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

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


@patch("smtplib.SMTP")
def test_send_email_auth_failure(mock_smtp_class, mock_config):
    mock_smtp_instance = MagicMock()
    mock_smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

    service = EmailService(config=mock_config)
    message = EmailMessage(to=["recipient@example.com"], subject="Test", body_text="Hello")

    with pytest.raises(EmailDeliveryError, match="SMTP authentication failed"):
        service.send(message)


@patch("smtplib.SMTP")
def test_verify_connection(mock_smtp_class, mock_config):
    mock_smtp_instance = MagicMock()
    mock_smtp_instance.noop.return_value = (250, b"OK")
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

    service = EmailService(config=mock_config)
    res = service.verify_connection()

    assert res["status"] == "ok"
    assert res["host"] == "smtp.ethdc.in"
    assert res["port"] == 587
    assert res["user"] == "kubera@ethdc.in"
    assert "latency_ms" in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_email_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.email.client'`

- [ ] **Step 3: Implement `app/services/email/client.py`**

```python
import email.utils
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
import logging
import smtplib
import socket
import ssl
import time
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.services.email.schemas import (
    EmailAttachment,
    EmailConfig,
    EmailDeliveryError,
    EmailDeliveryResult,
    EmailMessage,
)
from app.services.email.templates import extract_plain_text, render_email_template

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, config: Optional[EmailConfig] = None):
        if config:
            self.config = config
        else:
            settings = get_settings()
            self.config = EmailConfig(
                host=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                user=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=settings.SMTP_USE_TLS,
                use_ssl=settings.SMTP_USE_SSL,
                from_email=settings.SMTP_FROM_EMAIL,
                from_name=settings.SMTP_FROM_NAME,
                timeout=settings.SMTP_TIMEOUT,
            )

    def _get_connection(self):
        """Create and connect SMTP/SMTP_SSL client."""
        if not self.config.host:
            raise EmailDeliveryError("SMTP_HOST is not configured.")

        timeout = self.config.timeout
        if self.config.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(self.config.host, self.config.port, timeout=timeout, context=context)
        else:
            server = smtplib.SMTP(self.config.host, self.config.port, timeout=timeout)
            if self.config.use_tls:
                context = ssl.create_default_context()
                server.starttls(context=context)

        if self.config.user and self.config.password:
            try:
                server.login(self.config.user, self.config.password)
            except smtplib.SMTPAuthenticationError as e:
                raise EmailDeliveryError(f"SMTP authentication failed for user '{self.config.user}': {e.smtp_error.decode('utf-8', errors='ignore') if isinstance(e.smtp_error, bytes) else str(e)}")

        return server

    def build_mime_message(self, message: EmailMessage) -> MIMEMultipart:
        """Compose standard RFC multipart email message."""
        # Top-level container
        if message.attachments:
            root = MIMEMultipart("mixed")
            alt_container = MIMEMultipart("alternative")
            root.attach(alt_container)
        else:
            root = MIMEMultipart("alternative")
            alt_container = root

        # Render HTML from template if provided
        html_body = message.body_html
        if message.template_name:
            html_body = render_email_template(message.template_name, message.template_context or {})

        text_body = message.body_text
        if not text_body and html_body:
            text_body = extract_plain_text(html_body)
        elif not text_body:
            text_body = ""

        # Attach text and html parts
        part_text = MIMEText(text_body, "plain", "utf-8")
        alt_container.attach(part_text)

        if html_body:
            part_html = MIMEText(html_body, "html", "utf-8")
            alt_container.attach(part_html)

        # Attachments
        if message.attachments:
            for att in message.attachments:
                maintype, _, subtype = att.content_type.partition("/")
                part_att = MIMEBase(maintype or "application", subtype or "octet-stream")
                part_att.set_payload(att.content)
                encoders.encode_base64(part_att)
                part_att.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{att.filename}"',
                )
                root.attach(part_att)

        # Headers
        from_header = (
            f"{self.config.from_name} <{self.config.from_email}>"
            if self.config.from_name
            else self.config.from_email
        )
        root["From"] = from_header
        root["To"] = ", ".join(message.to)
        root["Subject"] = message.subject
        root["Date"] = email.utils.formatdate(localtime=True)
        root["Message-ID"] = email.utils.make_msgid(domain=self.config.from_email.split("@")[-1])

        if message.cc:
            root["Cc"] = ", ".join(message.cc)
        if message.reply_to:
            root["Reply-To"] = message.reply_to

        return root

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        """Send an email synchronously via SMTP."""
        if not message.to:
            raise EmailDeliveryError("Cannot send email: recipient list ('to') is empty.")

        all_recipients: List[str] = list(message.to)
        if message.cc:
            all_recipients.extend(message.cc)
        if message.bcc:
            all_recipients.extend(message.bcc)

        start_time = time.perf_counter()
        mime = self.build_mime_message(message)
        message_id = mime["Message-ID"]

        try:
            with self._get_connection() as server:
                server.send_message(mime, from_addr=self.config.from_email, to_addrs=all_recipients)
        except EmailDeliveryError:
            raise
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as e:
            raise EmailDeliveryError(f"SMTP rejected address: {e}")
        except smtplib.SMTPException as e:
            raise EmailDeliveryError(f"SMTP protocol error during sending: {e}")
        except (socket.timeout, TimeoutError, OSError) as e:
            raise EmailDeliveryError(f"SMTP network/connection error: {e}")

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            f"Email sent successfully to {len(all_recipients)} recipients in {duration_ms:.2f}ms (Message-ID: {message_id})"
        )

        return EmailDeliveryResult(
            success=True,
            message_id=message_id,
            recipients=all_recipients,
            duration_ms=duration_ms,
        )

    def verify_connection(self) -> Dict[str, Any]:
        """Test handshake and authentication without sending an email."""
        start_time = time.perf_counter()
        try:
            with self._get_connection() as server:
                code, resp = server.noop()
        except Exception as e:
            raise EmailDeliveryError(f"SMTP connection test failed: {e}")

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "status": "ok",
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user or "(anonymous)",
            "use_tls": self.config.use_tls,
            "use_ssl": self.config.use_ssl,
            "latency_ms": round(latency_ms, 2),
            "response": resp.decode("utf-8", errors="ignore") if isinstance(resp, bytes) else str(resp),
        }
```

Update `app/services/email/__init__.py`:
```python
from app.services.email.client import EmailService
from app.services.email.schemas import (
    EmailAttachment,
    EmailConfig,
    EmailDeliveryError,
    EmailDeliveryResult,
    EmailMessage,
)
from app.services.email.templates import extract_plain_text, render_email_template

__all__ = [
    "EmailAttachment",
    "EmailConfig",
    "EmailDeliveryError",
    "EmailDeliveryResult",
    "EmailMessage",
    "EmailService",
    "extract_plain_text",
    "render_email_template",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_email_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/email/client.py app/services/email/__init__.py tests/test_email_service.py
git commit -m "feat(email): implement core SMTP EmailService transport and verification"
```

---

### Task 4: Celery Background Tasks & Worker Integration

**Files:**
- Create: `app/services/email/tasks.py`
- Modify: `app/worker.py`
- Test: `tests/test_email_tasks.py`

**Interfaces:**
- Consumes: `EmailService`, `EmailMessage`, `EmailConfig`.
- Produces: Celery task `send_email_async.delay(message_dict, config_dict=None)`.

- [ ] **Step 1: Write the failing tests for Celery email task**

```python
# tests/test_email_tasks.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_email_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.email.tasks'`

- [ ] **Step 3: Implement `app/services/email/tasks.py` and register with `app/worker.py`**

`app/services/email/tasks.py`:
```python
import smtplib
from typing import Any, Dict, Optional
from app.services.email.client import EmailService
from app.services.email.schemas import EmailConfig, EmailMessage
from app.worker import celery_app


@celery_app.task(
    name="app.services.email.tasks.send_email_async",
    autoretry_for=(smtplib.SMTPException, OSError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def send_email_async(message_dict: Dict[str, Any], config_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Celery background task for asynchronous email delivery with automatic retries."""
    config = EmailConfig(**config_dict) if config_dict else None
    message = EmailMessage(**message_dict)
    service = EmailService(config=config)
    result = service.send(message)
    return result.model_dump()
```

In `app/worker.py`, import the tasks to ensure registration:
```python
# Import celery tasks so worker discovers them upon startup
import app.services.email.tasks  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_email_tasks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/email/tasks.py app/worker.py tests/test_email_tasks.py
git commit -m "feat(email): add Celery async email task with exponential retries"
```

---

### Task 5: Standalone Operator CLI Tool (`send_email.py`)

**Files:**
- Create: `send_email.py`
- Test: `tests/test_email_cli.py`

**Interfaces:**
- Consumes: `EmailService`, `EmailMessage`, `EmailAttachment`, `EmailDeliveryError`, `send_email_async`.
- Produces: Executable CLI `python send_email.py [flags]`.

- [ ] **Step 1: Write the failing tests for CLI parser and runner**

```python
# tests/test_email_cli.py
from unittest.mock import MagicMock, patch
import pytest
from send_email import build_parser, run_cli


def test_cli_parser_flags():
    parser = build_parser()
    args = parser.parse_args([
        "--to", "alice@example.com,bob@example.com",
        "--subject", "Notice",
        "--body", "Hello World",
        "--attach", "tests/test_email_cli.py",
        "--async",
    ])
    assert args.to == "alice@example.com,bob@example.com"
    assert args.subject == "Notice"
    assert args.body == "Hello World"
    assert args.attach == ["tests/test_email_cli.py"]
    assert args.is_async is True


@patch("send_email.EmailService")
def test_run_cli_verify(mock_service_class, capsys):
    mock_service_instance = MagicMock()
    mock_service_instance.verify_connection.return_value = {
        "status": "ok",
        "host": "smtp.ethdc.in",
        "port": 587,
        "user": "kubera@ethdc.in",
        "latency_ms": 120.5,
        "response": "250 OK",
    }
    mock_service_class.return_value = mock_service_instance

    code = run_cli(["--verify"])
    assert code == 0
    captured = capsys.readouterr()
    assert "SMTP connection verified" in captured.out


@patch("send_email.EmailService")
def test_run_cli_send_direct(mock_service_class, capsys):
    mock_service_instance = MagicMock()
    mock_service_instance.send.return_value = MagicMock(
        success=True,
        message_id="<msg123@ethdc.in>",
        recipients=["alice@example.com"],
        duration_ms=250.0,
    )
    mock_service_class.return_value = mock_service_instance

    code = run_cli([
        "--to", "alice@example.com",
        "--subject", "Report",
        "--body", "Report details.",
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "Email sent successfully" in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_email_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'send_email'`

- [ ] **Step 3: Implement `send_email.py`**

`send_email.py`:
```python
#!/usr/bin/env python3
"""Kubera Email CLI Operator Tool.

Send emails from kubera@ethdc.in (or configured SMTP) via interactive prompts
or one-liner command line flags, with support for branded HTML templates,
plain text, attachments, connection verification, and async background queuing.

Usage:
    # Interactive wizard
    python send_email.py

    # Verify SMTP credentials and connection
    python send_email.py --verify

    # Quick send
    python send_email.py --to user@example.com --subject "Welcome" --body "Hello"

    # Branded email with attachment
    python send_email.py --to user@example.com --subject "Audit Report" --body-file message.txt --attach report.pdf
"""
import argparse
import mimetypes
import os
import sys
from typing import List, Optional

# Ensure project root is in sys.path when script is run directly
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app.config import get_settings
from app.services.email.client import EmailService
from app.services.email.schemas import (
    EmailAttachment,
    EmailConfig,
    EmailDeliveryError,
    EmailMessage,
)
from app.services.email.tasks import send_email_async


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kubera Email Operator Tool — send emails via SMTP or Celery.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-t", "--to", help="Recipient email address(es), comma-separated.")
    parser.add_argument("-s", "--subject", help="Email subject line.")
    parser.add_argument("-b", "--body", help="Email body text.")
    parser.add_argument("-f", "--body-file", help="Path to text or HTML file containing body.")
    parser.add_argument("--html", action="store_true", help="Treat input body as raw HTML.")
    parser.add_argument("--plain", action="store_true", help="Send strictly plain text without branded HTML template.")
    parser.add_argument("-a", "--attach", action="append", help="Path to file to attach (can be specified multiple times).")
    parser.add_argument("--cc", help="CC recipient email address(es), comma-separated.")
    parser.add_argument("--bcc", help="BCC recipient email address(es), comma-separated.")
    parser.add_argument("--from-email", help="Override default sender email address.")
    parser.add_argument("--from-name", help="Override default sender display name.")
    parser.add_argument("--async", dest="is_async", action="store_true", help="Dispatch email to background Celery queue.")
    parser.add_argument("--verify", action="store_true", help="Verify SMTP connection and credentials without sending.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Force interactive prompt mode.")
    return parser


def prompt(label: str, default: Optional[str] = None) -> str:
    try:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{label}{suffix}: ").strip()
        return raw if raw else (default or "")
    except (EOFError, KeyboardInterrupt):
        sys.exit("\nAborted.")


def run_interactive(settings) -> int:
    from_email = settings.SMTP_FROM_EMAIL or "kubera@ethdc.in"
    from_name = settings.SMTP_FROM_NAME or "Kubera Compliance"

    print("\n" + "=" * 58)
    print("             KUBERA EMAIL OPERATOR WIZARD")
    print(f"       Sender: {from_name} <{from_email}>")
    print("=" * 58 + "\n")

    to_raw = prompt("Recipient email(s) (comma-separated)")
    if not to_raw:
        print("error: recipient is required.")
        return 1
    to_list = [e.strip() for e in to_raw.split(",") if e.strip()]

    cc_raw = prompt("CC email(s) (optional)")
    cc_list = [e.strip() for e in cc_raw.split(",") if e.strip()] if cc_raw else None

    bcc_raw = prompt("BCC email(s) (optional)")
    bcc_list = [e.strip() for e in bcc_raw.split(",") if e.strip()] if bcc_raw else None

    subject = prompt("Subject")
    if not subject:
        print("error: subject is required.")
        return 1

    format_choice = prompt("Format [1=Branded Kubera HTML, 2=Plain Text]", default="1")
    is_plain = format_choice == "2"

    body_input = prompt("Body text (or path to .txt/.html file)")
    if not body_input:
        print("error: body cannot be empty.")
        return 1

    body_text: Optional[str] = None
    body_html: Optional[str] = None
    template_name: Optional[str] = None
    template_context: Optional[dict] = None

    if os.path.isfile(body_input):
        with open(body_input, "r", encoding="utf-8") as fh:
            content = fh.read()
        if body_input.endswith(".html") or "<html" in content or "<p>" in content:
            body_html = content
        else:
            body_text = content
    else:
        if is_plain:
            body_text = body_input
        else:
            template_name = "branded_message.html"
            template_context = {
                "headline": subject,
                "paragraphs": [p.strip() for p in body_input.split("\n\n") if p.strip()],
            }

    attach_path = prompt("Attachment path (optional)")
    attachments: Optional[List[EmailAttachment]] = None
    if attach_path:
        if not os.path.isfile(attach_path):
            print(f"error: attachment file not found: {attach_path}")
            return 1
        ctype, _ = mimetypes.guess_type(attach_path)
        with open(attach_path, "rb") as fh:
            attachments = [
                EmailAttachment(
                    filename=os.path.basename(attach_path),
                    content=fh.read(),
                    content_type=ctype or "application/octet-stream",
                )
            ]

    print("\n" + "-" * 58)
    print(f"  To        : {', '.join(to_list)}")
    if cc_list:
        print(f"  CC        : {', '.join(cc_list)}")
    if bcc_list:
        print(f"  BCC       : {', '.join(bcc_list)}")
    print(f"  Subject   : {subject}")
    print(f"  Format    : {'Plain Text' if is_plain else 'Branded HTML'}")
    if attachments:
        print(f"  Attachment: {attachments[0].filename}")
    print("-" * 58)

    confirm = prompt("Send this email now? [Y/n]", default="y")
    if confirm.lower() not in ("y", "yes"):
        print("Cancelled.")
        return 0

    message = EmailMessage(
        to=to_list,
        cc=cc_list,
        bcc=bcc_list,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        template_name=template_name,
        template_context=template_context,
        attachments=attachments,
    )

    print("\nConnecting to SMTP server...")
    service = EmailService()
    try:
        res = service.send(message)
        print(f"✓ Email sent successfully in {res.duration_ms:.2f}ms!")
        print(f"  Message-ID: {res.message_id}\n")
        return 0
    except EmailDeliveryError as e:
        print(f"✗ Failed to send email: {e}\n")
        return 1


def run_cli(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()

    # If --verify is passed
    if args.verify:
        print("\nVerifying SMTP connection...")
        custom_config = None
        if args.from_email or args.from_name:
            custom_config = EmailConfig(
                host=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                user=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=settings.SMTP_USE_TLS,
                use_ssl=settings.SMTP_USE_SSL,
                from_email=args.from_email or settings.SMTP_FROM_EMAIL,
                from_name=args.from_name or settings.SMTP_FROM_NAME,
                timeout=settings.SMTP_TIMEOUT,
            )
        service = EmailService(config=custom_config)
        try:
            res = service.verify_connection()
            print("✓ SMTP connection verified successfully!")
            print(f"  Host   : {res['host']}:{res['port']}")
            print(f"  User   : {res['user']}")
            print(f"  TLS/SSL: TLS={res['use_tls']}, SSL={res['use_ssl']}")
            print(f"  Latency: {res['latency_ms']}ms\n")
            return 0
        except EmailDeliveryError as e:
            print(f"✗ SMTP connection check failed: {e}\n")
            return 1

    # If no flags passed or --interactive
    if (not args.to and not args.subject and not args.body) or args.interactive:
        return run_interactive(settings)

    # Validate required CLI args
    if not args.to or not args.subject:
        print("error: --to and --subject are required when not running interactively.")
        return 1

    to_list = [e.strip() for e in args.to.split(",") if e.strip()]
    cc_list = [e.strip() for e in args.cc.split(",") if e.strip()] if args.cc else None
    bcc_list = [e.strip() for e in args.bcc.split(",") if e.strip()] if args.bcc else None

    body_text: Optional[str] = None
    body_html: Optional[str] = None
    template_name: Optional[str] = None
    template_context: Optional[dict] = None

    if args.body_file:
        if not os.path.isfile(args.body_file):
            print(f"error: file not found: {args.body_file}")
            return 1
        with open(args.body_file, "r", encoding="utf-8") as fh:
            content = fh.read()
        if args.html or args.body_file.endswith(".html"):
            body_html = content
        else:
            body_text = content
    elif args.body:
        if args.html:
            body_html = args.body
        elif args.plain:
            body_text = args.body
        else:
            template_name = "branded_message.html"
            template_context = {
                "headline": args.subject,
                "paragraphs": [p.strip() for p in args.body.split("\n\n") if p.strip()],
            }
    else:
        body_text = ""

    attachments: Optional[List[EmailAttachment]] = None
    if args.attach:
        attachments = []
        for path in args.attach:
            if not os.path.isfile(path):
                print(f"error: attachment not found: {path}")
                return 1
            ctype, _ = mimetypes.guess_type(path)
            with open(path, "rb") as fh:
                attachments.append(
                    EmailAttachment(
                        filename=os.path.basename(path),
                        content=fh.read(),
                        content_type=ctype or "application/octet-stream",
                    )
                )

    message = EmailMessage(
        to=to_list,
        cc=cc_list,
        bcc=bcc_list,
        subject=args.subject,
        body_text=body_text,
        body_html=body_html,
        template_name=template_name,
        template_context=template_context,
        attachments=attachments,
    )

    custom_config = None
    if args.from_email or args.from_name:
        custom_config = EmailConfig(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            user=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=settings.SMTP_USE_TLS,
            use_ssl=settings.SMTP_USE_SSL,
            from_email=args.from_email or settings.SMTP_FROM_EMAIL,
            from_name=args.from_name or settings.SMTP_FROM_NAME,
            timeout=settings.SMTP_TIMEOUT,
        )

    if args.is_async:
        print(f"Dispatching email to Celery background queue for {len(to_list)} recipient(s)...")
        task = send_email_async.delay(
            message.model_dump(),
            custom_config.model_dump() if custom_config else None,
        )
        print(f"✓ Email task queued successfully (Task ID: {task.id})\n")
        return 0

    service = EmailService(config=custom_config)
    try:
        res = service.send(message)
        print(f"✓ Email sent successfully to {len(res.recipients)} recipient(s) in {res.duration_ms:.2f}ms!")
        print(f"  Message-ID: {res.message_id}\n")
        return 0
    except EmailDeliveryError as e:
        print(f"✗ Failed to send email: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_cli())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_email_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add send_email.py tests/test_email_cli.py
git commit -m "feat(cli): add standalone operator email CLI tool send_email.py"
```

---

### Task 6: Full Suite Verification & Documentation

**Files:**
- Modify: `README.md`
- Test: Full test suite (`pytest tests/test_email_*.py`)

**Interfaces:**
- Consumes: All modules from Tasks 1-5.
- Produces: Clean test run and updated operational documentation in `README.md`.

- [ ] **Step 1: Run complete email test suite**

Run: `pytest tests/test_email_config.py tests/test_email_templates.py tests/test_email_service.py tests/test_email_tasks.py tests/test_email_cli.py -v`
Expected: All tests PASS.

- [ ] **Step 2: Update `README.md` with Email CLI Operator documentation**

Add section to `README.md`:
```markdown
### Sending Emails (Operator CLI)

Kubera includes a standalone operator CLI script `send_email.py` for sending transactional, branded, or plain-text emails:

```bash
# Verify SMTP connection
python send_email.py --verify

# Interactive wizard
python send_email.py

# Send branded email with attachment
python send_email.py --to client@example.com --subject "Audit Notice" --body "Your report is attached." --attach ./report.pdf

# Dispatch via Celery background worker
python send_email.py --to client@example.com --subject "Notice" --body "Queued email" --async
```
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add email operator CLI documentation to README"
```
