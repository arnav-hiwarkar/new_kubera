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

from jinja2 import TemplateNotFound

from app.config import get_settings
from app.services.email.schemas import (
    EmailAttachment,
    EmailConfig,
    EmailDeliveryError,
    EmailDeliveryResult,
    EmailMessage,
)
from app.services.email.net_guard import resolve_public_smtp_target, BlockedSmtpTarget
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

        # Resolve host and ensure it's a public IP to prevent SSRF
        try:
            safe_ip = resolve_public_smtp_target(self.config.host, self.config.port)
        except BlockedSmtpTarget as exc:
            raise EmailDeliveryError(str(exc)) from exc

        timeout = self.config.timeout
        if self.config.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(timeout=timeout, context=context)
            server._host = self.config.host  # SNI pinning
            server.connect(safe_ip, self.config.port)
        else:
            server = smtplib.SMTP(timeout=timeout)
            server._host = self.config.host  # SNI pinning for starttls
            server.connect(safe_ip, self.config.port)

        try:
            if not self.config.use_ssl and self.config.use_tls:
                context = ssl.create_default_context()
                server.starttls(context=context)

            if self.config.user and self.config.password:
                server.login(self.config.user, self.config.password)
        except smtplib.SMTPAuthenticationError as e:
            server.close()
            err_msg = e.smtp_error.decode("utf-8", errors="ignore") if isinstance(e.smtp_error, bytes) else str(e)
            raise EmailDeliveryError(f"SMTP authentication failed for user '{self.config.user}': {err_msg}")
        except Exception:
            server.close()
            raise

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
            try:
                html_body = render_email_template(message.template_name, message.template_context or {})
            except TemplateNotFound:
                raise EmailDeliveryError(f"Email template '{message.template_name}' not found.")

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
                    "Content-Disposition", "attachment", filename=att.filename
                )
                root.attach(part_att)

        # Headers — RFC 5322 compliant, handles special chars and non-ASCII
        root["From"] = email.utils.formataddr(
            (self.config.from_name, self.config.from_email)
        )
        root["To"] = ", ".join(message.to)
        root["Subject"] = message.subject
        root["Date"] = email.utils.formatdate(localtime=True)
        domain = self.config.from_email.split("@")[-1] if "@" in self.config.from_email else "ethdc.in"
        root["Message-ID"] = email.utils.make_msgid(domain=domain)

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
                if code != 250:
                    resp_str = resp.decode("utf-8", errors="ignore") if isinstance(resp, bytes) else str(resp)
                    raise EmailDeliveryError(f"SMTP NOOP check returned status {code}: {resp_str}")
        except EmailDeliveryError:
            raise
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
