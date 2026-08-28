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
        "use_tls": True,
        "use_ssl": False,
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
