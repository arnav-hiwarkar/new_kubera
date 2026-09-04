# Kubera — Security Audit Update

**Date:** 2026-09-03
**Branch:** `main`
**Author:** Claude (Sonnet 5), commissioned review
**Supersedes status tracking in:** `docs/SECURITY_AUDIT_2026-09-01.md` (2026-09-01, 40 findings, KUB-001…KUB-019 + KUB-L01…KUB-L21)

---

## 0. What this document is

This is **not** a fresh audit from scratch. It is a line-by-line re-verification
of every finding in the 2026-09-01 audit against the code as it stands today,
plus three new findings surfaced during this session's own work. Every status
below was checked against the actual current file, not assumed from a commit
message or a changelog entry — where a commit message claimed a fix, the code
was read to confirm it, and two claims (KUB-002, KUB-014) turned out to be
**not** fully backed by the commit that referenced them.

The original document is still the canonical *description* of each
vulnerability (exploit chain, impact, proposed fix). This document tracks
**status only**, plus what's new. Read the two together.

### 0.1 Headline answer to "is the auditor sign-up/login thing fixed?"

**No — partially.** Two related issues were fixed (auditor login/registration
now rate-limited; auditor passwords now have a complexity floor), but the
actual account-takeover vulnerability — **anyone who knows or guesses an
invited auditor's email address can register first and steal their access,
locking the real auditor out** — is still open. See [KUB-002](#kub-002) below.
A `token` column was even added to the invite table in anticipation of fixing
this, but it is never read or compared anywhere — the fix was started and not
finished.

---

## 1. Scorecard

| Severity | Total | Fixed | Partial | Open |
|---|---|---|---|---|
| Critical | 2 | 0 | 1 | 1 |
| High | 6 | 4 | 1 | 1 |
| Medium | 11 | 1 | 1 | 9 |
| Low | 21 | 0 | 2 | 19 |
| **New findings (this session)** | 3 | 0 | 0 | 3 |
| **Total** | **43** | **5** | **5** | **33** |

Read that as: the team correctly triaged and closed the findings that were
easiest to fix and/or most visible in code review (rate limiting, password
rules, SMTP SSRF, the DocVault approval-bypass bug, the assets module-guard
gap). The findings that are still open skew toward the ones that require a
data-model change (session revocation, invite tokens) or touch many call
sites (filename/export sanitization, deployment hardening) — harder work,
correctly deferred but not yet done.

---

## 2. Fixed and verified

These were re-checked against current code, not taken on faith.

### KUB-003 — No rate limiting on `/auth/auditor/login` — **FIXED**
`app/routers/auth.py` now calls `enforce_rate_limit` at all 6 credential
endpoints: `activate_company_admin`, `company_login`, `company_refresh`,
`auditor_register`, `auditor_login`, `auditor_refresh`. `gateway/limits.conf`
adds an edge-level `api_auth` zone (1 r/s) mapped specifically to the four
credential URIs (refresh excluded by design, covered by the app-level limit
instead). `unit_tests/test_deployment_hardening.py::TestEdgeRateLimits`
asserts both the coverage and that normal-traffic endpoints (`/auth/*/me`,
bulk import) are *not* caught in the strict zone. 64/64 tests pass.

### KUB-004 — No password complexity floor on auditor/employee creation — **FIXED**
A shared `Password` Pydantic type (`app/services/user_security.py`) now backs
`AuditorRegister.password`, `UserCreate.password`, and
`account_admin.set_password`. `PASSWORD_MAX_LENGTH = 72`, matching bcrypt's
silent-truncation boundary rather than the misleading 128 the old schema
allowed.

### KUB-006 — SSRF via tenant-configurable SMTP verification — **FIXED**
`app/services/email/net_guard.py` (`resolve_public_smtp_target`) rejects
private/loopback/link-local/reserved/multicast resolved addresses and is
called from both the `/company/smtp/verify` endpoint *and* the shared
`EmailService._get_connection()` used by real sends — so the guard can't be
routed around by using the saved config instead of the verify form. The HTTP
error returned to the caller is now a generic
`"Could not connect to that mail server..."`; the real exception is
server-logged only.

### KUB-007 — DocVault self-approval / mass-assignment bypass — **FIXED**
`DocumentUpdate` no longer accepts `status`. A separate `POST
/documents/{id}/review` endpoint requires `pending_approval` state, restricts
to the assigned approver or an admin, and explicitly blocks
`current_user.id == doc.created_by` — the uploader cannot review their own
document. Ordinary metadata edits now go through `_may_edit_document`
(creator, approver, or admin — independent of bucket access), and
re-enabling `is_editable` requires admin or the original creator.

### KUB-019 — `assets` module guard incomplete for depreciation/financial-years — **FIXED**
Both `app/routers/depreciation.py` and `app/routers/financial_years.py` now
declare `dependencies=[Depends(require_assets_module)]` at the router level.

### DocVault existing-document attach gating — **FIXED (new work, not in the original audit)**
Not a finding from the 2026-09-01 document — this closes a hole in the
*existing-document attach* flow across Assets and AuditEase that was found and
fixed in this session's own work (2026-09-01→03): attaching a document you
already had a bucket link to required no re-check of module/bucket access.
`assert_document_attachable` (`app/services/bucket_access.py`) now gates all
four attach points (asset documents, acquisition documents, AuditEase query
replies, AuditEase requirement responses): 403 without the `docvault` module,
403 without bucket access, 404 (not 403) across tenants, admin bypass, and
all-or-nothing validation on multi-document submissions. Covered by
`tests/test_document_attach_gating.py`. The one route that deliberately reads
past DocVault's own ACL (so an already-attached document stays downloadable
by anyone with legitimate engagement access) now writes a `document.downloaded`
audit log entry, which it did not before this session's review caught it missing.

---

## 3. Still open — Critical and High

<a name="kub-002"></a>
### KUB-002 — Auditor invitation account takeover — **OPEN — Critical**

This is the auditor sign-up issue. Unchanged from the original finding:
`POST /api/v1/auth/auditor/register` (`app/routers/auth.py:508-563`) still
matches `PendingAuditorInvite` rows purely by lower-cased email
(line 555) — **no secret, no token, nothing that proves the caller actually
received the invitation email.**

What changed since the original audit, and what didn't:

- A `token: Mapped[uuid.UUID]` column *was* added to `PendingAuditorInvite`
  (`app/models/auditease.py:201-209`) — but it is **never read or compared
  anywhere in the codebase**. It's a dead column; someone started this fix and
  the registration handler was never updated to require it.
- `Auditor.email` is still a plain `unique=True` string column with no
  case-insensitive index (unlike `company_users`, which does have one), so
  `a@x.com` and `A@x.com` can still both be registered.
- The dead `__pending__` takeover branch (`app/routers/auth.py:529-537`) is
  still present.
- `GrantStatus.invited` still confers full read/write access to the
  engagement before the auditor has authenticated even once
  (`app/services/document_access.py:143,162,188,210`).

**Practical exploit, unchanged from the original report:** an attacker who
learns or guesses an invited auditor's email — for a CA firm this is often a
published contact address — registers at `/auditor/register` first. They get
an `invited` grant with (by default) every engagement area enabled, and can
read the trial balance, all requirements and responses, all query messages,
and download every attached document, while the real auditor gets `409
Conflict` and is locked out with no recovery path.

**This is the single highest-priority item in this document.** The fix is
already scoped in the original audit (§KUB-002 there): mint the token,
require it at registration, verify it before converting any invite into a
grant, and stop trusting knowledge of an email address as proof of anything.

### KUB-005 — No session revocation mechanism — **OPEN — High**

Also unchanged. `app/auth.py` still mints tokens with no `jti`/`token_version`
— just `sub`, `exp`, `type`. Consequences, all still true:

- Changing your password does not invalidate your existing access/refresh
  tokens (`app/routers/users.py::change_password` rotates the hash and
  nothing else).
- `company_refresh`/`auditor_refresh` never recheck `is_active`/`deleted_at` —
  they only check the row exists.
- `Auditor` still has **no `is_active` column at all**. There is no way to
  disable an auditor account, full stop — not even the blunt instrument
  available for company users.
- No logout endpoint exists anywhere in the API.

Combined with KUB-002, this matters more than it would in isolation: if an
attacker does hijack an auditor invite, there is no way to kick them out
short of deleting the auditor row (which the current admin UI/API may not
even expose) — changing nothing about their session, because nothing checks
it.

### KUB-020 — `dispose_asset` has no authorization check at all — **OPEN — High (new finding)**

Found during this session's review of module-gating coverage, not in the
original audit. `POST /api/v1/assets/{asset_id}/dispose`
(`app/routers/assets.py:849-928`) depends only on
`get_current_company_user` — no module check, no role check, nothing. Its
siblings `approve_asset` and `reject_asset` at least manually verify
`current_user.role != UserRole.admin`-adjacent logic; `dispose_asset` has
none of that. Any authenticated company user — including one with zero
`accessible_modules` — can dispose a capitalized asset. This is a strict
regression relative to every other module-gated write path in the app and
should be treated with the same urgency as the original KUB-001.

---

## 4. Still open or partial — Medium

| ID | Title | Status | What's left |
|---|---|---|---|
| [KUB-001](#kub-001-detail) | Module access enforced only in the browser | **PARTIAL** | Broad rollout done (docvault/auditease/sales/kra/notifications/activity/assets/roc/secretarial all gated). Two gaps remain: `dispose_asset` (now tracked separately as [KUB-020](#kub-020), High) and `GET /api/v1/custom-fields/{module}` (`app/routers/custom_fields.py:16-21`), which still has no module/role dependency at all — any authenticated user can read any other module's custom-field schema. |
| KUB-008 | Financial-year / depreciation controls inconsistently gated | **PARTIAL** | `close`/`reopen` (financial years) and `finalize`/`delete` (depreciation) are now `require_admin` + audit-logged, and depreciation execution now blocks against a closed financial year. But `POST /depreciation/runs` (create) is still open to any employee (`app/routers/depreciation.py:110-113`, plain `get_current_company_user`) — only creation, not the destructive transitions, remains ungated. |
| KUB-009 | `inline` disposition with client-supplied Content-Type (latent stored XSS) | **OPEN** | No CSP, no shared safe-response helper, no magic-byte validation on upload anywhere. `asset_documents.py` still serves photo-role documents `inline` with the raw client-supplied MIME type. |
| KUB-010 | `Content-Disposition` filename injection | **OPEN** | No sanitization at upload (`docvault.py:332` stores `file.filename` raw) and no RFC 6266 encoding on output. CRLF is still rejected by the framework (500, not header injection) but bare-quote filename spoofing is unchanged. |
| KUB-011 | Excel formula injection in every export | **OPEN** | No neutralization helper exists anywhere in `export_service.py` or `reporting/workbook.py`. A tenant string starting with `=`/`+`/`-`/`@` still becomes a live formula in every asset, sales, and AuditEase export. |
| KUB-012 | `INTERNAL_API_KEY` typed into and stored in the browser | **OPEN** | `OwnerLeadsPage.tsx` still stores the key in `sessionStorage`. No edge IP allowlist exists for `/api/v1/owner/` or `/api/v1/auth/companies`. Company hard-delete (`DELETE /auth/companies/{id}`) still relies on the same single key plus a `confirm_name` string that's readable from the same API — no independent second factor. |
| KUB-013 | Audit bucket silently downgrades `restricted` → `everyone` | **OPEN** | `ensure_audit_bucket` (`app/services/document_access.py:55-58`) still unconditionally force-resets an existing bucket's visibility to `everyone` on every new audit-engagement upload, reverting any admin restriction with no warning. |
| KUB-014 | Rate-limit key trusts client-supplied `X-Forwarded-For` | **OPEN** | `_client_ip` (`app/rate_limit.py:37-43`) still trusts the left-most XFF entry unconditionally with no trusted-proxy allowlist. `leads.py` still records the proxy's IP, not the real client's, on every lead row — this half of the finding was not touched despite the commit message for KUB-003 suggesting rate-limit work was done broadly. |
| KUB-015 | Backups unencrypted, unreplicated, colocated with the data | **OPEN** | `pg_dump` still writes plaintext; the subprocess environment still leaks `ROOT_MASTER_KEK` via `env={**os.environ, ...}`; no off-host replication, no restore verification. |
| KUB-016 | Migration/export bundle ships ciphertext and its root key together | **OPEN** | `ops/kubera-export.sh` still copies `.env` unencrypted into the export bundle (`chmod 600` only — no `age` encryption step). |
| KUB-017 | Non-transactional migrations + auto-migrate on container start | **OPEN** | `docker-compose.yml` still runs `alembic upgrade head && uvicorn ...` inline with no advisory lock; a specific migration (`cd98ce56a9c3`) is still non-idempotent past a `COMMIT`. |
| KUB-018 | `UserRole` enum drift (`manager` role) | **PARTIAL** | Data was backfilled (a migration reassigns any `manager` rows to `employee`), closing the immediate crash risk. No `CHECK` constraint was added, so the DB enum still technically permits `manager`, and dead code referencing it (`require_manager_or_admin`, `get_direct_report_ids`) is still imported in three routers. |

<a name="kub-001-detail"></a>

---

## 5. Low severity — status

Of the 21 Low findings, **19 are still fully open**, 2 are partially fixed.
None were prioritized in the work that closed the Critical/High items above —
this batch (deployment hygiene, pagination, minor DoS/500 edge cases,
container hardening) has not been touched since 2026-09-01.

Partially fixed:
- **KUB-L04** (spreadsheet decompression amplification) — the newer
  `load_raw_rows` import path now uses `openpyxl.load_workbook(read_only=True)`,
  which bounds memory better, but the older `parse_and_import` path was not
  updated and has no size cap either way.
- **KUB-L13** (activity log readable by every employee) — the router now has
  a `docvault`-style module gate (`require_module("activity")`), so this is
  no longer completely ungated, but there is still no per-user filtering or
  admin restriction: any employee with the `activity` module reads every
  colleague's full activity trail.

Everything else — malformed-JWT 500s (L01), untyped `entity_id` query params
(L02), the older import path's crash-on-bad-filename (L03), the missing
current-version null-check (L05), non-constant-time-safe header comparisons
that can raise on non-ASCII input (L06), lead IP misattribution (L07), docs
endpoints always enabled (L08), logo upload trusting declared MIME (L09), the
30-day password-cooldown with no incident-response override (L10), unbounded
list endpoints (L11), the "uncategorised documents visible to everyone" design
choice (L12), the Celery per-call engine creation (L14), container hardening
gaps — no logging caps, no `read_only`, no `pids_limit`, writable Caddyfile
mount (L15), no TLS requirement on the DB connection string (L16), no CSP
(L17), unnecessary `allow_credentials=True` (L18), archived documents never
actually deleted from disk (L19), `eval`-based JSON parsing in `ops/lib.sh`
(L20), and no Celery task time limits or backup-overlap lock (L21) — are all
unchanged from the original audit. Full detail and proposed fixes for each are
in `docs/SECURITY_AUDIT_2026-09-01.md` §9; this document does not repeat them
since nothing about them has changed.

---

## 6. New findings from this session

<a name="kub-020"></a>
Already covered above: **KUB-020** (`dispose_asset` — no auth check, High,
§3) and the addition to **KUB-001**'s tracking (`custom_fields` GET — no
module gate, §4).

### KUB-021 — Compliance/ROC/Secretarial document linking has no ownership check — **OPEN — Medium**

Found while reviewing the DocVault attach-gating fix for other instances of
the same pattern; explicitly out of scope for that fix, so it was flagged but
not touched. Creating a compliance/ROC/Secretarial record lets the caller
point it at *any* document ID in the company with no ownership or bucket
check at all — not even the "do you have the DocVault module" check that
existed even before this session's fixes elsewhere. Severity is Medium rather
than High because the actual file content stays protected: downloads for
these records still go through DocVault's own properly-gated generic route,
so the practical impact is data integrity (a record can point at, or be
linked to, a document the linking user has no business referencing) rather
than direct disclosure. Compliance users without DocVault access also
currently get a 403 trying to download their own linked document templates —
the same "download too restrictive" bug that was fixed for AuditEase in this
session's work, still present here.

### KUB-022 — Attached-document access is permanent once granted (informational, not a defect)

Not a bug — an explicit, verified design trade-off from this session's own
work, recorded here because it's a real widening of exposure worth your
conscious awareness rather than something to "fix." Once a document is
attached to an AuditEase query or requirement response, every user with
AuditEase access on that engagement can read it — permanently, even if the
bucket grant that let the *original attacher* reach the document is later
revoked, and even for company users who never had DocVault access at all.
This mirrors how the auditor side already worked before this session's
changes and was a deliberate choice ("gate the attach, not the read"), not an
oversight. Worth revisiting only if your access model wants attachments to be
re-checked continuously rather than treated as permanently vested once made.

---

## 7. Recommended priority order

Ranked by realistic exploitability × blast radius, not by original severity
label alone:

1. **KUB-002** — auditor invite takeover. Unauthenticated, no precondition
   beyond knowing/guessing an email address, full read/write on an
   engagement, and it locks out the legitimate auditor as a side effect. Fix
   scoped and ready in the original audit; a dead `token` column already
   exists waiting to be wired up.
2. **KUB-020** — `dispose_asset` with zero auth check. Trivial to exploit
   (any authenticated user, any company), directly destructive
   (asset disposal is not casually reversible).
3. **KUB-005** — session revocation. Makes every other credential-compromise
   scenario in this list (including #1) unrecoverable for up to 7 days even
   after you notice and react.
4. **KUB-012** — `INTERNAL_API_KEY` exposure path. Low likelihood but
   maximal blast radius (irreversible multi-tenant data destruction via one
   header value); the edge IP allowlist alone is a small, high-value fix.
5. **KUB-013** — audit bucket auto-reopening. Silently defeats an admin's
   explicit access decision on every single audit engagement, with no error
   to alert them it happened.
6. **KUB-011** — Excel formula injection. Wide blast radius (every export,
   every user who opens one) for a small, mechanical fix (one helper
   function, two call sites) already fully specified in the original audit.
7. Remaining Medium/Low items, roughly in the order listed in §4/§5 — none
   are urgent in isolation, but KUB-014's leads-IP half and KUB-018's dead
   code are cheap enough that there's no reason to leave them for the next
   pass.

---

## 8. Methodology note

Every status in §2–§6 was established by reading the current file at the
line the original finding cited (or its current equivalent after refactors),
not by trusting a commit message, a docstring, or `docs/security_checks_notes.md`
(which documents KUB-001 and KUB-003 as fixed — confirmed accurate for both,
but that document does not cover the other 38 findings and should not be read
as a complete status tracker). Two specific claims were checked and found
overstated relative to what the code does: `docs/security_checks_notes.md`'s
KUB-003 writeup implies the X-Forwarded-For trust boundary was hardened
alongside the rate-limit work — it was not (KUB-014 is unrelated code and is
still open); and the `PendingAuditorInvite.token` column's existence could
easily be mistaken for KUB-002 being fixed if you only grep for the word
"token" — it is not read anywhere. Where this document says FIXED, it means
the specific code path was read end-to-end and the vulnerable pattern is
gone; where it says PARTIAL, the remaining gap is stated explicitly rather
than left implicit.
