# Deployment & Container Hardening — Design

Date: 2026-09-01
Status: Approved, in implementation
Scope: Spec 1 of 2. Spec 2 (upload progress UI) is deferred to its own document.

## Context

A prior change closed the Postgres/Redis internet exposure (see
`docs/SECURITY_HARDENING.md`). This pass audits the remaining Docker, container
and deployment surface. Every finding below was verified against a live stack
(Docker 29.7.2, Caddy 2.11.4), not inferred from reading configuration.

## Corrected prior finding

An earlier report claimed the login rate limiter was bypassable by spoofing
`X-Forwarded-For`. **It is not.** Thirteen requests with rotating spoofed values
produced a single Redis key, `rl:login:192.168.65.1:...`, holding the true client
IP. Caddy 2.11.4 replaces `X-Forwarded-For` for untrusted peers rather than
appending. The residual issue is that this protection rests on an undocumented
framework default with no test guarding it.

## Verified findings

| # | Finding | Severity | Evidence |
|---|---------|----------|----------|
| 1 | Built image contains `.env.bak.*` (live SMTP password) and 3013 tenant vault files | Critical | Inspected `new_kubera-api:latest` layer directly |
| 2 | `ops/kubera-export.sh` exits 127, no output | High | `.env` sourced under `set -e`; `SMTP_FROM_NAME=Kubera Compliance` unquoted |
| 3 | Nightly DB backup never runs | High | `pg_dump` silently ignores `postgresql+asyncpg://` and falls back to a Unix socket |
| 4 | Uploads over 1 MiB rejected | High (functional) | 1048000 B → 403; 1200000 B → 413 through caddy→gateway→api |
| 5 | CORS echoes any origin with credentials | Medium | `Origin: https://evil.example` reflected with `allow-credentials: true` |
| 6 | No security headers; `server:` version advertised | Medium | Live header capture |
| 7 | api/worker/beat run as uid 0 | Medium | `id` in each container. nginx workers already drop to `nginx` |
| 8 | Rotating `POSTGRES_PASSWORD` yields an 80-line traceback restart loop | Medium | Reproduced |
| 9 | `alembic.ini` hardcodes `kubera:kubera_secret` | Low | Overridden by `env.py`, but live in a tracked file |
| 10 | `auth.py:56` uses `!=` where `leads.py` uses `compare_digest` | Low | Read |
| 11 | `node:18-alpine` EOL; `npm install` despite a lockfile | Low | Read |
| 12 | No container resource limits | Medium | Read |

## Decisions

- **Upload cap: none for now** (user decision). The 1 MiB nginx cap is removed so
  large uploads work for the first time. Accepted risk: `docvault.py` reads
  uploads fully into memory, so an authenticated user can OOM the api container.
  Container memory limits contain this to one restart rather than the host.
  A real strategy (streaming encryption, per-plan quotas) is deferred.
- **Server size: 4 GB.** Limits sized to ~3.3 GB total, leaving host headroom.
- **Backups in scope.**
- **No full CSP.** `3d-force-graph` and Tailwind make a strict policy likely to
  break the SPA. `frame-ancestors 'none'` only; a full CSP gets its own pass.

## Workstreams

### A. Image hygiene
Rewrite `.dockerignore` as a superset of `.gitignore`'s sensitive entries; drop
`frontend/` from the api build context. Add a unit test diffing the two ignore
files so they cannot drift again.

Operational consequence: the leaked layer is permanent. The server must rebuild
and prune old images, and the exposed `SMTP_PASSWORD` must be rotated.

### B. Backups
Replace `load_env()`'s `source` with a safe line parser — sourcing also means a
secret containing `$(...)` executes as code. Quote `.env.example` values.
Fix `nightly_backup`: strip the `+asyncpg` dialect, pass the password via
`PGPASSWORD` rather than argv (argv is world-readable in the container's process
list), honour `BACKUP_PATH`, emit `-Fc` to match the documented restore path,
prune beyond a retention window, and raise on failure instead of printing.

### C. Non-root containers
Create `kubera` (uid 10001). Pre-create and chown `/data/vault`,
`/data/backups`, `/var/lib/kubera-beat` in the image so fresh named volumes
inherit ownership from the image path — only pre-existing volumes need the
documented one-time chown. Set `USER kubera` and `PYTHONDONTWRITEBYTECODE=1`.
Add `no-new-privileges` everywhere and `cap_drop: ALL` wherever it survives
testing.

### D. Edge hardening
HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`,
and removal of the `Server` header, applied at Caddy so every route is covered.
`client_max_body_size 0` and `proxy_request_buffering off` so nginx streams
uploads rather than buffering them whole.

### E. CORS, XFF, constant-time compare
Restrict origins to `DOMAIN`/`LANDING_DOMAIN` with a `CORS_ALLOWED_ORIGINS`
override for dev. Make Caddy's XFF replacement explicit via
`header_up X-Forwarded-For {remote_host}` and pin it with a test.
Use `secrets.compare_digest` in `auth.py`.

### F. Resource limits (4 GB host)
postgres 1g · api 1g · worker 640m · beat 160m · redis 256m · caddy 96m ·
gateway 64m · frontend 64m. Redis gets `maxmemory` with `noeviction`: LRU
eviction on a Celery broker silently discards queued tasks.

### G. Smaller fixes
Remove the credential from `alembic.ini`; `node:18` → `node:22` with `npm ci`;
a readable one-line error on Postgres auth failure.

## Verification

Every workstream is verified against a live stack, not just unit tests:
rebuild images, run the containers, re-run the upload/CORS/header probes that
produced the evidence above, and confirm the existing suite still passes.

## Out of scope

Full CSP; streaming upload encryption; upload quotas; IPv6 firewall rules;
the pre-existing stale `migrate.py`.
