# SMTP SSRF Mitigation (KUB-006) Design

## Purpose
Fix a Server-Side Request Forgery (SSRF) vulnerability in the SMTP verification endpoint (`POST /api/v1/company/smtp/verify`) and related Celery background tasks, which allowed authenticated tenant admins to port-scan the internal network (e.g., Postgres, Redis) and access cloud instance metadata.

## Architecture & Approach

### 1. Egress Network Guard
A new module `app/services/email/net_guard.py` will enforce an IP allowlist policy:
- **Port Allowlist**: SMTP connections will only be permitted on common ports (25, 465, 587, 2525).
- **Public IP Enforcement**: The provided hostname will be resolved using `socket.getaddrinfo`. The resolved IPs will be strictly checked to ensure they are public.
- **Blocked Ranges**: Private, loopback, link-local, multicast, and unspecified addresses (e.g., `127.0.0.1`, `10.x.x.x`, `169.254.169.254`, `0.0.0.0`, `::1`) are explicitly blocked using Python's `ipaddress` module.

### 2. IP Pinning (DNS Rebinding Protection)
To completely close the Time-Of-Check to Time-Of-Use (TOCTOU) gap common in SSRF mitigations, we will implement IP pinning:
- Instead of passing the hostname to `smtplib`, the SMTP client will connect directly to the pre-validated public IP address returned by the network guard.
- To ensure TLS Certificate Validation (SNI) continues to work, we will manually inject the original hostname into `smtplib`'s internal state (`server._host = original_host`) right before the TLS handshake (`starttls()` or `SMTP_SSL` connection).

### 3. Masking Error Responses
To prevent banner grabbing and service discovery, error handling in the API endpoint (`app/routers/company_smtp.py`) will be updated:
- The endpoint will catch specific `EmailDeliveryError` exceptions and raise a generic HTTP 400 error (e.g., "Could not connect to that mail server. Check the host, port and credentials.") instead of echoing the raw network exception.
- The `response` key containing the target's server banner will be removed from the successful `verify_connection` return dict.

### 4. Input Schema Validation
The `CompanySmtpVerifyRequest` Pydantic model (`app/schemas/company_smtp.py`) will be tightened:
- Enforce `min_length=1` and `max_length=255` on `host`.
- Enforce `ge=1` and `le=65535` on `port`.

## Testing Strategy
The `tests/test_company_smtp_api.py` file will be expanded to include:
- **Internal Targets**: Ensure connection attempts to `127.0.0.1`, `localhost`, `postgres`, and `redis` fail with a generic 400 error.
- **Cloud Metadata**: Ensure connections to `169.254.169.254` are blocked.
- **Edge Case Encodings**: Test obfuscated IP formats like `0.0.0.0`, `0x7f.0.0.1` (hex), `0177.0.0.1` (octal), and `::1` (IPv6).
- **Schema Rejections**: Verify that attempting to use non-SMTP ports (like `6379`) is rejected early.
