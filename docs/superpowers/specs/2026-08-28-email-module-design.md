# Kubera Email Module & CLI Tool Design Spec

## Overview
This specification details the architecture, design, and implementation of an isolated, extensible email module and operator CLI tool for Kubera. The system enables the application administrator to send secure, fast, and branded product emails from a configurable sender address (`kubera@ethdc.in` by default) via CLI, while providing an asynchronous Celery task pipeline and an extensible multi-tenant SMTP architecture ready for per-company mail integration.

---

## 1. Architecture & Core Concepts

The email system is split into three decoupled layers:
1. **Core Service Layer (`app/services/email/`)**: Encapsulates data schemas, standard SMTP protocol connections (STARTTLS / SSL), Jinja2 template rendering, MIME composition, attachment encoding, and Celery tasks.
2. **CLI Operator Tool (`send_email.py`)**: Standalone, interactive and scriptable operator CLI located in the repository root (matching existing operator tools like `create_company.py`).
3. **Background Worker Pipeline (`app/worker.py` / Celery)**: Asynchronous task queue for non-blocking email dispatching from API endpoints or scheduled jobs.

```
┌────────────────────────────────────────────────────────┐
│                      Caller Layers                     │
│  ┌───────────────────────┐   ┌──────────────────────┐  │
│  │ CLI (send_email.py)   │   │ FastAPI Endpoints /  │  │
│  │ (Interactive / Flags) │   │ Background Jobs      │  │
│  └───────────┬───────────┘   └──────────┬───────────┘  │
└──────────────┼──────────────────────────┼──────────────┘
               │                          │
               ▼ (direct/sync)            ▼ (async task)
┌────────────────────────────────────────────────────────┐
│  Email Service Layer (app/services/email/)             │
│  ├── schemas.py       -> EmailMessage, EmailConfig     │
│  ├── client.py        -> SMTP transport, SSL/TLS       │
│  ├── templates.py     -> Jinja2 template engine        │
│  ├── templates/       -> Branded HTML & text templates │
│  └── tasks.py         -> Celery async tasks & retries  │
└────────────────────────────────────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────────────────┐
│  External SMTP Relay (e.g. ethdc.in mail server)       │
└────────────────────────────────────────────────────────┘
```

---

## 2. Configuration & Environment Variables

### Environment Variables (`.env` and `app/config.py`)
All mail configurations are read through Pydantic `BaseSettings` with environment fallbacks:

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `SMTP_HOST` | `str` | `""` | SMTP relay server hostname (e.g. `smtp.ethdc.in` or `mail.ethdc.in`) |
| `SMTP_PORT` | `int` | `587` | Port (587 for STARTTLS, 465 for SSL, 25 for local/unencrypted) |
| `SMTP_USER` | `str` | `""` | SMTP authentication username / mailbox address |
| `SMTP_PASSWORD` | `str` | `""` | SMTP authentication password / app password |
| `SMTP_USE_TLS` | `bool` | `True` | Enable STARTTLS encryption (recommended for port 587) |
| `SMTP_USE_SSL` | `bool` | `False` | Enable direct SSL socket encryption (for port 465) |
| `SMTP_FROM_EMAIL` | `str` | `kubera@ethdc.in` | Default sender email address |
| `SMTP_FROM_NAME` | `str` | `Kubera Compliance` | Default sender display name |
| `SMTP_TIMEOUT` | `int` | `15` | Socket connection and command timeout in seconds |

### Dynamic / Multi-Tenant Configuration (`EmailConfig`)
To support per-company custom SMTP in future phases without breaking changes:
* `EmailConfig` model holds all connection settings.
* `EmailService(config: Optional[EmailConfig] = None)` defaults to global `get_settings()` when `config` is omitted, but can take a custom `EmailConfig` instance loaded at runtime for any tenant.

---

## 3. Data Models & Schemas (`app/services/email/schemas.py`)

### `EmailAttachment`
* `filename: str`
* `content: bytes`
* `content_type: str = "application/octet-stream"`

### `EmailMessage`
* `to: List[str]`
* `subject: str`
* `body_text: Optional[str] = None`
* `body_html: Optional[str] = None`
* `cc: Optional[List[str]] = None`
* `bcc: Optional[List[str]] = None`
* `reply_to: Optional[str] = None`
* `attachments: Optional[List[EmailAttachment]] = None`
* `template_name: Optional[str] = None` (e.g. `"branded_message.html"`)
* `template_context: Optional[Dict[str, Any]] = None`

---

## 4. SMTP Client Transport & Engine (`app/services/email/client.py`)

### Connection Lifecycle
* Support `smtplib.SMTP_SSL` when `use_ssl=True` and `smtplib.SMTP` + `starttls(context=ssl.create_default_context())` when `use_tls=True`.
* Automatic authentication when `user` and `password` are provided.
* Robust exception handling mapping standard SMTP exceptions (`SMTPAuthenticationError`, `SMTPConnectError`, `SMTPSenderRefused`, `SMTPRecipientsRefused`, `socket.timeout`) into human-readable `EmailDeliveryError` exceptions.

### MIME Message Composition
* Builds RFC 5322 multipart message:
  * Top-level `multipart/mixed` if attachments exist.
  * Inner `multipart/alternative` containing `text/plain` and `text/html` parts.
* Standard headers:
  * `From`: `"{from_name} <{from_email}>"`
  * `To`: comma-separated recipients
  * `Cc`: comma-separated CC recipients
  * `Subject`: subject line with proper RFC 2047 header encoding if non-ASCII
  * `Date`: RFC 2822 formatted date
  * `Message-ID`: `<{uuid}@{host}>`
  * `Reply-To`: optional reply address
* Attachments are encoded using standard `MIMEBase` with base64 payload and `Content-Disposition: attachment; filename="..."`.

### Connection Verification
* `verify_connection() -> Dict[str, Any]`: Performs connection, TLS handshake, and authentication, then cleanly disconnects, returning connection latency (ms) and server greeting.

---

## 5. Templating Engine (`app/services/email/templates/`)

* Uses `jinja2.Environment` with `FileSystemLoader` pointing to `app/services/email/templates`.
* Templates provided:
  * `base.html`: Modern, responsive HTML email boilerplate with Kubera branding, neutral background, centered card, custom header logo/text, action button styling, and compliance footer.
  * `branded_message.html`: Extends `base.html`, accepting `headline`, `content_paragraphs`, `action_button` (label + url), and `footer_note`.
* Plain-text fallback generation: Automatically converts paragraph content and links into clean markdown-style plain text when only HTML or template variables are supplied.

---

## 6. Celery Background Tasks (`app/services/email/tasks.py`)

* Registered task `send_email_task(message_dict: dict, config_dict: Optional[dict] = None)`.
* Uses Celery's `autoretry_for=(smtplib.SMTPException, OSError, TimeoutError)` with `retry_backoff=True`, `max_retries=3`, and jitter.
* Returns delivery status dictionary: `{"status": "sent", "message_id": "<...>", "recipients": [...]}`.

---

## 7. CLI Tool Interface (`send_email.py`)

Located in the root repository folder, executable via `python send_email.py`.

### Modes of Operation
1. **Interactive Wizard Mode** (invoked when run with no arguments or `--interactive`):
   * Prompts sequentially for:
     1. Recipient email(s) (comma-separated).
     2. CC / BCC (optional).
     3. Subject line.
     4. Formatting choice (1: Branded Kubera HTML template, 2: Plain text).
     5. Message body (or file path).
     6. Attachment path (optional).
     7. Confirmation before sending.
   * Displays step-by-step progress: connection, authentication, delivery latency, and Message-ID.

2. **Flag / One-Liner Mode**:
   * Arguments supported:
     * `--to`, `-t`: One or more recipient emails (comma-separated or multiple flags).
     * `--subject`, `-s`: Subject line.
     * `--body`, `-b`: Body text.
     * `--body-file`, `-f`: Read body from path (supports `.txt` and `.html`).
     * `--html`: Treat input body as raw HTML.
     * `--plain`: Send as raw plain text rather than wrapping in branded template.
     * `--attach`, `-a`: File path(s) to attach.
     * `--cc`, `--bcc`: CC and BCC recipient addresses.
     * `--from-email`: Override default sender address.
     * `--from-name`: Override default sender display name.
     * `--async`: Dispatch to Celery background queue.
     * `--verify`: Test SMTP connection and credentials without sending.

---

## 8. Verification & Test Plan

### Automated Tests
1. `tests/test_email_service.py`:
   * Test SMTP client connection handling with mock server (`unittest.mock`).
   * Test MIME generation for plain text, HTML, and dual-format messages.
   * Test attachment binary encoding and MIME header parameters.
   * Test error translation for invalid credentials, connection failures, and invalid addresses.
   * Test Jinja2 template rendering.
2. `tests/test_email_tasks.py`:
   * Test Celery task execution and retry triggers.
3. `tests/test_email_cli.py`:
   * Test CLI argument parser for all flags.
   * Test interactive prompt flow execution with mock inputs.

### Manual Verification
* Run `python send_email.py --verify` with real SMTP credentials to verify handshake.
* Send test email with `--to` and `--subject` to verify delivery.
* Send test email with `--attach` to verify attachment integrity in email client.
