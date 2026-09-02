import ipaddress
import socket

ALLOWED_PORTS = frozenset({25, 465, 587, 2525})


class BlockedSmtpTarget(ValueError):
    """The requested SMTP endpoint is not a permitted egress destination."""


def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP address is not a globally-routable public address."""
    # Unwrap IPv4-mapped IPv6 address (e.g. ::ffff:127.0.0.1 -> 127.0.0.1)
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped

    return bool(
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def resolve_public_smtp_target(host: str, port: int) -> str:
    if port not in ALLOWED_PORTS:
        raise BlockedSmtpTarget(
            f"Port {port} is not a permitted SMTP port "
            f"({', '.join(str(p) for p in sorted(ALLOWED_PORTS))})."
        )
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedSmtpTarget(f"Could not resolve {host!r}.") from exc

    if not infos:
        raise BlockedSmtpTarget(f"Could not resolve {host!r}.")

    valid_ips = []
    for *_, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            raise BlockedSmtpTarget(f"Invalid IP address {sockaddr[0]!r}.") from exc

        if is_ip_blocked(ip):
            raise BlockedSmtpTarget(
                f"{host} resolves to a non-public address and cannot be used as a mail server."
            )
        valid_ips.append(str(ip))

    if not valid_ips:
        raise BlockedSmtpTarget(
            f"{host} resolves to a non-public address and cannot be used as a mail server."
        )

    return valid_ips[0]
