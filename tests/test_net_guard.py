import pytest
from app.services.email.net_guard import resolve_public_smtp_target, BlockedSmtpTarget

def test_resolve_public_smtp_target_blocks_private():
    with pytest.raises(BlockedSmtpTarget):
        resolve_public_smtp_target("127.0.0.1", 587)
    with pytest.raises(BlockedSmtpTarget):
        resolve_public_smtp_target("localhost", 587)
    with pytest.raises(BlockedSmtpTarget):
        resolve_public_smtp_target("169.254.169.254", 587)
    with pytest.raises(BlockedSmtpTarget):
        resolve_public_smtp_target("0.0.0.0", 587)

def test_resolve_public_smtp_target_blocks_invalid_ports():
    with pytest.raises(BlockedSmtpTarget, match="not a permitted SMTP port"):
        resolve_public_smtp_target("smtp.gmail.com", 6379)

def test_resolve_public_smtp_target_allows_public(monkeypatch):
    import socket
    # Mock DNS resolution to return a public IP
    def mock_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 587))]
    monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
    
    ip = resolve_public_smtp_target("smtp.example.com", 587)
    assert ip == "8.8.8.8"
