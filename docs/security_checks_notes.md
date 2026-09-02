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
