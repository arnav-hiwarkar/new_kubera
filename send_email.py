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
