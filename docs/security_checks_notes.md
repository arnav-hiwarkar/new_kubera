# Security Checks and Best Practices

This document outlines core security principles for the Kubera application, historical security fixes, and standard reference material for developers to ensure applications remain secure.

## KUB-001: Server-Side Module Access Control
**Class:** Broken access control (OWASP A01)
**Severity:** Critical

### The Vulnerability
Historically, module access control (e.g., hiding DocVault or AuditEase from unauthorized employees) was only enforced in the browser UI via `ModuleGuard.tsx`. The API endpoints themselves lacked backend enforcement. An authenticated user could bypass the frontend and directly request data from modules they were explicitly restricted from viewing.

### The Fix
Backend routing gates were added to all affected modules (`docvault`, `auditease`, `sales`, `kra`, `notifications`, `activity`). Every endpoint within these routers now requires the user to pass a `require_module("<module_id>")` dependency check. 

### The Lesson: Defense in Depth
UI-level security is a user experience (UX) feature, not a security boundary. All access control must be strictly enforced at the API/server level.

### Operational Consequence
The gate is a real behaviour change for anyone whose `accessible_modules` did not
previously reflect what they actually used. Two things to watch when provisioning:

- **`notifications` is cross-cutting.** Notifications are generated *by* other
  modules (DocVault approvals, AuditEase queries) but read through
  `/api/v1/notifications`. A user granted `docvault` but not `notifications` will
  silently never see approval notifications about their own documents. Grant
  `notifications` alongside any module that produces them.
- **Admins bypass every gate** (`require_module` returns early for
  `UserRole.admin`), so an admin can never lock themselves out of their tenant.

Before rolling this out to an existing tenant, list the users who would newly lose
access:

```sql
SELECT company_id, email, role, accessible_modules
FROM company_users
WHERE deleted_at IS NULL AND is_active AND role <> 'admin';
```

---

## The Principle of Least Privilege
**Least Privilege** dictates that a user, program, or process should have only the bare minimum privileges necessary to perform its function. 

When building or modifying applications in Kubera, you must verify that:
1. **API Endpoints are Gated:** Never rely solely on the frontend to hide functionality. If a user shouldn't see data, the backend must actively block the request (returning a `403 Forbidden`).
2. **Horizontal Access Control:** Users should only see records they own or are explicitly granted access to (e.g., scoping database queries using `company_id` and `user_id`).
3. **Vertical Access Control:** Standard users must never be able to access administrative endpoints or perform administrative actions.
4. **Validation:** Input validation must occur on the backend. Do not trust client-side validation alone.

---

## OWASP Top 10 (2021)
The Open Worldwide Application Security Project (OWASP) Top 10 is a standard awareness document for developers representing a broad consensus about the most critical security risks to web applications.

1. **A01:2021 - Broken Access Control:** (Addressed in KUB-001). Failures in enforcing policy such that users can act outside of their intended permissions.
2. **A02:2021 - Cryptographic Failures:** Failures related to cryptography, which often lead to sensitive data exposure.
3. **A03:2021 - Injection:** Cross-site Scripting, SQL injection, and OS injection where untrusted data is sent to an interpreter as part of a command or query.
4. **A04:2021 - Insecure Design:** Risks related to design and architectural flaws, highlighting the need for threat modeling and secure design principles.
5. **A05:2021 - Security Misconfiguration:** Missing appropriate security hardening across the application stack.
6. **A06:2021 - Vulnerable and Outdated Components:** Using components with known vulnerabilities.
7. **A07:2021 - Identification and Authentication Failures:** Incorrect execution of functions related to user identity, authentication, and session management.
8. **A08:2021 - Software and Data Integrity Failures:** Code and infrastructure that does not protect against integrity violations (e.g., unverified CI/CD pipelines or deserialization flaws).
9. **A09:2021 - Security Logging and Monitoring Failures:** Without logging and monitoring, breaches cannot be detected.
10. **A10:2021 - Server-Side Request Forgery (SSRF):** Occurs when a web application is fetching a remote resource without validating the user-supplied URL.

---

## KUB-003: Insufficient Anti-Automation & Rate Limiting
**Class:** Insufficient anti-automation (OWASP A07)
**Severity:** High

### The Vulnerability
`enforce_rate_limit` had three call sites in the whole application. `/auth/auditor/login`
had none of them: unauthenticated, unlimited, no lockout, no backoff, against accounts
that hold audit data for several client companies. `/auth/auditor/register` and both
refresh endpoints were equally open.

The limiter that did exist was also keyed on `(ip, email)` only. That stops someone
guessing one account's password; it does nothing about *spraying* — one password tried
against a list of addresses — because rotating the email hands the attacker a fresh
bucket every request. And there was no edge limit at all: `limit_req` was absent from
the gateway, and Caddy's rate-limit module is not compiled into `caddy:2-alpine`.

### The Fix
1. **A second, coarser counter.** `enforce_rate_limit` now takes `ip_limit`/`ip_window`
   and keeps a per-IP count independent of the identifier. Both counters always
   increment, including on requests that are already being rejected — otherwise parking
   on one email would be a way to burn that account's budget while keeping the coarse
   counter at zero.
2. **Every unauthenticated auth endpoint throttled.** Login and activate carry both
   counters; auditor registration is capped hard (`REGISTER_RATE_LIMIT`, 5/hour/IP)
   because it is both an account-spam vector and the enumeration oracle in KUB-002;
   refresh is per-IP only, since its identifier is a signed token rather than something
   guessable. The numbers live in `app/config.py`, not inline in the router.
3. **Fail-open, but loudly.** Redis runs `noeviction` at 200mb, so filling it is a
   realistic way to switch the limiter off. It still fails open — throttling must never
   take down auth — but at `ERROR` **with `exc_info`**, and every Redis call sits inside
   the `try` so a store that dies mid-check cannot turn into a 500 from a login endpoint.
4. **An edge backstop that survives a Redis outage** (`gateway/limits.conf`): `api_auth`
   at 1r/s for the four credential URIs, `api_general` as a per-tenant sanity ceiling,
   and `limit_conn` against the memory pressure of concurrent uploads and report renders.
5. **A user-visible wait.** 429s carry a standard `Retry-After` derived from the bucket's
   TTL; `frontend/src/api/rateLimit.ts` turns it into "Please try again in N minutes".
   Nothing else about the limiter is exposed — not the count, not which of the two limits
   was hit — so the notice cannot be used to probe whether an account exists.

### The Lesson: what you key a limit on *is* the limit
Every serious defect in this fix, first and second attempt, was a key that was either
too narrow or too broad. Both directions are dangerous, and they fail in opposite ways.

- **Too narrow is a bypass.** `(ip, email)` reads like a rate limit and stops nothing an
  attacker with a wordlist does. Any limit whose key contains attacker-controlled input
  needs a companion limit that does not.
- **Too broad is a denial-of-service switch you installed yourself.** The first attempt
  keyed the gateway zones on `$binary_remote_addr` with no `real_ip` configuration. But
  nothing reaches the gateway except Caddy, so that variable is Caddy's address on the
  `edge` network — *the same value for every visitor on the internet*. The whole user base
  shared one 1r/s bucket, and ten requests from one client locked everyone out. The
  gateway had been rebuilt and the config was valid; nginx cannot tell you that a key is
  constant. **Verify a limit by reading back what it actually keyed on** — nginx logs it:
  `limiting requests ... client: 172.19.0.3` was Caddy, and after the fix the same line
  reads `client: 172.19.0.1`.
- **Namespace your keys.** `rl:{scope}:{ip}:{identifier}` and `rl:{scope}:ip:{ip}` overlap
  when `ip` is the literal string `ip`. The counters are now `...:id:...` and `...:ip:...`,
  so no identifier can be crafted to land in another client's bucket. Ambiguity between
  a trusted and an untrusted component of a key is a vulnerability even when today's
  callers happen to make it unreachable.

### Operational Consequence
**Deploying this touches `gateway/`, not just `app/`.** `docker compose up -d --build
api frontend worker beat` — the README's routine deploy sequence — does not rebuild the
gateway container, because gateway normally stays up throughout a deploy to keep serving
the maintenance page. This fix changes `gateway/limits.conf`, `gateway/modes/app.conf`,
and `gateway/Dockerfile`, so it needs `gateway` added to that line — see
[README §Zero-downtime maintenance mode](../README.md#zero-downtime-maintenance-mode).
Rebuilding just `api` ships the application-layer counters but silently leaves the old,
key-on-a-constant edge zone running.

**Per-IP means per-customer.** Kubera is sold to companies, and a whole office shares one
NAT address, so every "per-IP" number here is really per-tenant. A limit tuned for one
user reads a fifty-seat office's Monday morning as an attack — and because
`limit_req ... nodelay` *rejects* past burst rather than queueing, and a 429 on
`/auth/*/refresh` is a forced sign-out, the failure mode is "the customer is logged out",
not "the customer waits". That is why `api_general` is a loose ceiling and the security
work is done by `api_auth` (guessing) and `limit_conn` (memory). If a large tenant reports
spurious 429s, raise `api_general` first.

**The strict zone must not cover normal traffic.** `/auth/company/me` and `/auth/*/refresh`
are called on every app boot and route guard, and `/auth/companies` is driven in bulk by
`ops/kubera-import.sh`. All three live under `/api/v1/auth/`, so a location-prefix rule
sweeps them into the 1r/s bucket and logs users out. `gateway/limits.conf` selects the
strict zone with a `map` over the exact credential URIs instead, and
`unit_tests/test_deployment_hardening.py` asserts in both directions — that the four
credential endpoints are in it, and that the five normal-traffic endpoints are not.

**A limiter you cannot see is a limiter you do not have.** Fail-open plus a silent
`except` is indistinguishable from having no rate limiting. Alert on the ERROR from
`app.rate_limit`; if it is firing, the auth endpoints are unprotected and only the gateway
is holding.
