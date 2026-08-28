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
