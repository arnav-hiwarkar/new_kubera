import ipaddress
import socket
import pytest
from app.services.email.net_guard import (
    ALLOWED_PORTS,
    BlockedSmtpTarget,
    is_ip_blocked,
    resolve_public_smtp_target,
)


@pytest.mark.parametrize(
    "host",
    [
        # Loopback
        "127.0.0.1",
        "127.0.0.2",
        "127.1",
        "localhost",
        "::1",
        "[::1]",
        # RFC 1918 Private ranges
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "192.168.0.254",
        # Cloud metadata / Link-local
        "169.254.169.254",
        "169.254.1.1",
        "fe80::1",
        # CGNAT (RFC 6598)
        "100.64.0.1",
        "100.127.255.255",
        # Unspecified / Current network / Broadcast / Reserved
        "0.0.0.0",
        "::",
        "255.255.255.255",
        "240.0.0.1",
        # Multicast
        "224.0.0.1",
        "ff02::1",
        # IPv6 Unique Local (ULA)
        "fc00::1",
        "fd00::1",
        # IPv4-mapped IPv6
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",
        "::ffff:100.64.0.1",
    ],
)
def test_resolve_public_smtp_target_blocks_non_public_ips(host):
    with pytest.raises(BlockedSmtpTarget):
        resolve_public_smtp_target(host, 587)


@pytest.mark.parametrize("port", [25, 465, 587, 2525])
def test_resolve_public_smtp_target_permits_allowed_ports(port, monkeypatch):
    def mock_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
    ip = resolve_public_smtp_target("smtp.example.com", port)
    assert ip == "93.184.216.34"


@pytest.mark.parametrize(
    "port", [21, 22, 23, 80, 443, 3306, 5432, 6379, 8000, 8080, 0, -1, 65536]
)
def test_resolve_public_smtp_target_blocks_disallowed_ports(port):
    with pytest.raises(BlockedSmtpTarget, match="not a permitted SMTP port"):
        resolve_public_smtp_target("smtp.example.com", port)


def test_resolve_public_smtp_target_blocks_dns_failure(monkeypatch):
    def mock_getaddrinfo(*args, **kwargs):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
    with pytest.raises(BlockedSmtpTarget, match="Could not resolve"):
        resolve_public_smtp_target("nonexistent.invalid.domain", 587)


def test_resolve_public_smtp_target_blocks_mixed_dns_records(monkeypatch):
    """If DNS returns both a public IP and an internal/private IP, it must be rejected."""
    def mock_getaddrinfo(*args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 587)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 587)),
        ]

    monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
    with pytest.raises(BlockedSmtpTarget, match="resolves to a non-public address"):
        resolve_public_smtp_target("mixed.attacker.com", 587)


def test_resolve_public_smtp_target_allows_valid_public_ipv4(monkeypatch):
    def mock_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 587))]

    monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
    ip = resolve_public_smtp_target("smtp.google.com", 587)
    assert ip == "8.8.8.8"


def test_resolve_public_smtp_target_allows_valid_public_ipv6(monkeypatch):
    def mock_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2607:f8b0:4005:805::200e", 587))]

    monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
    ip = resolve_public_smtp_target("smtp.google.com", 587)
    assert ip == "2607:f8b0:4005:805::200e"


def test_is_ip_blocked_helper():
    assert is_ip_blocked(ipaddress.ip_address("127.0.0.1")) is True
    assert is_ip_blocked(ipaddress.ip_address("10.0.0.1")) is True
    assert is_ip_blocked(ipaddress.ip_address("100.64.0.1")) is True
    assert is_ip_blocked(ipaddress.ip_address("169.254.169.254")) is True
    assert is_ip_blocked(ipaddress.ip_address("::1")) is True
    assert is_ip_blocked(ipaddress.ip_address("::ffff:127.0.0.1")) is True
    assert is_ip_blocked(ipaddress.ip_address("8.8.8.8")) is False
    assert is_ip_blocked(ipaddress.ip_address("1.1.1.1")) is False
