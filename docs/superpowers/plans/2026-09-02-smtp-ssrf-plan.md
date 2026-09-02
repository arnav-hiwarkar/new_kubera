# SMTP SSRF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a network guard and IP pinning in the SMTP verification flow to prevent SSRF and DNS rebinding attacks.

**Architecture:** We will create a `net_guard` module to validate resolved IPs against public ranges, modify the `EmailService` to connect via the resolved IP while preserving the original hostname for SNI, and update the API schemas/router to constrain inputs and mask error messages.

**Tech Stack:** Python 3, FastAPI, Pydantic, pytest.

## Global Constraints

- Must block connection attempts to private, loopback, link-local, multicast, and unspecified addresses (e.g., `127.0.0.1`, `10.x.x.x`, `169.254.169.254`, `0.0.0.0`, `::1`).
- Must only allow SMTP ports: 25, 465, 587, 2525.
- Error messages returned to the caller must not leak service banners or raw socket errors.

---

### Task 1: Network Guard Module

**Files:**
- Create: `app/services/email/net_guard.py`
- Create: `tests/test_net_guard.py`

**Interfaces:**
- Produces: `resolve_public_smtp_target(host: str, port: int) -> str`
- Produces: `BlockedSmtpTarget(ValueError)` exception class

- [ ] **Step 1: Write the failing test**

```python
# tests/test_net_guard.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_net_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.email.net_guard'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/email/net_guard.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_net_guard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/email/net_guard.py tests/test_net_guard.py
git commit -m "feat(email): add network guard to block internal SMTP targets"
```

---

### Task 2: IP Pinning in SMTP Client

**Files:**
- Modify: `app/services/email/client.py`
- Modify: `tests/test_email_service.py`

**Interfaces:**
- Consumes: `resolve_public_smtp_target`, `BlockedSmtpTarget` from Task 1

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_email_service.py
from unittest.mock import patch, MagicMock
from app.services.email.client import EmailService
from app.services.email.schemas import EmailConfig, EmailDeliveryError
import pytest
from app.services.email.net_guard import BlockedSmtpTarget

def test_get_connection_uses_net_guard_and_pins_ip():
    config = EmailConfig(host="smtp.example.com", port=587, user="u", password="p", use_tls=True)
    service = EmailService(config=config)
    
    with patch("app.services.email.client.resolve_public_smtp_target") as mock_resolve:
        mock_resolve.return_value = "8.8.8.8"
        with patch("app.services.email.client.smtplib.SMTP") as mock_smtp_class:
            mock_smtp_instance = MagicMock()
            mock_smtp_class.return_value = mock_smtp_instance
            
            # Use a dummy context for TLS
            with patch("app.services.email.client.ssl.create_default_context"):
                # We expect _get_connection to succeed if mocked properly
                server = service._get_connection()
                
                # Check that resolve was called
                mock_resolve.assert_called_once_with("smtp.example.com", 587)
                
                # Check that we connected to the IP, not the hostname
                mock_smtp_instance.connect.assert_called_once_with("8.8.8.8", 587)
                
                # Check that SNI hostname was preserved
                assert mock_smtp_instance._host == "smtp.example.com"

def test_get_connection_blocks_internal():
    config = EmailConfig(host="127.0.0.1", port=587, user="u", password="p")
    service = EmailService(config=config)
    
    with patch("app.services.email.client.resolve_public_smtp_target") as mock_resolve:
        mock_resolve.side_effect = BlockedSmtpTarget("Blocked")
        with pytest.raises(EmailDeliveryError, match="Blocked"):
            service._get_connection()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_email_service.py::test_get_connection_uses_net_guard_and_pins_ip -v`
Expected: FAIL (Because `resolve_public_smtp_target` is not called, and `connect` is called with hostname)

- [ ] **Step 3: Write minimal implementation**

Edit `app/services/email/client.py` around line 46 (`def _get_connection(self):`):

```python
# app/services/email/client.py
# (Add imports at the top)
from app.services.email.net_guard import resolve_public_smtp_target, BlockedSmtpTarget

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_email_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/email/client.py tests/test_email_service.py
git commit -m "fix(email): apply network guard and IP pinning in SMTP client"
```

---

### Task 3: Schema Constraints and Error Masking

**Files:**
- Modify: `app/schemas/company_smtp.py`
- Modify: `app/routers/company_smtp.py`
- Modify: `app/services/email/client.py`
- Modify: `tests/test_company_smtp_api.py`

**Interfaces:**
- Router updates input schema constraints and masks exceptions.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_company_smtp_api.py
@pytest.mark.asyncio
async def test_smtp_verify_refuses_internal_targets_and_masks_error(client: AsyncClient):
    await create_test_company(client, name="Co Verify SSRF", email="admin@ssrf.com")
    token = await get_company_token(client, email="admin@ssrf.com")
    
    payload = {
        "host": "127.0.0.1",
        "port": 587,
        "user": "audit@conf.com",
        "password": "Password123!",
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    r = await client.post("/api/v1/company/smtp/verify", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert "Could not connect to that mail server" in r.json()["detail"]

@pytest.mark.asyncio
async def test_smtp_verify_refuses_invalid_port_schema(client: AsyncClient):
    await create_test_company(client, name="Co Verify Schema", email="admin@schema.com")
    token = await get_company_token(client, email="admin@schema.com")
    
    payload = {
        "host": "smtp.example.com",
        "port": 99999, # invalid port
        "user": "audit@conf.com",
        "password": "Password123!",
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    r = await client.post("/api/v1/company/smtp/verify", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422 # Pydantic validation error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_company_smtp_api.py::test_smtp_verify_refuses_internal_targets_and_masks_error -v`
Expected: FAIL (because schema currently accepts any port and error includes full exception string)

- [ ] **Step 3: Write minimal implementation**

Edit `app/schemas/company_smtp.py`:

```python
# app/schemas/company_smtp.py
class CompanySmtpVerifyRequest(BaseModel):
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    user: Optional[str] = None
    password: Optional[str] = None
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None
    from_email: Optional[EmailStr] = None
    from_name: Optional[str] = None
```

Edit `app/routers/company_smtp.py` exception handling in `verify_smtp_config` (around line 165):

```python
# app/routers/company_smtp.py
# (At the top, ensure logger is imported if not already)
import logging
logger = logging.getLogger(__name__)

# Replace the except block in verify_smtp_config:
    except EmailDeliveryError as e:
        logger.warning("SMTP verify failed for company %s: %s", user.company_id, e)
        raise HTTPException(
            status_code=400,
            detail="Could not connect to that mail server. Check the host, port and credentials.",
        )
```

Edit `app/services/email/client.py` in `verify_connection` (around line 199) to drop `"response"`:

```python
# app/services/email/client.py
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "status": "ok",
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user or "(anonymous)",
            "use_tls": self.config.use_tls,
            "use_ssl": self.config.use_ssl,
            "latency_ms": round(latency_ms, 2),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_company_smtp_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/company_smtp.py app/routers/company_smtp.py app/services/email/client.py tests/test_company_smtp_api.py
git commit -m "fix(api): mask SMTP error messages and enforce port schema"
```
