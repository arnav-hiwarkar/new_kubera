import ipaddress
import socket

ALLOWED_PORTS = frozenset({25, 465, 587, 2525})

class BlockedSmtpTarget(ValueError):
    """The requested SMTP endpoint is not a permitted egress destination."""

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

    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            continue
        return str(ip)
        
    raise BlockedSmtpTarget(
        f"{host} resolves to a non-public address and cannot be used as a mail server."
    )
