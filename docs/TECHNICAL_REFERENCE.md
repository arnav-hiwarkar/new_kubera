# Kubera — Complete Technical Reference

**Version:** 0.1.0 · **Scope:** the whole system — every service, module, data model, endpoint, background job, operator tool and deployment flow.

Kubera is a **multi-tenant corporate compliance platform** for Indian private limited companies. It bundles six product surfaces behind one API and one React app:

| Surface | What it does |
|---|---|
| **DocVault** | Encrypted document repository with buckets, versioning, approvals, and a 3D graph explorer |
| **AuditEase** | Trial-balance import, chart-of-accounts mapping, adjusting entries, auditor collaboration, statutory reports |
| **Fixed Asset Register** | Acquisitions → asset units → depreciation (Companies Act Schedule II *and* Income Tax Act s.32) → 10 statutory reports |
| **SecretarialEase / ROC Compliance** | Two parallel compliance domains with document types, meeting records and DocVault sync |
| **Sales & KRA** | Lightweight sales pipeline and employee appraisal tracking |
| **Admin / Owner portal** | Lead capture, company provisioning, operator scripts, maintenance mode |

---

## Table of Contents

1. [System architecture](#1-system-architecture)
2. [Technology inventory](#2-technology-inventory)
3. [Configuration](#3-configuration)
4. [Identity, authentication and authorization](#4-identity-authentication-and-authorization)
5. [Cryptography and the vault](#5-cryptography-and-the-vault)
6. [Data model — every table](#6-data-model--every-table)
7. [API reference — every endpoint](#7-api-reference--every-endpoint)
8. [Core flows, end to end](#8-core-flows-end-to-end)
9. [Domain engines](#9-domain-engines)
10. [Reporting subsystem](#10-reporting-subsystem)
11. [Email subsystem](#11-email-subsystem)
12. [Background jobs](#12-background-jobs)
13. [Frontend architecture](#13-frontend-architecture)
14. [Edge, gateway and maintenance mode](#14-edge-gateway-and-maintenance-mode)
15. [Operator tooling](#15-operator-tooling)
16. [Migrations](#16-migrations)
17. [Testing](#17-testing)

---

## 1. System architecture

### 1.1 Containers

`docker-compose.yml` defines eight services:

| Service | Image / build | Command | Host port (production) | Network |
|---|---|---|---|---|
| `postgres` | `postgres:16-alpine` | — | none | `data` |
| `redis` | `redis:7-alpine` | `redis-server --requirepass "$REDIS_PASSWORD"` | none | `data` |
| `api` | `./Dockerfile` | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000` | `127.0.0.1:8000` | `edge` + `data` |
| `worker` | `./Dockerfile` | `celery -A app.worker.celery_app worker` | — | `data` |
| `beat` | `./Dockerfile` | `celery -A app.worker.celery_app beat --schedule=/var/lib/kubera-beat/celerybeat-schedule` | — | `data` |
| `frontend` | `./frontend/Dockerfile` | Nginx serving the Vite build | — | `edge` |
| `gateway` | `./gateway/Dockerfile` | Nginx traffic switch | — | `edge` |
| `caddy` | `caddy:2-alpine` | Reverse proxy + automatic HTTPS | `80`, `443` | `edge` |

`caddy` is the only service bound to a wildcard address; it is the sole internet-facing
surface. The `edge`/`data` split means `caddy`, `gateway` and `frontend` cannot open a
socket to Postgres or Redis — only `api`, `worker` and `beat` can.

`docker-compose.override.yml` (gitignored, local only) adds `--reload`, a `.:/code`
bind-mount, and publishes Postgres on `127.0.0.1:5433` and Redis on `127.0.0.1:6379`.
It must never exist on a server. `unit_tests/test_compose_exposure.py` enforces the
production invariant. See `docs/SECURITY_HARDENING.md`.

**Named volumes:** `pgdata`, `vault_data` (`/data/vault`), `backup_data` (`/data/backups`), `caddy_data`, `caddy_config`, `maintenance_runtime`.

`postgres` and `redis` both carry healthchecks; `api`, `frontend` and `gateway` depend on them via `condition: service_healthy`. The API's healthcheck hits `/readyz`.

### 1.2 Request path

```
Internet
  │ :80 / :443  (Caddy terminates TLS, auto-provisions certs for $DOMAIN and $LANDING_DOMAIN)
  ▼
Caddy ── reverse_proxy ──▶ gateway:80
                             │
                             │ include /var/lib/kubera-maintenance/active.conf   (a symlink)
                             │
                   ┌─────────┴──────────┐
                   ▼                    ▼
             app.conf              maintenance.conf
                   │                    └─▶ static 503 page from /srv/maintenance
                   │
        ┌──────────┼───────────────┐
        ▼          ▼               ▼
  /api/v1/leads/  /api/*        everything else
   interest      → api:8000     → frontend:80 (Nginx SPA)
   (allowed from                        │
    both domains)                       └─ /api/ inside the frontend container
                                            also proxies to api:8000
```

The gateway is the **domain isolation** layer:

1. `POST /api/v1/leads/interest` is proxied from **either** domain — the marketing site needs it.
2. Any other `/api/` path returns **403** when `Host` matches `(www.)?kuberacompliance.com` — application APIs are reachable only from the app domain.
3. `/(app|login|auditor|internal)` on the marketing domain is **301**-redirected to `https://app.kuberacompliance.com$request_uri`.
4. Everything else is proxied to the frontend.

`keepalive_timeout 0` on the gateway means a mode switch takes effect on the very next request — Caddy can never hold an old worker (and therefore an old route) open across a reload.

### 1.3 Backend layering

```
app/main.py            FastAPI app, CORS, router registration
  └─ app/routers/*     HTTP boundary: auth deps, validation, HTTP errors, activity logging
       └─ app/services/*   business logic (mostly pure; DB-touching layers are explicit)
            └─ app/models/*  SQLAlchemy 2.0 declarative ORM
                 └─ app/database.py  async engine + session factory
```

`app/services/` splits into **pure** modules (no DB, no ORM — `asset_costing`, `depreciation`, `it_depreciation`, `trial_balance`, `calc_trace`, `mapping_import`, `tb_reimport`, `auditor_access`, `reporting/*`) and **query/orchestration** modules that own async DB access (`depreciation_query`, `trial_balance_query`, `asset_register`, `requirements`, `document_access`, `account_admin`). The pure/impure split is why the engine layers are unit-testable without a database (`unit_tests/`) while the wiring is integration-tested (`tests/`).

---

## 2. Technology inventory

### 2.1 Backend (`pyproject.toml`, Python ≥ 3.12, locked in `uv.lock`)

| Package | Version | Role |
|---|---|---|
| `fastapi` | 0.115.12 | HTTP framework, dependency injection, OpenAPI |
| `uvicorn[standard]` | 0.34.3 | ASGI server |
| `sqlalchemy[asyncio]` | 2.0.41 | ORM, `Mapped[]` declarative style |
| `asyncpg` | 0.31.0 | Async Postgres driver |
| `alembic` | 1.16.2 | Schema migrations |
| `pydantic` / `pydantic-settings` | 2.11.5 / 2.9.1 | Request/response schemas, typed settings |
| `python-jose[cryptography]` | 3.4.0 | JWT encode/decode (HS256) |
| `passlib[bcrypt]` + `bcrypt` | 1.7.4 | Password hashing (the app calls `bcrypt` directly in `app/auth.py`) |
| `python-multipart` | 0.0.20 | Multipart form parsing (uploads) |
| `email-validator` | 2.2.0 | `EmailStr` validation |
| `celery[redis]` | 5.5.3 | Background tasks + beat scheduler |
| `redis` | 5.2.1 | Rate limiting, Celery broker/backend |
| `cryptography` | 45.0.4 | AES-GCM envelope encryption |
| `httpx` / `anyio` | 0.28.1 / 4.9.0 | Async test client, async primitives |
| `aiofiles` | 23.2.1 | Async file writes into the vault |
| `openpyxl` | ≥3.1 | XLSX read (imports) and write (exports/reports) |
| `weasyprint` | ≥62 | HTML → PDF rendering for reports |
| `jinja2` | ≥3.1 | Email templates and PDF report templates |

Dev group: `pytest` 8.4.1, `pytest-asyncio` 1.0.0 (`asyncio_mode = auto`), `pytest-xdist`.

The Docker image is `python:3.12-slim` with `uv` copied in from `ghcr.io/astral-sh/uv:0.9.28`. System packages: `postgresql-client` (for `pg_dump`/`psql`), WeasyPrint's runtime libs (`libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz0b`, `libgdk-pixbuf-2.0-0`, `libffi8`, `shared-mime-info`) and fonts (`fonts-dejavu-core`, `fonts-noto-core` — the latter supplies ₹ U+20B9). The virtualenv lives at `/opt/venv`, **outside** `/code`, so the compose bind-mount for `--reload` cannot shadow it. `uv sync --frozen --no-dev` fails if `pyproject.toml` and `uv.lock` disagree.

### 2.2 Frontend (`frontend/package.json`)

| Package | Version | Role |
|---|---|---|
| `react` / `react-dom` | 18.3.1 | UI runtime |
| `react-router-dom` | 6.24 | Routing (`createBrowserRouter`) |
| `@tanstack/react-query` | 5.51 | Server state, caching, invalidation |
| `react-hook-form` | 7.52 | Forms |
| `zod` | 3.23 | Client-side schema validation |
| `tailwindcss` | 3.4 | Styling |
| `clsx` + `tailwind-merge` | — | `cn()` class composition |
| `framer-motion` | 12.42 | Page transitions, drawers |
| `lucide-react` | 1.24 | Icon set |
| `three` + `3d-force-graph` | 0.185 / 1.80 | DocVault 3D graph explorer |
| `vite` | 5.3 | Dev server + build |
| `vitest` + Testing Library + `jsdom` | 2.0 | Component/unit tests |
| `openapi-typescript` | 7.0 | `npm run gen:api` regenerates `src/api/schema.d.ts` from `/openapi.json` |

---

## 3. Configuration

Everything is one `.env` at the repo root, read by `pydantic-settings` into `app/config.Settings` (cached with `@lru_cache`).

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | *(required)* | `postgresql+asyncpg://…` |
| `REDIS_URL` | `redis://redis:6379/0` | Rate limits + Celery |
| `JWT_SECRET_KEY` | *(required)* | HS256 signing key |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | |
| `ROOT_MASTER_KEK` | *(required)* | 64 hex chars = 32-byte root key encryption key |
| `INTERNAL_API_KEY` | *(required)* | Root operator secret for `X-Internal-Api-Key` endpoints |
| `RATE_LIMIT_ENABLED` | `true` | Master switch |
| `LOGIN_RATE_LIMIT` / `LOGIN_RATE_WINDOW` | `10` / `300s` | |
| `ACTIVATE_RATE_LIMIT` / `ACTIVATE_RATE_WINDOW` | `10` / `900s` | |
| `VAULT_STORAGE_PATH` | `/data/vault` | Encrypted blob root |
| `BACKUP_PATH` | `/data/backups` | Nightly backup target |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | |
| `DOMAIN` | `localhost` | App domain; also builds absolute URLs in invite emails |
| `LANDING_DOMAIN` | `kuberacompliance.com` | Marketing domain (compose/Caddy only) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | `""` / `587` / `""` / `""` | Server-default SMTP |
| `SMTP_USE_TLS` / `SMTP_USE_SSL` | `true` / `false` | STARTTLS vs implicit TLS |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | `kubera@ethdc.in` / `Kubera Compliance` | |
| `SMTP_TIMEOUT` | `15` | Seconds |

`extra = "ignore"`, so unknown keys in `.env` are harmless.

**Host vs container URLs:** the `.env` values point at `localhost` (Postgres on `5433`) for running commands directly on your machine, against the ports the dev compose override publishes. `docker-compose.yml` **overrides** `DATABASE_URL`, `REDIS_URL` and the Celery URLs per-service to the compose service names (`postgres:5432`, `redis:6379`), so container networking is correct regardless of what `.env` says. On a server no host port exists for either, so the `localhost` values there are inert.

**Startup secret validation:** `Settings._reject_insecure_secrets` raises `InsecureConfigurationError` if `JWT_SECRET_KEY`, `ROOT_MASTER_KEK`, `INTERNAL_API_KEY`, the `DATABASE_URL` password or any of the three Redis URLs still holds a value from `.env.example`, or if a Redis URL carries no password at all. Every problem is collected and reported in one message. `KUBERA_ALLOW_INSECURE_DEFAULTS=1` bypasses the check and is set by the root `conftest.py` for the test suite only.

---

## 4. Identity, authentication and authorization

### 4.1 Three principals

| Principal | Table | Token `principal_type` | Reaches |
|---|---|---|---|
| **Company user** | `company_users` | `company_user` | everything except `/api/v1/auditor/*` |
| **Auditor** | `auditors` | `auditor` | only `/api/v1/auditor/*` |
| **Operator / owner** | *(none — a shared secret)* | — | `X-Internal-Api-Key` endpoints |

The two token identities are enforced separately at every layer:

* **Backend** — `get_current_company_user` and `get_current_auditor` (`app/auth.py`) each reject a token whose `principal_type` does not match, and whose `type` is not `access`.
* **Frontend** — `createTokenStorage(namespace)` gives each identity its own `localStorage` key (`kubera.company.tokens`, `kubera.auditor.tokens`). Each identity has its own `HttpClient` with its own `refreshPath`. The two route trees (`companyRoutes`, `auditorRoutes`) are siblings and never nest, so there is no shared layer through which one session could reach the other's.

### 4.2 Tokens

`app/auth.py`:

* `create_access_token(subject_id, principal_type)` → `{sub, principal_type, exp, type: "access"}`, HS256, 30 min.
* `create_refresh_token(...)` → same shape with `type: "refresh"`, 7 days.
* `decode_token` raises **401 "Invalid or expired token"** on any `JWTError`.

`get_current_company_user` additionally loads the row and rejects `is_active == False` with **401 "Account is inactive"** — so deactivating a user (or archiving their company, which deactivates every user) revokes access **immediately**, not at token expiry.

### 4.3 Passwords

* `hash_password` — `bcrypt.gensalt()` + `bcrypt.hashpw`.
* `verify_password` — `bcrypt.checkpw`, returning `False` (not raising) on a malformed hash.
* Complexity policy lives in `app/services/user_security.validate_password_complexity`.
* A **pending** account carries the literal sentinel `"__pending__"` as its hash, which can never verify — so a not-yet-activated admin cannot log in even with a correct-looking password.

### 4.4 Authorization primitives

| Dependency | Behaviour |
|---|---|
| `require_role(*roles)` | 403 unless `user.role` ∈ roles |
| `require_admin` | `require_role(UserRole.admin)` |
| `require_manager_or_admin` | currently identical to `require_admin` (the `manager` role was migrated away) |
| `require_module(module_id)` | 403 unless `module_id ∈ user.accessible_modules`; **admins always pass** |
| `require_assets_module` | `require_module("assets")` |

Roles are just `admin` and `employee` (`UserRole`).

**Module access** is a JSONB array on `company_users.accessible_modules`. The canonical IDs (mirrored in `frontend/src/auth/company/modules.ts`) are:

`dashboard`, `docvault`, `sales`, `assets`, `kra`, `auditease`, `roc`, `secretarial`, `notifications`, `activity`.

`app/access_modules.normalize_accessible_modules` de-duplicates while preserving order and expands the legacy combined `compliance` grant into both `roc` and `secretarial`. Persisted values are always canonical.

> `require_module` exists because `accessible_modules` was historically enforced only in the browser (`ModuleGuard.tsx`), which made it a UX affordance rather than a boundary. Endpoints that rely on it for authorization must use the server-side dependency.

### 4.5 Auditor per-area permissions

An `AuditorEngagementGrant` carries `area_permissions` (JSONB) over five areas (`AuditorAccessArea`): `trial_balance`, `entries`, `requirements`, `queries`, `documents`. `app/services/auditor_access.normalize_area_permissions` treats `None` as "every area enabled" (invite default); an explicit payload sets exactly what it names. `check_auditor_access` in `app/routers/auditor_engagements.py` is the single gate every auditor endpoint passes through.

### 4.6 Rate limiting

`app/rate_limit.enforce_rate_limit` — a fixed-window counter in Redis keyed `rl:{scope}:{ip}:{identifier}`. The IP honours `X-Forwarded-For` (first hop) because the app sits behind Caddy + the gateway. **It fails open**: if Redis is unreachable the limiter returns silently, because throttling must never take down auth. Over the limit → **429**.

Applied at: `POST /auth/company/login` (10 / 300 s), `POST /auth/company/activate` (10 / 900 s), `POST /leads/interest` (3 / 600 s, hardcoded).

### 4.7 CORS

`app/main.py` installs `CORSMiddleware` with `allow_origins=["*"]`, credentials, all methods, all headers. In production the gateway's `Host`-based 403 rule is the real cross-origin boundary.

---

## 5. Cryptography and the vault

Three-tier **envelope encryption**, all AES-256-GCM (`app/encryption.py`):

```
ROOT_MASTER_KEK  (env, 32 bytes hex)
   │ AES-GCM encrypts
   ▼
Company KEK      (company_keys.encrypted_kek + kek_nonce, one row per company)
   │ AES-GCM encrypts
   ▼
Document DEK     (document_versions.encrypted_dek + dek_nonce, one per version)
   │ AES-GCM encrypts
   ▼
File ciphertext  (on disk at {VAULT_STORAGE_PATH}/{company_id}/{uuid}.enc)
```

| Function | Purpose |
|---|---|
| `get_root_kek()` | hex-decode `ROOT_MASTER_KEK` |
| `generate_company_kek()` | new 32-byte KEK → `(raw, encrypted, nonce)` |
| `decrypt_company_kek(enc, nonce)` | unwrap under the root KEK |
| `generate_dek()` | new 32-byte DEK + 12-byte nonce |
| `encrypt_dek` / `decrypt_dek` | wrap/unwrap a DEK under a company KEK |
| `encrypt_file_data` / `decrypt_file_data` | file bytes ↔ ciphertext with the DEK |
| `encrypt_smtp_password` / `decrypt_smtp_password` | company SMTP secrets under the company KEK |

Every nonce is a fresh `os.urandom(12)`.

**On-disk layout.** `handle_file_upload` (`app/routers/docvault.py`) writes `file_nonce (12 bytes) || ciphertext` into a single `.enc` file, computes `sha256(plaintext)` as `checksum`, and records `storage_path`, `original_filename`, `mime_type`, `size_bytes`, the wrapped DEK, the uploader and the version number.

A company's blobs all live under `{VAULT_STORAGE_PATH}/{company_id}/`, which is what makes a purge a single `shutil.rmtree`.

---

## 6. Data model — every table

Base classes (`app/models/base.py`): `Base` (declarative), `TimestampMixin` (`created_at`, `updated_at` with `onupdate`), `TenantScopedMixin` (indexed `company_id` FK with `ON DELETE CASCADE`).

Every PK is a `uuid4` UUID. Money is `Numeric(15,2)`.

### 6.1 Tenancy and identity

**`companies`** — `name`; profile block (`legal_name`, `cin`, `pan`, `gstin`, `tan`, address lines, `city`, `state`, `pincode`, `contact_email`, `contact_phone`, `date_of_incorporation`, `website`, `industry`, `logo_path`, `profile_completed`); activation block (`activation_key_hash`, `activation_expires_at`, `activation_used_at`); `archived_at` (legacy marker — nothing sets it any more since delete became a hard purge, but pre-existing archived rows still block login and show as archived to the operator).

**`company_keys`** — one row per company (`UNIQUE company_id`): `encrypted_kek`, `kek_nonce`.

**`company_users`** — `company_id`, `email`, `hashed_password`, `role` (`admin` | `employee`), `manager_id` (self-FK, `SET NULL`), `full_name`, `designation`, `department`, `is_active`, `deleted_at`, `accessible_modules` (JSONB), `can_change_password`, `password_changed_at`, `avatar_path`, `avatar_updated_at`.

> Uniqueness is a **partial** unique index — `uq_company_users_email_active` on `lower(email) WHERE deleted_at IS NULL` — so a soft-deleted user's email is free for reuse while the row (and their name on historical records) survives. The index is declared in the model *and* migration `e1f2a3b4c5d6` so `create_all` in tests matches production.

**`auditors`** — `email` (globally `UNIQUE`), `hashed_password`, `name`. Auditors are **not** tenant-scoped; they reach companies through engagement grants.

**`leads`** — `email`, `company_name`, `phone`, `entities_count`, `notes`, `status` (`new` | `contacted` | `converted` | `archived`), `ip_address`, `user_agent`. Indexes: `lower(email)`, `created_at`.

### 6.2 Email

**`company_smtp_configs`** — one per company (`UNIQUE company_id`): `host`, `port`, `user`, `encrypted_password`, `password_nonce`, `use_tls`, `use_ssl`, `from_email`, `from_name`, `is_active`, `last_tested_at`.

**`email_logs`** — `company_id` (`SET NULL`), `sender_email`, `sender_name`, `recipient_email`, `subject`, `template_name`, `status` (`queued` | `sent` | `failed`), `message_id`, `error_message`, `duration_ms`, `source`, `created_at`.

### 6.3 DocVault

**`buckets`** — `company_id`, `name`, `created_by` (nullable, so system buckets created during an auditor's action have no company user to attribute), `visibility` (`everyone` | `restricted`).

**`bucket_access_grants`** — `(bucket_id, company_user_id)` unique. Populates `Bucket.access_user_ids`.

**`documents`** — `company_id`, `current_version_id` (FK to `document_versions`, `use_alter`, `SET NULL` so a purge does not depend on delete order), `bucket_id` (`SET NULL`), `status`, `title`, `doc_type_id`, `tags` (`text[]`), `is_editable`, `created_by` (nullable for auditor-uploaded attachments), `approver_id`, `approval_requested_at`, `approved_at`, `approval_notes`.

`DocumentStatus`: `uploaded`, `pending_approval`, `action_required`, `verified`, `submitted`, `overdue`, `archived`.

**`document_versions`** — `document_id` (`CASCADE`), `storage_path`, `original_filename`, `mime_type`, `size_bytes`, `checksum`, `encrypted_dek`, `dek_nonce`, `uploaded_by`, `uploaded_at`, `version_number`.

**`document_access_overrides`** — `document_id`, `principal_type` (`company_user` | `auditor`), `principal_id`, `permission_level` (default `read`). This is how an auditor is granted read on a specific company document.

### 6.4 AuditEase

**`ledger_groups`** — `company_id` (NULL = seeded global), `parent_id`, `name`, `has_children`, `level` (0 = seeded top group, 1–2 = company sub-groups), `nature` (`debit` | `credit`, set only on seeded level-0 rows; descendants inherit by walking to the root).

**`trial_balance_accounts`** — `company_id`, `engagement_id`, `ledger_code`, `ledger_name`, `mapped_group_id`.
*Source figures (verbatim, audit trail + cross-check only):* `opening_balance`, `debit`, `credit`, `closing_balance`.
*Canonical figures (the only ones the statements read):* `opening_net_debit`, `closing_net_debit` — signed net debit, debit positive, credit negative.
*Diagnostics:* `sign_unresolved` (canonical sign was taken as a bare magnitude), `source_row_consistent` (did `opening + debit − credit == closing`; NULL if the source did not supply every input).

**`audit_engagements`** — `company_id`, `period_label`, `status` (`draft` | `invited` | `active` | `closed`), `created_by`, `financial_year_id`, `tb_sign_convention` (`signed` | `magnitude` | `explicit` | `derived`; NULL = no TB yet or a legacy engagement pending confirmation).

**`auditor_engagement_grants`** — `(auditor_id, engagement_id)` unique; `status` (`invited` | `accepted` | `revoked`), `invited_at`, `accepted_at`, `area_permissions` (JSONB, server default = all five areas true).

**`pending_auditor_invites`** — `engagement_id`, `email`, `token`, `created_at`. Converted into a grant automatically when someone registers with that email.

**`audit_entries`** — `engagement_id`, `created_by` (auditor), `code`, `description`, `status` (`proposed` | `approved` | `rejected`), `rejection_comment`.

**`audit_entry_lines`** — `entry_id`, `ledger_id` (→ `trial_balance_accounts`, `CASCADE`), `side` (`debit` | `credit`), `amount`. The `ledger` relationship is `lazy="raise"` — every read path must `selectinload` it explicitly.

**`requirement_requests`** — `engagement_id`, `raised_by` (auditor), `seq_number`, `description`, `status` (`open` | `closed`), `priority`, `due_date`, `closed_by`, `closed_at`. Exposes `requirement_id` → `REQ-003`.

**`requirement_responses`** — one submission round; `(requirement_id, round_number)` unique; `responded_by`, `text_answer`, `created_at`. Append-only: round 2 never overwrites round 1.

**`requirement_response_documents`** — `(response_id, document_id)` unique; `document_id` is **`SET NULL`** and paired with a `filename` snapshot, so deleting the document later still leaves an honest record that six files were submitted.

**`queries`** — `engagement_id`, `opened_by` (auditor), `requirement_id` (optional link, `SET NULL`), `status` (`open` | `closed`).

**`query_messages`** — `query_id`, `sender_type` (`company_user` | `auditor`), `sender_id`, `text`, `attached_document_id`, `created_at`.

**`report_templates`** — `name`, `schema_content` (JSONB).

### 6.5 Fixed assets

**`asset_categories`** (`company_id` NULL = seeded Schedule II Part C tree) — `parent_id`, `name`, `code`, defaults inherited by assets (`default_useful_life_months`, `default_dep_method`, `default_residual_pct`, `default_it_block_id`, `default_itc_treatment`), `tag_prefix`, `applicable_field_groups` (JSONB), `schedule_ii_reference`, `is_active`, `display_order`.

`FIELD_GROUPS` = `registration`, `network_ids`, `insurance`, `amc`, `warranty`, `test_certificate`, `manual`.

**`it_asset_blocks`** (`company_id` NULL = seeded Appendix I) — `code`, `name`, `dep_rate`, `block_class` (`building` | `furniture` | `plant_machinery` | `intangible`), `is_active`, `display_order`. Unique index `(company_id, lower(code))` with `NULLS NOT DISTINCT`, so re-seeding collides instead of duplicating.

**`suppliers`** — `code`, `name`, `gstin`, `state_code` (first two GSTIN chars, denormalised because that is what the CGST/SGST-vs-IGST decision compares), `state`, `pan`, contact and address fields, `is_active`.

**`asset_lookups`** — a generic dimension table with a `kind` discriminator: `branch`, `cost_centre`, `department`, `location`. Fields: `name`, `code`, `parent_id`, `gstin`, `state_code`, `state`, `is_active`, `display_order`. (`condition` is deliberately *not* here — it is the closed ordinal `AssetCondition` enum, because reports sort on it.)

**`asset_acquisitions`** — one invoice line. Supplier (`supplier_id` + `supplier_name_snapshot`, `supplier_gstin_snapshot`), invoice/PO/purchase dates, `quantity`, `unit_basic_price`, `discount_type`/`discount_value`, `hsn_sac_code`, `gst_rate`, `branch_id`, `place_of_supply_state_code`, `cgst_amount`/`sgst_amount`/`igst_amount`, `gst_amounts_overridden`, `gst_split_basis`, `itc_treatment`, `itc_eligible_pct`, `freight_cost`, `installation_cost`, `other_capitalizable_cost`; derived: `gross_basic_price`, `discount_amount`, `net_basic_price`, `total_gst`, `recoverable_gst`, `capitalizable_gst`, `landed_cost`, `total_acquisition_outlay`, `per_unit_cost`; import block (`is_imported`, `bill_of_entry_number`/`_date`, `customs_duty`, `foreign_currency`, `foreign_currency_value`, `exchange_rate`); lease block (`is_leased`, `lease_type`, `lessor_name`, `lease_start_date`, `lease_end_date`, `lease_rental`); logistics (`grn_number`/`grn_date`, `delivery_challan_number`, `eway_bill_number`, `irn`).

**`assets`** — one physical unit. `acquisition_id`, `unit_index`, `asset_code`, `asset_name`, `category_id`, descriptive fields (`manufacturer`, `brand_model`, `manufacturer_serial_number`, …), `lifecycle_status`, `operational_status`, `condition`, dimensions (`branch_id`, `cost_centre_id`, `department_id`, `location_id`, `custodian_id`, `custodian_name`, `custodian_employee_code`), dates (`available_for_use_date`, `capitalization_date`, `warranty_start_date`, `warranty_months`, `warranty_expiry_date`), depreciation inputs (`useful_life_months`, `dep_method`, `residual_pct`, `residual_value`, `useful_life_override_reason`), tax inputs (`it_block_id`, `it_dep_rate`, `it_put_to_use_date`), cost (`original_cost`), pre-cutover opening balances (`is_pre_cutover`, `opening_accumulated_depreciation`, `opening_wdv`, `opening_it_wdv`), disposal block (`disposal_date`, `disposal_type`, `sale_proceeds`, `buyer_name`, `disposal_invoice_no`, `disposal_remarks`, `disposal_gain_loss`, `disposal_it_proceeds`, `disposed_by`), identifiers (`registration_number`, `engine_number`, `chassis_number`, `imei`, `mac_address`), `technical_specs`, `parent_asset_id`, `custom_fields` (JSONB), and workflow columns (`created_by`, `submitted_by`, `submitted_at`, `approved_by`, `approved_at`).

> **Almost every column is nullable on purpose.** "Mandatory" is enforced per *lifecycle transition* (`app/services/asset_validation.py`), not per INSERT, so a six-field draft can be saved and enriched later without fighting the database.

Enums: `AssetLifecycleStatus` (`draft`, `ready`, `capitalized`, `disposed`), `AssetDisposalType` (`sale`, `scrap`, `write_off`, `loss_destruction`, `insurance_claim`), `AssetOperationalStatus` (`in_use`, `idle`, `under_maintenance`, `in_storage`), `AssetCondition` (`new`, `good`, `fair`, `poor`, `unusable`), `DepreciationMethod` (`slm`, `wdv`), `ItcTreatment` (`eligible`, `blocked`, `partial`), `DiscountType` (`amount`, `percent`).

**`asset_documents`** — links an `assets` or `asset_acquisitions` row to a DocVault `documents` row with a `doc_role` (`AssetDocRole`: `invoice`, `purchase_order`, `grn`, `eway_bill`, `approval`, `asset_photo`, `serial_photo`, `warranty`, `insurance`, `amc`, `test_certificate`, `manual`, `customs`, `lease`, `other`), a `note` and `uploaded_by`. `ACQUISITION_DOC_ROLES` (invoice, PO, GRN, e-way, approval, customs, lease) attach at the acquisition level and are shared by every unit; the rest are per unit.

**`asset_code_sequences`** — `(company_id, prefix)` → `next_number`, locked `FOR UPDATE` when allocating.

### 6.6 Financial years and depreciation

**`financial_years`** — `label` (unique per company), `start_date`, `end_date`, `status` (`open` | `closed`), `closed_at`, `closed_by`.

**`depreciation_runs`** — `financial_year_id`, `book`, `run_date`, `status` (`draft` | `finalized`), `finalized_at`, `finalized_by`, `notes`. Partial unique index `uq_depreciation_runs_company_fy_finalized` on `(company_id, financial_year_id) WHERE status = 'finalized'` — **at most one finalized run per FY**.

**`asset_depreciation_lines`** (Companies Act) — `run_id`, `asset_id`, `method`, `opening_gross_block`, `additions`, `disposals`, `closing_gross_block`, `opening_accumulated_depreciation`, `depreciation_for_year`, `disposal_accumulated_depreciation`, `closing_accumulated_depreciation`, `opening_carrying_amount`, `closing_carrying_amount`, `residual_value`, `remaining_useful_life_days`, `effective_rate_pct`, `is_part_year`, `is_disposed`, `gain_loss_on_disposal`, `calc_trace` (JSONB, display only).

**`it_block_depreciation_lines`** (Income Tax) — `run_id`, `it_block_id`, `block_name`, `prescribed_rate`, `opening_wdv`, `additions_more_than_180`, `additions_less_than_180`, `realized_from_sales`, `balance_before_depreciation`, `depreciation_full_rate`, `depreciation_half_rate`, `total_depreciation`, `closing_wdv`, `capital_gain_or_loss`, `has_stcg`, `has_stcl`, `calc_trace`.

### 6.7 Compliance, and the rest

**`document_types`** — `company_id` (NULL = system-shipped), `domain` (`secretarial` | `roc`), `name`, `template_file_id` (`SET NULL`), `metadata_schema` (JSONB), `due_date_rule`.

**`meeting_records`** — `doc_type_id` (nullable; DocVault-imported records arrive unclassified), `domain` (denormalised — an untyped record still belongs to exactly one app), `title`, `document_id`, `structured_metadata`, `record_date`, and an archive snapshot (`archived_at`, `archived_document_status`, `archived_document_editable`) so unarchiving restores the linked document's status **and** lock state exactly.

**`custom_field_definitions`** — `module` (`asset_management` | `sales_tracking`), `field_name`, `field_key`, `field_type` (`text` | `number` | `date` | `dropdown`), `is_required`, `dropdown_options`, `display_order`, `is_active`.

**`sales_records`** — `client_name`, `product_service`, `amount`, `status` (`lead` | `negotiation` | `won` | `lost`), `closing_date`, plus custom fields.

**`kra_items`** — `title`, `description`, `weightage`, `target_metric`, `cycle`, `status` (`draft`, `pending_approval`, `approved`, `in_progress`, `review_submitted`, `completed`, `rejected`), `user_id`, `manager_id`, `employee_self_rating`/`employee_comment`, `manager_rating`/`manager_comment`, `rejection_reason`.

**`notifications`** — `recipient_type` (`company_user` | `auditor`), `recipient_id`, `type`, `payload` (JSONB), `read_at`, `created_at`.

**`activity_logs`** — append-only: `company_id`, `actor_type` (`company_user` | `auditor` | `internal`), `actor_id`, `action`, `entity_type`, `entity_id`, `engagement_id` (nullable, indexed), `metadata` (JSONB, mapped as `metadata_`), `created_at`.

---

## 7. API reference — every endpoint

Base: `/api/v1`. Interactive docs at `/docs` (Swagger) and `/redoc`. All authenticated routes take `Authorization: Bearer <access_token>`.

Legend — **Auth**: `—` public · `CU` company user · `CU:admin` admin only · `CU:mod(x)` module `x` required · `AUD` auditor · `KEY` `X-Internal-Api-Key` header.

### 7.1 Health — `app/routers/health.py`

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/healthz` | — | `{"status":"ok"}`. Liveness. Excluded from the schema. |
| GET | `/readyz` | — | Pings Postgres (`SELECT 1`) and Redis. `200 {"status":"ready", checks:{…}}` or `503 {"status":"not_ready", …}`. |

### 7.2 Leads and owner portal — `app/routers/leads.py`

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/leads/interest` | — | Public capture. Honeypot field `website_url_hp` → silent success, no DB write. Rate limit 3 / 10 min per IP+email. Always returns the same generic response (anti-enumeration). Records `ip_address` and `user-agent`. |
| GET | `/owner/leads` | KEY | Optional `?status=`. Newest first. |
| PATCH | `/owner/leads/{lead_id}/status` | KEY | Body `{status}`. |
| POST | `/owner/leads/{lead_id}/provision` | KEY | One-shot conversion: creates the `Company`, mints an activation key, seeds asset masters, generates the company KEK, creates the pending admin (`__pending__` password, `is_active=False`), marks the lead `converted`. Returns the plaintext activation key. 409 if the email is already on a live account. |

`_require_internal_key` here uses `secrets.compare_digest` (constant time).

### 7.3 Auth — `app/routers/auth.py`

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/companies` | KEY | Initialize a company + pending admin. Creates `Company`, mints a 48 h one-shot activation key (`secrets.token_urlsafe(24)`, stored bcrypt-hashed), seeds global asset reference data, generates the company KEK, creates the pending admin. Returns the plaintext key **once**. 409 on a duplicate live email (checked, and re-caught from `IntegrityError` to cover the TOCTOU race). |
| POST | `/auth/companies/{company_id}/reissue-key` | KEY | Fresh key + 48 h window. 409 if the admin already activated. Touches no tenant data. |
| POST | `/auth/company/activate` | — | `{email, activation_key, password, full_name}` → sets the real password, flips `is_active`, one-shots the key. Rate limited. **Every** failure mode returns the identical `400 "Invalid or expired activation details"`. No session is issued — the admin logs in normally afterwards. |
| GET | `/auth/companies` | KEY | Every company with `admin_email`, `admin_active`, `profile_completed`, `activation_pending`, `activation_expires_at`, `archived`. |
| DELETE | `/auth/companies/{company_id}` | KEY | **Hard purge.** Requires `confirm_name` to equal the company name. Deletes the row (cascade takes every tenant-owned row), then `rmtree`s the company's vault directory — only after the transaction commits. |
| POST | `/auth/company/login` | — | Case-insensitive, live-rows-only lookup. Rejects unknown user / wrong password / inactive / pending / archived company, all with the same `401 "Invalid credentials"`. Returns `{access_token, refresh_token, role, full_name}`. Rate limited. |
| POST | `/auth/company/refresh` | — | `{refresh_token}` → new pair. Rejects a token whose `principal_type`/`type` is wrong. |
| GET | `/auth/company/me` | CU | Current profile. |
| POST | `/auth/auditor/register` | — | Open self-registration. If a `__pending__` placeholder auditor exists for the email (created by an invite), it is claimed rather than rejected. On success, every `PendingAuditorInvite` for that email is converted into an `AuditorEngagementGrant` and deleted. |
| POST | `/auth/auditor/login` | — | Returns `{access_token, refresh_token}`. |
| POST | `/auth/auditor/refresh` | — | |
| GET | `/auth/auditor/me` | AUD | |

### 7.4 Company profile — `app/routers/company.py`

| Method | Path | Auth |
|---|---|---|
| GET | `/company/profile` | CU |
| PUT | `/company/profile` | CU:admin |
| POST | `/company/profile/logo` | CU:admin |
| GET | `/company/profile/logo` | CU |

Logo upload validates image magic bytes via `user_security.detect_image_format`. Completing the profile sets `profile_completed`, which is what the frontend's `ProfileGate` unblocks.

### 7.5 Company SMTP — `app/routers/company_smtp.py`

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/company/smtp` | CU:admin | Config **without** the password. |
| PUT | `/company/smtp` | CU:admin | Upsert. Password is AES-GCM encrypted under the company KEK before storage. |
| POST | `/company/smtp/verify` | CU:admin | Opens a real SMTP connection, STARTTLS/SSL, `LOGIN`, `NOOP`; returns host/port/user/latency. Updates `last_tested_at`. Sends nothing. |
| DELETE | `/company/smtp` | CU:admin | Removes the config; the company falls back to server-default SMTP. |
| GET | `/company/smtp/logs` | CU:admin | `email_logs` for this company. |

### 7.6 Users — `app/routers/users.py`

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/users` | CU:admin | Create a user; `accessible_modules` normalized. |
| GET | `/users` | CU:admin | Live users of this company. |
| GET | `/users/me` | CU | |
| GET | `/users/me/reports` | CU:admin | Direct reports (`manager_id`). |
| POST | `/users/me/change-password` | CU | Requires the current password, enforces the complexity policy, blocked when `can_change_password` is false. Sets `password_changed_at`. |
| POST | `/users/me/avatar` | CU | Magic-byte validated image; stored and `avatar_updated_at` bumped. |
| GET | `/users/me/avatar` | CU | Streams the image. |
| GET | `/users/{user_id}` | CU:admin | |
| GET | `/users/{user_id}/avatar` | CU | |
| PATCH | `/users/{user_id}` | CU:admin | Role, modules, manager, designation, department, `can_change_password`. |
| DELETE | `/users/{user_id}` | CU:admin | **Soft delete** — sets `deleted_at`, disables login, frees the email. The row and `full_name` survive so historical work still shows who created it. Guards the last active admin. |
| PATCH | `/users/{user_id}/deactivate` | CU:admin | `is_active = False`, email retained. |
| PATCH | `/users/{user_id}/reactivate` | CU:admin | |

### 7.7 Custom fields — `app/routers/custom_fields.py`

`{module}` ∈ `asset_management`, `sales_tracking`.

| Method | Path | Auth |
|---|---|---|
| GET | `/custom-fields/{module}` | CU |
| POST | `/custom-fields/{module}` | CU:admin |
| PATCH | `/custom-fields/{module}/{field_id}` | CU:admin |
| PATCH | `/custom-fields/{module}/{field_id}/deactivate` | CU:admin |
| PATCH | `/custom-fields/{module}/{field_id}/reactivate` | CU:admin |

Values submitted on assets and sales records are validated against the live definitions by `services/custom_field_validator.validate_custom_fields`.

### 7.8 Financial years — `app/routers/financial_years.py`

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/financial-years` | CU | |
| POST | `/financial-years` | CU | Label unique per company; date range validated. |
| POST | `/financial-years/{fy_id}/close` | CU | |
| POST | `/financial-years/{fy_id}/reopen` | CU | |

### 7.9 Depreciation — `app/routers/depreciation.py`

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/depreciation/runs` | CU | Runs newest first with line summaries. |
| POST | `/depreciation/runs` | CU | Executes **both** books for a financial year. 404 FY not found · 409 sequencing/status conflict · 422 statutory data error. |
| POST | `/depreciation/explain` | CU | Re-derives a labelled `CalcTrace` for one asset or one IT block without persisting anything. |
| GET | `/depreciation/runs/{run_id}` | CU | |
| GET | `/depreciation/runs/{run_id}/lines` | CU | Companies Act asset lines. |
| GET | `/depreciation/runs/{run_id}/it-lines` | CU | Income Tax block lines. |
| POST | `/depreciation/runs/{run_id}/finalize` | CU | Locks the run for statutory reporting. |
| POST | `/depreciation/runs/{run_id}/reopen` | CU:admin | Requires a `reason`; logged as `depreciation.run.reopened`. 409 if a later year blocks it. |
| DELETE | `/depreciation/runs/{run_id}` | CU | 409 on a finalized run. |

### 7.10 Asset masters — `app/routers/asset_masters.py`

Reads need `CU:mod(assets)`; writes need `CU:admin`.

| Method | Path | Notes |
|---|---|---|
| GET | `/asset-masters/it-blocks` | Seeded globals + company rows. |
| POST | `/asset-masters/it-blocks` | |
| PATCH | `/asset-masters/it-blocks/{block_id}` | |
| GET | `/asset-masters/categories` | `?include_inactive=` |
| POST | `/asset-masters/categories` | |
| PATCH | `/asset-masters/categories/{category_id}` | |
| GET | `/asset-masters/suppliers` | `?include_inactive=` |
| POST | `/asset-masters/suppliers` | |
| PATCH | `/asset-masters/suppliers/{supplier_id}` | |
| GET | `/asset-masters/lookups` | `?kind=` |
| POST | `/asset-masters/lookups` | |
| PATCH | `/asset-masters/lookups/{lookup_id}` | |
| GET | `/asset-masters/{kind}/{row_id}/impact-preview` | "What does editing this row affect?" — `none` or `future_only`, plus which finalized FYs would need reopening. |

### 7.11 Assets — `app/routers/assets.py`

All require `CU:mod(assets)`; `DELETE` additionally requires admin.

| Method | Path | Notes |
|---|---|---|
| POST | `/assets/quick-add` | Minimal create (name + category) → draft. |
| POST | `/assets/existing` | Pre-existing asset with opening balances instead of an invoice. |
| GET | `/assets/import/template` | XLSX template for the bulk import. |
| POST | `/assets/import` | Bulk import of existing assets. **All-or-nothing** — one bad row aborts the file with a per-row error report. |
| POST | `/assets/cost-preview` | Runs the costing engine on unsaved input and returns the full breakdown + trace. |
| GET | `/assets/export/excel` | Register export. |
| GET | `/assets` | Filtered list. |
| GET | `/assets/{asset_id}` | Detail incl. acquisition, category, documents. |
| PATCH | `/assets/{asset_id}` | |
| POST | `/assets/{asset_id}/serials` | Bulk-assign serial numbers across sibling units. |
| POST | `/assets/{asset_id}/submit` | `draft → ready`. Returns the **full checklist** of issues (422) rather than the first error. `apply_to_siblings` optional. |
| POST | `/assets/{asset_id}/approve` | `ready → capitalized`. **Admin only** — an unreviewed capitalized cost enters the depreciation base. |
| POST | `/assets/{asset_id}/reject` | `ready → draft` with a note. |
| POST | `/assets/{asset_id}/dispose` | Only from `capitalized`. Validates the disposal date against the company's FYs and whether that FY already has a finalized run. |
| DELETE | `/assets/{asset_id}` | Drafts only. A capitalized asset leaves the register through **disposal**, which is an accounting event, not a delete. |

### 7.12 Asset acquisitions — `app/routers/asset_acquisitions.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/asset-acquisitions` | `?supplier_id=` |
| GET | `/asset-acquisitions/{acq_id}` | |
| GET | `/asset-acquisitions/{acq_id}/units` | The asset rows this acquisition parented. |
| PATCH | `/asset-acquisitions/{acq_id}` | Re-runs costing and re-allocates per-unit cost; can resize the unit count. |
| POST | `/asset-acquisitions/{acq_id}/explode` | Turn one invoice line for *N* identical items into *N* individually tagged draft asset rows. |

### 7.13 Asset documents — `app/routers/asset_documents.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/assets/{asset_id}/documents` | |
| POST | `/assets/{asset_id}/documents` | Attach an existing DocVault document with a `doc_role`. |
| POST | `/assets/{asset_id}/documents/upload` | Upload a file → encrypted DocVault document → attach. |
| POST | `/asset-acquisitions/{acq_id}/documents` | Attach (acquisition-level roles only). |
| POST | `/asset-acquisitions/{acq_id}/documents/upload` | Upload + attach. |
| DELETE | `/asset-documents/{link_id}` | Unlinks. The underlying document is left alone. |
| GET | `/asset-documents/{link_id}/thumbnail` | Decrypts and streams the file so photographs display in the UI. |

### 7.14 Asset reports — `app/routers/asset_reports.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/asset-reports` | The 10 report keys with titles and descriptions. |
| GET | `/asset-reports/{report_key}/export` | `?format=xlsx\|pdf`, `financial_year_id`, `units`, plus filters. |
| GET | `/asset-reports/{report_key}/preview-html` | Server-rendered HTML preview. |
| POST | `/asset-reports/pack` | Multi-sheet / multi-page pack with a cover sheet. |
| POST | `/asset-reports/archive` | Renders and files the report into a DocVault bucket, encrypted like any other document. |

Report keys: `fixed_asset_register`, `companies_act_depreciation`, `income_tax_depreciation`, `it_asset_annexure`, `additions_register`, `disposals_register`, `cwip_register`, `dimension_summary`, `physical_verification`, `gst_itc_summary`.

Shared filters: `lifecycle_status` (or the literal `all` to drop the default), `operational_status`, `condition`, `category_id`, `location_id`, `branch_id`, `custodian_id`, `acquisition_id`. Unknown enum values return **422** naming the allowed values — they are coerced early precisely so an unknown string cannot reach the Postgres enum comparison and 500 the report. `fixed_asset_register` and `dimension_summary` default to `capitalized`. The three depreciation reports require a **finalized** run for the FY, else **409** with instructions.

### 7.15 Sales — `app/routers/sales.py`

| Method | Path | Auth |
|---|---|---|
| GET | `/sales` | CU |
| GET | `/sales/aggregate` | CU |
| POST | `/sales` | CU |
| GET | `/sales/{sales_id}` | CU |
| PATCH | `/sales/{sales_id}` | CU |
| POST | `/sales/import/inspect` | CU |
| POST | `/sales/import` | CU |
| GET | `/sales/export/excel` | CU |

### 7.16 KRA — `app/routers/kra.py`

| Method | Path | Auth |
|---|---|---|
| GET | `/kra` | CU |
| POST | `/kra` | CU |
| GET | `/kra/{kra_id}` | CU |
| PATCH | `/kra/{kra_id}` | CU |

Visibility follows `get_visible_user_ids`: an admin sees all, anyone else sees only their own.

### 7.17 Activity and notifications

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/activity-log` | CU | Company-scoped, newest first, filterable. |
| GET | `/notifications` | CU | For the current user. |
| PATCH | `/notifications/{notification_id}/read` | CU | Sets `read_at`. |

### 7.18 DocVault — `app/routers/docvault.py`

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/docvault/buckets` | CU:admin | `visibility` = `everyone` or `restricted`. |
| GET | `/docvault/buckets` | CU | Only buckets the caller can see. |
| GET | `/docvault/approvers` | CU | Users who could approve here (DocVault access + bucket access). |
| PATCH | `/docvault/buckets/{bucket_id}` | CU:admin | Rename. |
| PATCH | `/docvault/buckets/{bucket_id}/access` | CU:admin | Replace the grant list / flip visibility. |
| DELETE | `/docvault/buckets/{bucket_id}` | CU:admin | |
| POST | `/docvault/documents` | CU | Multipart: `title`, `file`, `bucket_id?`, `tags?` (comma-separated), `is_editable?`, `needs_approval?`, `approver_id?`. Encrypts, writes v1, optionally sets `pending_approval` and notifies the approver. |
| POST | `/docvault/documents/{document_id}/versions` | CU | New encrypted version; `version_number` increments; `current_version_id` moves. |
| GET | `/docvault/documents` | CU | Bucket-filtered by access. |
| GET | `/docvault/documents/search` | CU | |
| GET | `/docvault/documents/{document_id}` | CU | |
| GET | `/docvault/documents/{document_id}/download` | CU | Unwraps KEK → DEK → decrypts → streams. |
| PATCH | `/docvault/documents/{document_id}` | CU | Status, title, tags, bucket, approver, approval notes. See the guardrails below. |
| DELETE | `/docvault/documents/{document_id}` | CU | Same guardrails. |

**Access rules.** `accessible_bucket_ids` returns `None` for an admin (sees everything) or the set of `everyone` buckets ∪ buckets the user created ∪ buckets explicitly granted. A document in a bucket the caller cannot see returns **404**, not 403 — its existence is not disclosed.

**Approval guardrails on `PATCH`/`DELETE`:**
* While `status == pending_approval`, only the assigned approver or an admin may modify *anything*.
* A locked (`is_editable == False`) document freezes `title`, `tags` and `bucket_id`; status changes and re-enabling `is_editable` are always allowed, and a request that re-enables editing in the same call may also change the gated fields.
* Approver candidates are validated to be live, active, DocVault-capable, and to have access to the target bucket.
* Transitioning **out of** `pending_approval` stamps `approved_at` and notifies the creator (`docvault.approval_resolved`).

### 7.19 Compliance — `app/routers/compliance.py`

One factory, `create_compliance_router(domain, prefix, tags)`, produces **two identical routers**, each gated by `Depends(require_module(domain.value))`:

* `secretarial_router` → `/api/v1/secretarial` (module `secretarial`)
* `roc_router` → `/api/v1/roc` (module `roc`)

| Method | Path (relative) | Notes |
|---|---|---|
| POST | `/document-types` | Company-owned type. |
| GET | `/document-types` | System-shipped (`company_id IS NULL`) **plus** company-owned, in this domain. |
| PUT | `/document-types/{dt_id}` | Company-owned only. |
| DELETE | `/document-types/{dt_id}` | **409** if any record uses it. |
| GET | `/bucket` | The domain's DocVault bucket reference (read-only lookup). |
| POST | `/meeting-records` | |
| GET | `/meeting-records` | |
| GET | `/meeting-records/unsynced` | Documents in the domain bucket with no `meeting_records` row yet. |
| POST | `/meeting-records/sync` | Imports those documents as unclassified records. |
| PATCH | `/meeting-records/{record_id}` | |
| POST | `/meeting-records/{record_id}/archive` | Snapshots the linked document's status + `is_editable`, then archives both. |
| POST | `/meeting-records/{record_id}/unarchive` | Restores both from the snapshot exactly. |

Bucket resolution lives server-side in `services/compliance_bucket` (`ensure_compliance_bucket` / `find_compliance_bucket`) — it used to be done in the browser by matching the literal bucket name, which sync detection cannot rely on.

### 7.20 AuditEase — company side — `app/routers/auditease.py`

Prefix `/api/v1/auditease`.

**Trial balance**

| Method | Path | Notes |
|---|---|---|
| POST | `/engagements/{id}/trial-balance/inspect` | **Step 1.** Every sheet's headers, 8 preview rows, the detected header row, and a suggested column map. |
| POST | `/engagements/{id}/trial-balance/preview` | **Step 3.** Reports what *would* happen — diagnostics, sample rows, re-import impact, `would_import` / `would_skip`. Writes nothing. Only a structurally unusable mapping is a 400; every other finding comes back as data, so the review screen is non-blocking by construction. |
| POST | `/engagements/{id}/trial-balance/import` | **Step 4.** Upserts. |
| GET | `/engagements/{id}/trial-balance` | Accounts **plus** server-computed totals, `sign_convention`, `sign_unresolved_count`, `inconsistent_row_count`, `warnings`. |
| POST | `/engagements/{id}/trial-balance/sign-convention` | Corrects a mis-detected convention **without re-importing** — rewrites only derived canonical figures, never row identity, so every `audit_entry_lines.ledger_id` stays valid. |

**Chart of accounts**

| Method | Path | Notes |
|---|---|---|
| GET | `/ledger-groups` | Seeded top groups (idempotently ensured) + company groups. |
| POST | `/ledger-groups` | |
| PATCH | `/ledger-groups/{group_id}` | Rename. Seeded groups → **403**. |
| DELETE | `/ledger-groups/{group_id}` | |
| POST | `/engagements/{id}/ledgers/{ledger_id}/map` | |
| POST | `/engagements/{id}/ledgers/bulk-map` | |
| POST | `/engagements/{id}/ledgers/unmap` | |
| GET | `/engagements/{id}/mapping-sources` | Prior engagements whose mappings can be copied. |
| POST | `/engagements/{id}/mappings/import` | Deterministic one-to-one plan (`services/mapping_import`): match by normalised ledger code, else normalised name. |

**Engagements and auditors**

| Method | Path | Auth |
|---|---|---|
| POST | `/engagements` | CU:admin |
| GET | `/engagements` | CU |
| GET | `/engagements/{id}` | CU |
| PATCH | `/engagements/{id}/close` | CU:admin |
| DELETE | `/engagements/{id}` | CU:admin |
| POST | `/engagements/{id}/auditors/invite` | CU:admin |
| GET | `/engagements/{id}/auditors` | CU |
| PATCH | `/engagements/{id}/auditors/{auditor_id}` | CU:admin — edit `area_permissions` |
| DELETE | `/engagements/{id}/auditors/{auditor_id}` | CU:admin — revoke |
| GET | `/engagements/{id}/auditors/{auditor_id}/activity` | CU |
| GET | `/engagements/{id}/auditors/{auditor_id}/activity-report` | CU — xlsx/pdf |

**Entries, requirements, queries**

| Method | Path | Notes |
|---|---|---|
| PATCH | `/entries/{entry_id}/approve` | Approve or reject with a comment. Only **approved** entries move the numbers. |
| GET | `/engagements/{id}/entries` | |
| GET | `/engagements/{id}/requirement-requests` | With submission rounds and their documents. |
| POST | `/engagements/{id}/requirement-requests/{req_id}/respond` | Multipart: `text_answer?` + files + existing `document_ids`. Creates a new append-only round. |
| GET | `/engagements/{id}/queries` | |
| POST | `/engagements/{id}/queries/{query_id}/messages` | |

**Reports**

| Method | Path | Notes |
|---|---|---|
| GET | `/engagements/{id}/reports/preview` | Available reports + headline figures. |
| GET | `/engagements/{id}/reports/{report_key}/preview-html` | |
| GET | `/engagements/{id}/reports/{report_key}/export` | `?format=xlsx\|pdf&units=` |
| GET | `/engagements/{id}/reports/pack` | All nine sheets + cover. |
| POST | `/engagements/{id}/reports/archive` | Into DocVault, encrypted. |
| POST | `/engagements/{id}/reports/generate` | |

Report keys: `balance_sheet`, `profit_and_loss`, `notes_to_accounts`, `trial_balance_detailed`, `trial_balance_summary`, `extended_trial_balance`, `adjusting_entries`, `ledger_mapping`, `exceptions`.

### 7.21 AuditEase — auditor side — `app/routers/auditor_engagements.py`

Prefix `/api/v1/auditor`. Every route runs `check_auditor_access(engagement_id, auditor, area)`, which requires an active grant **and** the named area in `area_permissions`.

| Method | Path | Area |
|---|---|---|
| GET | `/engagements` | — |
| POST | `/engagements/{id}/accept` | — (flips the grant to `accepted`, engagement to `active`) |
| GET | `/engagements/{id}/trial-balance` | `trial_balance` |
| POST | `/engagements/{id}/entries` | `entries` |
| GET | `/engagements/{id}/entries` | `entries` |
| DELETE | `/entries/{entry_id}` | `entries` |
| POST | `/engagements/{id}/requirement-requests` | `requirements` |
| GET | `/engagements/{id}/requirement-requests` | `requirements` |
| PUT | `/engagements/{id}/requirement-requests/{req_id}` | `requirements` |
| DELETE | `/engagements/{id}/requirement-requests/{req_id}` | `requirements` |
| POST | `/engagements/{id}/requirement-requests/{req_id}/close` | `requirements` |
| POST | `/engagements/{id}/requirement-requests/{req_id}/reopen` | `requirements` |
| GET | `/engagements/{id}/requirement-requests/import-template` | `requirements` |
| POST | `/engagements/{id}/requirement-requests/import` | `requirements` — all-or-nothing 4-column Excel import |
| GET | `/engagements/{id}/queries` | `queries` |
| GET | `/engagements/{id}/queries/{query_id}` | `queries` |
| POST | `/engagements/{id}/queries` | `queries` |
| POST | `/engagements/{id}/queries/{query_id}/messages` | `queries` |
| POST | `/engagements/{id}/queries/{query_id}/close` | `queries` |
| GET | `/documents/{document_id}` | `documents` |
| GET | `/documents/{document_id}/download` | `documents` |

Auditors can read a company document only if `document_access.auditor_can_access_document` says so — i.e. it is attached to a requirement response or a query message on an engagement they hold, or an explicit `document_access_overrides` row grants it.

---

## 8. Core flows, end to end

### 8.1 Lead → company → activated admin

```
1. Visitor fills the landing-page modal
     POST /api/v1/leads/interest        (honeypot + 3/10min rate limit)
     → Lead(status=new)

2. Operator reviews
     python3 list_leads.py              → GET /api/v1/owner/leads
     PATCH /owner/leads/{id}/status     → contacted

3. Operator provisions
     POST /owner/leads/{id}/provision   (or python3 create_company.py → POST /auth/companies)
     ├─ Company row
     ├─ activation key: secrets.token_urlsafe(24), bcrypt-hashed onto the company, 48h TTL
     ├─ seed_global_asset_reference_data(company_id)   ← Schedule II tree + Appendix I blocks
     ├─ CompanyKey: AES-GCM(root KEK) over a fresh 32-byte company KEK
     ├─ CompanyUser(role=admin, hashed_password="__pending__", is_active=False)
     └─ lead.status = converted
     → plaintext activation key returned ONCE

4. Operator sends the key out of band. Admin visits /activate
     POST /auth/company/activate {email, activation_key, password, full_name}
     ├─ rate limited 10/15min
     ├─ live-rows-only lookup; must be a pending admin
     ├─ expiry check, then bcrypt-verify the key
     ├─ set real password, full_name, is_active=True
     ├─ company.activation_used_at = now; key hash and expiry cleared (one-shot)
     └─ ActivityLog "company.admin_activated"
     → 204. No session issued.

5. Admin logs in at /login → POST /auth/company/login
6. ProfileGate blocks the app shell until the company profile is completed
     PUT /company/profile → profile_completed = true
```

### 8.2 Document upload, approval, download

```
POST /docvault/documents (multipart)
 ├─ bucket access check (404 if not visible)
 ├─ if needs_approval: approver must be live+active, DocVault-capable, and able to see the bucket
 ├─ Document row (status = uploaded | pending_approval)
 └─ handle_file_upload:
      raw_dek, _  = generate_dek()
      ct, nonce   = AES-GCM(raw_dek).encrypt(plaintext)
      kek         = decrypt_company_kek(company_keys row)
      enc_dek, n2 = AES-GCM(kek).encrypt(raw_dek)
      write  {VAULT}/{company_id}/{uuid}.enc  =  nonce || ct
      checksum = sha256(plaintext)
      DocumentVersion(version_number=1, …)
 ├─ document.current_version_id = version.id
 ├─ Notification "docvault.approval_requested" → approver
 └─ ActivityLog "document.uploaded"

PATCH /docvault/documents/{id}  (approver or admin while pending)
 ├─ status → verified / action_required / …
 ├─ approved_at = now
 └─ Notification "docvault.approval_resolved" → creator

GET /docvault/documents/{id}/download
 └─ read file → split nonce||ct → decrypt_dek(enc_dek, n2, kek) → decrypt_file_data → stream
```

### 8.3 Trial balance import — the four-step wizard

```
Step 1  POST …/trial-balance/inspect      (file)
        → every sheet: headers, 8 preview rows, detected header row, suggested column map
           detect_header_row() skips title/period banner rows
           suggest_column_map() uses one shared synonym list so UI and server agree

Step 2  User confirms sheet + column mapping in the browser

Step 3  POST …/trial-balance/preview      (file, column_map, sheet?, header_row?, sign_convention?)
        → diagnostics (dropped rows WITH REASONS, inconsistent rows, stated vs computed totals),
          sample rows, re-import impact, would_import / would_skip
        Only a structurally unusable mapping is a 400. Everything else is data.

Step 4  POST …/trial-balance/import       (…, confirm)
        parse_trial_balance → canonical rows
        plan_reimport(existing, parsed, referenced_ledger_ids)
          match by ledger_code, else by ledger_name
          UPDATE IN PLACE — never DELETE+INSERT
        → ids survive, so mapped_group_id and every audit_entry_lines.ledger_id survive too
```

> **Why upsert matters.** The original import did `DELETE FROM trial_balance_accounts WHERE engagement_id = …` then re-inserted. Because `audit_entry_lines.ledger_id` is `ON DELETE CASCADE`, that silently destroyed approved audit-entry lines — a blanket 409 guard was the only thing preventing it — and it threw away every `mapped_group_id`. Updating in place preserves `id`, which preserves both.

### 8.4 Sign convention detection

Every ledger is normalized at the import boundary into a **signed net debit** (debit positive, credit negative). `detect_sign_convention` infers how the source encoded signs and reports an honest confidence:

| Convention | Source shape |
|---|---|
| `explicit` | The cell carries a `Dr`/`Cr` marker, or there is a Dr column + Cr column pair (`net = abs(dr) − abs(cr)`) |
| `signed` | Credit balances are negative; the closing column sums to ~0 |
| `magnitude` | Everything is positive; the side comes from the mapped group's nature |
| `derived` | No closing column at all; `closing = opening + debit − credit` |

`canonical_net_debit()` resolves in strict precedence: explicit marker → column pair → mapped group nature → bare magnitude (which sets `sign_unresolved = True` so the UI can ask rather than silently guess). `POST …/sign-convention` is the escape hatch that makes an ambiguous detection recoverable instead of permanent.

### 8.5 Auditor invitation

```
POST /auditease/engagements/{id}/auditors/invite  {email, area_permissions?}
 ├─ 409 if the engagement is closed
 ├─ normalize_area_permissions(None) => all five areas true
 ├─ if the email has an Auditor row:
 │     existing non-revoked grant → 400 "already invited"
 │     existing REVOKED grant     → resurrected in place (keeps uq_grant_auditor_engagement)
 │     no grant                   → new AuditorEngagementGrant(status=invited)
 │  else:
 │     → PendingAuditorInvite (409 if one already pending)
 ├─ ActivityLog "auditor.invited"
 ├─ engagement.status: draft → invited
 └─ EMAIL (best effort, never fails the request):
      base_url from DOMAIN (adds https:// unless localhost/127.0.0.1)
      registered auditor → {base}/auditor/login    "Log In to Audit Portal"
      unknown email      → {base}/auditor/register?email=…  "Set Up Auditor Account"
      from = company SMTP config if present, else server default
      subject = "Audit Invitation: {company} — {period_label}"
      record_email_log(status="queued", source="auditease.invite")
      send_email_async.delay(msg, company_id, log_id)     ← Celery

Later: POST /auth/auditor/register with that email
 └─ every PendingAuditorInvite for the email becomes an AuditorEngagementGrant

Then: POST /auditor/engagements/{id}/accept
 └─ grant.status = accepted; engagement.status = active
```

### 8.6 Asset lifecycle

```
   quick-add / existing / import / explode
              │
              ▼
          ┌────────┐   submit   ┌───────┐   approve (ADMIN)  ┌─────────────┐  dispose  ┌──────────┐
          │ draft  │──────────▶ │ ready │──────────────────▶ │ capitalized │─────────▶ │ disposed │
          └────────┘◀────────── └───────┘                    └─────────────┘           └──────────┘
              │        reject                                       │
              │ DELETE (admin only)                                 └─ depreciates
              ▼
           (gone)
```

Required-field validation is tiered by **transition**, not by INSERT (`services/asset_validation.validate_transition`):

* `→ draft` — asset name + category. Save and walk away.
* `→ ready` — every commercial and statutory field, plus the invoice and a photograph. This is the completeness gate.
* `→ capitalized` — the dates that start depreciation, and a non-zero cost.

It returns **every** issue rather than raising on the first one, so `POST /assets/{id}/submit` responds 422 with the full checklist.

`apply_to_siblings` transitions every unit of the acquisition at once, skipping units already past that state.

**Disposal** (`validate_disposal`) additionally checks that the disposal date falls inside a company financial year and whether that FY already has a finalized depreciation run.

### 8.7 Asset tag allocation

Codes look like `COMP-HO-000137`: a category-derived prefix, an optional branch code, and a zero-padded running number. The number comes from an explicit per-prefix `asset_code_sequences` row locked `FOR UPDATE` — **not** `MAX(asset_code) + 1`, because exploding a 50-unit acquisition allocates fifty codes at once and two concurrent explodes reading the same MAX would hand out the same tags. The string is deliberately plain ASCII so it can be QR-encoded later without a schema change.

### 8.8 Depreciation run

```
POST /depreciation/runs {financial_year_id, notes?}
  execute_depreciation_run:
    ├─ resolve the FY (404 if missing)
    ├─ sequence gate: prior years must be finalized (409 otherwise)
    ├─ load prior FY's FINALIZED run lines → opening balances
    ├─ for each capitalized/disposed asset:
    │     build_asset_depreciation_input(asset, prior_line)
    │     calculate_asset_depreciation(inp, fy_start, fy_end)   ← pure Schedule II engine
    │     build_schedule_ii_trace(inp, result)                  ← labels the same numbers
    │     → AssetDepreciationLine (+ calc_trace JSONB)
    ├─ for each IT block with assets:
    │     build_it_block_input(block, block_assets, prior_line, fy_start, fy_end)
    │     calculate_it_block_depreciation(inp)                  ← pure s.32 engine
    │     build_it_block_trace(inp, result)
    │     → ItBlockDepreciationLine (+ calc_trace)
    └─ DepreciationRun(status=draft)

POST /depreciation/runs/{id}/finalize
    → status=finalized, finalized_at/by set
    → the partial unique index guarantees at most ONE finalized run per FY

POST /depreciation/runs/{id}/reopen  {reason}    (admin)
    → 409 if a later FY's run would be invalidated
    → ActivityLog "depreciation.run.reopened" with the reason
```

Finalized runs store **snapshot** lines, which is why a master-data edit can never retroactively change history (see `services/master_impact`).

---

## 9. Domain engines

All engines are pure `Decimal` code with `ROUND_HALF_UP`, no DB, no ORM.

### 9.1 Acquisition costing — `services/asset_costing.py`

The rule that matters, because getting it backwards misstates both the balance sheet and the tax computation:

* GST for which **input tax credit is available** is *recoverable* — **not** part of the asset's cost.
* GST for which credit is **blocked** (CGST Act s.17(5) — motor cars, etc.) or simply **not taken** is **capitalized** into cost.
* `partial` splits by `itc_eligible_pct`.

`money(value)` quantizes to paise, half-up — the single rounding rule for the module. `allocate_per_unit(total, quantity)` splits a total into parts that sum to **exactly** the total (the remainder is distributed, not dropped), so per-unit costs always tie back to the landed cost.

`_split_gst` decides CGST+SGST vs IGST by comparing the supplier's `state_code` with the place of supply (`asset_register.resolve_place_of_supply` — the branch's own GSTIN state if it has one, else the company's).

Also here: `compute_residual_value` (Schedule II expresses residual as a percentage of original cost) and `compute_warranty_expiry` (calendar-month addition clamped to the last valid day of the target month).

### 9.2 Companies Act Schedule II — `services/depreciation.py`

Handles SLM and WDV, pro-rata additions, disposals, pre-cutover opening balances, and residual-value capping. `_remaining_life_days` derives remaining life from how much of the depreciable base is left, rather than trusting a stored counter. Raises `DepreciationDataError` (→ 422) when input violates a statutory or computation rule.

### 9.3 Income Tax s.32 — `services/it_depreciation.py`

Block-level WDV depreciation with:

* **180-day rule** — an asset put to use for ≥ 180 days gets the full prescribed rate; < 180 days gets half.
* **Sale proceeds** are deducted from full-rate additions first, then opening WDV.
* **Section 50 STCG** when sale proceeds exceed the block value.
* **Section 50 STCL** when the block ceases to exist (every asset in it disposed).

### 9.4 Trial balance core — `services/trial_balance.py`

**One internal representation:** a signed **net debit** per ledger, normalized at import.

```
present(net_debit, nature) =  net_debit    if nature is debit
                           = -net_debit    if nature is credit

assets      =  Σ nd(Assets)          liabilities = -Σ nd(Liabilities)
expenditure =  Σ nd(Expenditure)     income      = -Σ nd(Income)
```

Presentation becomes a single function and every total becomes plain addition — no `abs()` anywhere. Notable pieces:

| Function | Role |
|---|---|
| `parse_amount` | One cell → signed Decimal + optional Dr/Cr tag. Handles `_extract_side` (rejects two markers in one cell) and `_resolve_separators` (decides which of `.` and `,` is decimal) |
| `classify_row` | Junk rows are **dropped with a reason**, never counted as errors |
| `detect_header_row` / `build_headers` / `suggest_column_map` | Header detection and one shared synonym list |
| `validate_rows` | Cross-checks the file as a whole. **Never blocking** — findings are data |
| `build_figures` | TB accounts → canonical pre-rounded `LedgerFigure`s, with approved adjustments folded in |
| `summarize` | Statement totals by pure addition |
| `build_group_tree` | Hierarchical `GroupNode` tree with subtotals rolled up at every level |
| `make_profit_figure` | The Balance Sheet's balancing figure, as a real renderable line |

`services/trial_balance_query.load_engagement_figures` is the **single** implementation behind every consumer: the company TB endpoint, the auditor TB endpoint, the report preview, the report generator, the import result and the sign-convention repair endpoint. Nothing in the frontend computes a subtotal.

`load_adjustments` counts net-debit adjustments from **approved entries only** — proposed and rejected entries never move the numbers.

### 9.5 Calculation traces — `services/calc_trace.py` + `calc_trace_builders.py`

A trace explains a computed figure: an ordered list of steps, each carrying the symbolic formula, the same formula with this entity's values substituted in, and the result.

Two rules make it trustworthy:

1. **Formatting happens once, here**, using the same quantization the engines use — so a trace cannot display a number that differs from the figure it explains.
2. **Nothing reads a trace back to compute anything.** It is output, never input, so it never becomes a second source of truth.

The engines stay math-only and hand over raw `intermediates`; the builders only name and format what the engine already did. Statutory notes are deliberately sparse — they appear on the rules that surprise people (pro-rata charge, residual cap, the 180-day half rate) and on nil-value cases where a bare `0.00` would look like a bug.

Traces are persisted on `*_depreciation_lines.calc_trace` (nullable — nothing may depend on a trace being present) and re-derivable live via `POST /depreciation/explain` and `POST /assets/cost-preview`. The frontend renders them in `components/calc/CalculationDrawer.tsx`.

### 9.6 Master-data impact — `services/master_impact.py`

Because finalized runs store snapshot lines, a master edit can never retroactively change history. Effects therefore classify **exhaustively** as:

* `none` — cosmetic, or a default that is only copied onto *future* assets.
* `future_only` — feeds future run math.

When finalized years were computed at values that differ from the row's current state, the message says to **reopen those years** rather than pretending nothing happened.

---

## 10. Reporting subsystem

The organising principle: **build each report once as a neutral `ReportDocument`, then render it twice** — to XLSX and to PDF. The builder computes every total; the renderers only format and display.

```
data ─▶ builder (pure) ─▶ ReportDocument ─┬─▶ workbook.py  (openpyxl) ─▶ .xlsx
                                          ├─▶ pdf.py (Jinja2 → HTML) ─▶ preview-html
                                          └─▶ pdf.py (WeasyPrint)    ─▶ .pdf
                                                     │
                                                     └─▶ vault.archive_report ─▶ encrypted DocVault document
```

**`reporting/document.py`** — frozen dataclasses, no I/O, no library imports: `ColumnKind` (semantic type driving alignment and formatting), `ColumnSpec`, `ReportRow`, `ReportTotal`, `ReportSection` (nests via `children`, producing subtotals at every level without duplicate arithmetic), `ReportDocument`.

**`reporting/format.py`** — the single source of truth for Indian digit grouping (`12,34,567.00`), scale rounding for Schedule III (`thousands` / `lakhs` / `crores` via the `units` parameter), percentages and `DD/MM/YYYY` dates.

**`reporting/workbook.py`** — styled statutory spreadsheets: standardized title block (company, title, subtitle, period, units), frozen header panes, depth-first section rendering, thin top borders on sub-section totals (level ≥ 1), double bottom borders on grand totals (level 0), auto-fitted or explicit column widths, and an automated **Cover sheet** for multi-sheet packs.

**`reporting/pdf.py`** — `render_html` / `render_pdf` (WeasyPrint), plus `render_pack_html` / `render_pack_pdf` for combined multi-page documents with a cover page. `landscape` is a parameter.

**`reporting/vault.py`** — `archive_report` wraps rendered bytes in a `_BytesUploadAdapter` (exposing async `read()`, `filename`, `content_type`) and pushes them through the **standard** `handle_file_upload`, so an archived report is encrypted exactly like any other DocVault document.

**`reporting/auditease_reports.py`** — nine builders, registered in `AUDITEASE_BUILDERS`: Balance Sheet (Schedule III Div I), Statement of Profit and Loss, Notes to Accounts, TB Detailed, TB Summary, Extended Trial Balance (10-column: Unadjusted → Adjustments → Adjusted → P&L → BS), Adjusting Entries Register, Ledger Mapping & Verification Audit, Exceptions & Diagnostics.

**`reporting/asset_reports.py`** — the ten asset builders listed in §7.14.

**`reporting/activity_report.py`** — per-auditor engagement activity, pure (takes prepared event dicts, touches no DB), rendered twice like everything else.

---

## 11. Email subsystem

```
app/services/email/
  schemas.py    EmailMessage, EmailAttachment, EmailConfig, EmailDeliveryResult, EmailDeliveryError
  templates.py  Jinja2 env (autoescape html/xml) + extract_plain_text()
  client.py     EmailService — MIME build, SMTP send, verify_connection
  resolver.py   per-company config resolution + record_email_log
  tasks.py      Celery task send_email_async
  templates/    base.html, branded_message.html, auditor_invite.html
```

**Config resolution** (`resolver.get_email_config_for_company`): look up an **active** `company_smtp_configs` row → unwrap the company KEK → `decrypt_smtp_password` → build an `EmailConfig`. Any failure logs and returns `None`, and `get_email_service_for_company` then falls back to the **server-default** `SMTP_*` settings. So a company with no SMTP config still sends mail, just from the platform address.

**MIME construction** (`client.build_mime_message`): `multipart/mixed` wrapping a `multipart/alternative` when there are attachments, otherwise `multipart/alternative` directly. HTML comes from `template_name` (rendered through Jinja2 with autoescape) or `body_html`; the plain-text part is auto-derived by `extract_plain_text` when not supplied — it strips `<style>`/`<script>`, converts `<br>`/`</p>`/headings to newlines, rewrites links as `text (url)`, strips remaining tags, collapses blank lines and unescapes entities. Headers are RFC 5322 compliant via `email.utils.formataddr` / `formatdate` / `make_msgid` (the Message-ID domain comes from the sender address).

**Sending** (`client.send`): connects (`SMTP_SSL` if `use_ssl`, else `SMTP` + optional `starttls`), logs in when credentials are present, and sends. Errors are normalised into `EmailDeliveryError` with a readable message — authentication failures decode the server's `smtp_error` bytes. Returns `{success, message_id, recipients, duration_ms}`.

**`verify_connection`** does the full handshake + auth + `NOOP` and returns host, port, user, TLS/SSL flags, latency and the server's response — **without sending anything**. This is what `POST /company/smtp/verify` and `send_email.py --verify` call.

**Async delivery** (`tasks.send_email_async`): a Celery task with `autoretry_for=(SMTPException, OSError, TimeoutError)`, exponential backoff capped at 60 s, `max_retries=3`. It resolves the company config *inside the worker* (its own `NullPool` engine — the API's pooled engine must not cross the process boundary) and updates the `EmailLog` row to `sent` (with `message_id` and `duration_ms`) or `failed` (with the error, truncated to 2000 chars). **Permanent** failures — "not configured", "authentication failed", "template" — return instead of raising, so Celery does not burn retries on something that cannot succeed. Attachment bytes survive JSON serialization via base64 `field_serializer`/`field_validator` on `EmailAttachment`.

**Audit trail.** Every dispatch writes an `email_logs` row first (`status="queued"`, with a `source` tag such as `auditease.invite`), and the worker updates it. Admins read them at `GET /company/smtp/logs`.

---

## 12. Background jobs

`app/worker.py` builds the Celery app (`kubera`) on the Redis broker/backend, JSON serialization only, UTC.

**Beat schedule:**

| Task | Schedule |
|---|---|
| `app.worker.nightly_backup` | `crontab(hour=2, minute=0)` — 02:00 UTC daily |

`nightly_backup` creates `/data/backups`, then:
1. `pg_dump -Fc -f /data/backups/db_backup_{ts}.dump` — custom format, restored with `pg_restore` (not `psql`). Connection args are built from `DATABASE_URL` by `pg_dump_target()` rather than passed as a URL, because `pg_dump` doesn't understand the `+asyncpg` dialect suffix and silently falls back to a local socket if handed the raw URL. Raises (does not skip) on failure or an empty output file.
2. `tar -czf /data/backups/vault_backup_{ts}.tar.gz -C /data vault` — note the tarball root is `/data`, so it contains a top-level `vault/` directory (contrast with `ops/kubera-export.sh`'s bundle tarball, which is rooted at `/data/vault` itself — see `docs/OPERATIONS_RUNBOOK.md` §7 for why the two are not interchangeable).

Returns `{"status": "success", "timestamp": ts, "db_backup": ..., "db_bytes": ..., "vault_backup": ..., "vault_bytes": ..., "pruned": ...}`. Pruned by `BACKUP_RETENTION_DAYS` (default 14).

`app/services/email/tasks` is imported at the bottom of `worker.py` so the worker discovers `send_email_async` on startup.

---

## 13. Frontend architecture

### 13.1 Route tree

```
/                          RootDispatcher — host starts with "app." ? redirect /app : LandingPage
/landing                   LandingPage
/internal/owner-vault      OwnerLeadsPage         (stealth owner console, uses the internal API key)
└─ DomainIsolatedApp       redirects marketing-domain visitors to app.<domain>
   ├─ companyRoutes  (CompanyAuthProvider)
   │   /login  /activate
   │   /app  (CompanyGuard)
   │     onboarding                       ← outside the shell AND ProfileGate (no redirect loop)
   │     └─ CompanyShell
   │        └─ ProfileGate                ← everything below is blocked until profile_completed
   │           /app                       Dashboard          [module dashboard]
   │           /app/users                 UsersDirectory     [AdminGuard]
   │           /app/kra                   KraPage            [module kra]
   │           /app/assets                AssetsPage         [module assets]
   │             masters | reports | new/existing | :assetId
   │           /app/sales                 SalesPage          [module sales]
   │           /app/custom-fields         CustomFieldsPage
   │           /app/docvault              DocVaultPage       [module docvault]
   │           /app/docvault/graph        DocVaultGraphPage  [module docvault]
   │           /app/compliance/roc        CompliancePage     [module roc]
   │           /app/compliance/secretarial CompliancePage    [module secretarial]
   │           /app/auditease             EngagementsPage    [module auditease]
   │             :engagementId            EngagementWorkspace
   │           /app/notifications         [module notifications]
   │           /app/activity              [module activity]
   │           /app/settings/profile      CompanyProfilePage
   │           /app/settings/user         UserSettingsPage
   └─ auditorRoutes  (AuditorAuthProvider)
       /auditor/login  /auditor/register
       /auditor/app  (AuditorGuard)
         └─ AuditorShell
            index                          AuditorEngagements
            :engagementId                  AuditorEngagementWorkspace
```

Literal asset paths are declared **before** `:assetId`, which would otherwise swallow `masters`, `reports` and `new/existing`.

### 13.2 HTTP layer

`src/api/http.ts` defines `HttpClient`, constructed with an `AuthAdapter` = `{storage, refreshPath, onAuthFailure}`. Two instances exist (`api/clients/company.ts`, `api/clients/auditor.ts`), each bound to its own namespaced `localStorage` and its own refresh endpoint.

* Attaches `Authorization: Bearer …` when a token is present.
* `formData` uploads let the browser set the multipart boundary; JSON bodies get `Content-Type: application/json`.
* `responseType`: `json` (default), `blob` (downloads), `text` (the report preview returns HTML — without `text` the client would run `JSON.parse` over an HTML body and throw).
* On a **401** for an authenticated request it performs **one** refresh-and-retry; if refresh fails it calls `onAuthFailure()` which forces logout.
* `ApiError(status, message, detail)` unwraps FastAPI's `detail` — a string, or the first `msg` of a validation array.

### 13.3 Layering

```
src/api/endpoints/*   thin typed functions, one per API surface
src/api/hooks/*       React Query wrappers (query keys, invalidation, optimistic updates)
src/api/contracts/*   runtime contract assertions with their own tests
src/api/schema.d.ts   generated from the live OpenAPI document
```

`src/auth/createIdentityAuth.tsx` is the factory that builds a provider + guard for an identity; `company/` and `auditor/` each instantiate it. `ModuleGuard`, `AdminGuard` and `ProfileGate` are the three declarative gates. `config/navigation.ts` drives the sidebar off the same module IDs the backend enforces.

### 13.4 Notable UI

* **DocVault 3D graph** (`pages/company/docvault/graph/`) — `three` + `3d-force-graph`, with its own `useGraphData` / `useGraphControls` hooks and pure helpers for dim state, dynamic fog, text sprites and theming, each unit-tested.
* **Calculation drawer** (`components/calc/`) — renders a `CalcTrace` step by step, with `traceFromCostPreview` adapting the costing response and `traceToText` producing a copyable form.
* **Requirements workspace** (`components/auditease/requirements/`) — requirement cards, submission timeline, DocVault picker, bulk import modal, priority chips, progress computation.
* **UI kit** (`components/ui/`) — Button, Card, CommandPalette, ConfirmDialog, CountUp, DataTable, Drawer, EmptyState, Field, FileUploadDropzone, FinalBadge, Modal, Sidebar, Sparkline, Spinner, StatCard, StatusBadge, Switch, Tabs, Toast, TopBar.

### 13.5 Serving

`frontend/nginx.conf`: `/index.html` is `no-store` (the shell must be revalidated after every deploy); `/assets/` is `immutable, max-age=31536000` because Vite filenames carry a content hash — and a **missing** bundle returns a real 404 via `@missing_asset` rather than the SPA HTML fallback, which would otherwise surface as a confusing parse error. `/api/` proxies to `api:8000` with `X-Real-IP` and forced `Cache-Control: no-store`. `resolver 127.0.0.11` plus a `set $api_upstream` variable means Nginx re-resolves the upstream instead of failing at startup when the API container is not up yet.

---

## 14. Edge, gateway and maintenance mode

### 14.1 The switch

The `gateway` container's `nginx.conf` contains a single `include /var/lib/kubera-maintenance/active.conf` — a **symlink** in the persistent `maintenance_runtime` volume pointing at either `/etc/nginx/modes/app.conf` or `/etc/nginx/modes/maintenance.conf`. `initialize-runtime.sh` (a `docker-entrypoint.d` hook) creates the symlink pointing at `app.conf` and writes `{"mode":"active"}` into `state.json` on first boot.

The maintenance page is a standalone `index.html` + `maintenance.css` + `maintenance.js` baked into the image at `/srv/maintenance`. It reads `/maintenance-state.json` (served `no-store`) for its countdown. **Nothing in maintenance mode depends on React, FastAPI, Postgres or Redis** — that is the entire point.

`maintenance.conf` returns **503** for everything with `Retry-After: 60` and `X-Robots-Tag: noindex, nofollow`, using `error_page 503 /index.html` with an `internal` location to serve the page body.

### 14.2 `maintenance.py`

Run on the Docker host from the repo root.

| Command | Behaviour |
|---|---|
| `python3 maintenance.py on` | Flips the symlink to `maintenance.conf`, reloads Nginx, writes `state.json` with an ISO deadline, runs a 10-second countdown. |
| `python3 maintenance.py off` | Requires app readiness first (`require_app_readiness`), then flips back to `app.conf`. |
| `python3 maintenance.py status` | Current mode, seconds remaining, and whether the Caddy edge route is healthy. |

Safety mechanisms: an `fcntl` **operator lock** on `.maintenance.lock` (two operators cannot switch concurrently); `compose_command()` auto-detects `docker compose` vs `docker-compose`; `parse_caddy_dials` reads Caddy's admin API at `http://127.0.0.1:2019/config/` and asserts the edge actually dials `gateway:80` (`EXPECTED_EDGE_UPSTREAM`) — so a mis-adapted Caddyfile is caught *before* traffic is switched. `MaintenanceError` produces an operator-facing message with no traceback.

### 14.3 Caddy

```
{$DOMAIN}         { reverse_proxy gateway:80 }
{$LANDING_DOMAIN} { reverse_proxy gateway:80 }
```

Both domains land on the same gateway; the gateway's `Host` rules do the separation. Certificates are auto-provisioned and persisted in the `caddy_data` volume.

---

## 15. Operator tooling

### 15.1 Repo-root scripts

| Script | Runs | What it does |
|---|---|---|
| `create_company.py` | host | Prompts for company name + admin email, calls `POST /auth/companies` with the internal key, prints the one-shot activation key. |
| `list_companies.py` | host | `GET /auth/companies`. |
| `delete_company.py` | host | Lists companies, requires retyping the exact name **and** typing `PURGE`, then `DELETE /auth/companies/{id}`. Hard purge. |
| `list_leads.py` | host | `GET /owner/leads`, optional `--status`. |
| `list_users.py` | host | Runs `psql` inside the postgres container; lists users across **all** companies, optionally filtered by an email/company substring. |
| `change_password.py` | **inside `api`** | Resets a company user's *or* an auditor's password by email; hidden double prompt; disambiguates when both exist. |
| `delete_user.py` | **inside `api`** | Soft-deletes a company user. Guards the last active admin; requires retyping the email. |
| `send_email.py` | host / container | Full email CLI — see below. |
| `scripts/backfill_tb_net_debit.py` | inside `api` | Audits and backfills canonical TB signs. Dry-run by default; `--apply` writes only conventions **proven** from stored figures; an ambiguous engagement needs both `--engagement` and `--convention signed\|magnitude`, which is an explicit operator decision, not a guess. |

The host scripts parse the `.env` next to them for `API_BASE_URL` (else `DOMAIN`) and `INTERNAL_API_KEY`, then shell out to `curl`.

The container scripts share their logic with the API through `app/services/account_admin.py` — `find_accounts`, `set_password`, `soft_delete_company_user`, `purge_company` — so there is exactly one implementation. None of those helpers commit; the caller owns the transaction (`get_db` auto-commits for endpoints, scripts commit explicitly).

### 15.2 `send_email.py`

```
python send_email.py                                        # interactive wizard
python send_email.py --verify                               # handshake + auth, sends nothing
python send_email.py -t a@b.com -s "Hi" -b "Hello"
python send_email.py -t a@b.com -s "Report" -f body.txt -a report.pdf
python send_email.py … --async                              # queue through Celery
```

Flags: `-t/--to`, `-s/--subject`, `-b/--body`, `-f/--body-file`, `--html`, `--plain`, `-a/--attach` (repeatable), `--cc`, `--bcc`, `--from-email`, `--from-name`, `--async`, `--verify`, `-i/--interactive`. Without `--plain`, the body is wrapped in the branded `branded_message.html` template.

### 15.3 Migration and disaster recovery — `ops/`

| Script | Run on | What it does |
|---|---|---|
| `ops/kubera-export.sh` | source server | Produces a **verified bundle**: Postgres dump + vault tarball + `.env` + a manifest. Enters maintenance mode and stops `api`/`worker`/`beat` first (skip with `--no-maintenance` / `--keep-live`). On **any** failed exit it prints the exact command to bring the old server back — the old data is never modified or deleted. |
| `ops/kubera-import.sh` | target server | Installs Docker if needed, places the repo, restores DB + vault, starts the stack, verifies the manifest. Also the disaster-recovery restore path. `--domain` rewrites the domain; `--skip-setup`, `--keep-bundle`, `--dry-run`. |
| `ops/kubera-migrate.sh` | source server | End-to-end orchestrator: export here → ship over SSH → import there. |
| `ops/lib.sh` | — | Shared `die`/`warn`/`require_repo`/`load_env` helpers. |

All three honour `--dry-run` and are covered by `tests/test_ops_export.py`, `test_ops_import.py`, `test_ops_migrate.py`, `test_ops_lib.py`.

---

## 16. Migrations

Alembic, 42 revisions in `alembic/versions/`, applied automatically by the `api` container's start command (`alembic upgrade head && uvicorn …`). Notable ones:

| Revision | What it introduced |
|---|---|
| `f4e8f5695f21` | Phase 0 scaffolding |
| `70e5eedbe8e8` | Phase 1 — DocVault |
| `331ba914cf74` | Phase 2 — AuditEase |
| `e05b5c558dd5` | Phases 3–4 — compliance |
| `a1f2b3c4d5e6` / `b2c3d4e5f6a7` / `c3d4e5f6a7b8` | AuditEase slices 1–3 |
| `d1e2f3a4b5c6` | Fixed asset register |
| `f3a5b7c9d1e2` | Financial years and depreciation |
| `e2c4a6b8d0f1` | TB sign convention |
| `b5d8f2a6c9e1` | Multi-auditor grants |
| `b7c1d2e3f4a5` | Bucket access control |
| `e9f0a1b2c3d4` | DocVault approval system |
| `e1f2a3b4c5d6` | Partial unique email index |
| `d7e9f1a2b3c4` | Soft delete + archive |
| `c8d9e0f1a2b3` | Company hard-delete cascade |
| `c1f2e3d4a5b6` | One finalized depreciation run per FY |
| `d7a1c9b2e4f3` | `calc_trace` on depreciation lines |
| `4f6a8b0c2d1e` | Split the combined `compliance` module grant into `roc` + `secretarial` |
| `d8e9f0a1b2c3` | Remove the `manager` role, migrate to `employee` |
| `a4b5c6d7e8f9` | Leads table |
| `ddf024af58cd` | Company SMTP configs + email logs |

`asset_seed.seed_global_asset_reference_data_sync(connection)` exists specifically so a migration can install the Schedule II tree and Appendix I blocks over a plain sync `Connection`. The seed is **idempotent** — it matches on `(company_id IS NULL, code/name)` and updates in place, so re-running after a statutory rate change corrects existing rows rather than duplicating them.

Where a model declares an index that `create_all` must also produce (the partial email index, the `NULLS NOT DISTINCT` IT-block index, the finalized-run index), the declaration is deliberately mirrored in both the model and the migration so the test database matches production.

---

## 17. Testing

```
pytest.ini / [tool.pytest.ini_options]:  asyncio_mode = auto,  pythonpath = .
```

**`unit_tests/`** — the pure layers, no database: `test_depreciation.py`, `test_it_depreciation.py`, `test_trial_balance.py`, `test_group_tree.py`, `test_tb_reimport.py`, `test_mapping_import.py`, `test_calc_trace.py`, `test_calc_trace_builders.py`, `test_auditor_access.py`, `test_requirement_import.py`, `test_requirement_models.py`, `test_reporting_document.py`, `test_reporting_format.py`, `test_reporting_render.py`.

**`tests/`** — integration against a real schema built with `create_all` (`conftest.py`), covering auth and onboarding, RBAC (`test_user_role_rbac`, `test_user_access`, `test_auditease_rbac`, `test_docvault_bucket_rbac`), DocVault and approvals, compliance, assets (costing, validation, import, disposal, masters, forking, impact, reports), depreciation API, financial years, AuditEase (multi-auditor, reports, requirement submissions), leads and the owner console, the entire email stack (config, resolver, service, tasks, templates, CLI, API, models, the auditor-invite email), encryption, health, maintenance, and the three `ops/` scripts.

**Frontend** — `vitest` + Testing Library + `jsdom`, with tests co-located next to components (`*.test.tsx` / `*.test.ts`). `src/test/renderApp.tsx` mounts the real route table under a memory router, which is how the auth-guard and route-isolation tests work.

Run:

```bash
uv run pytest                    # backend, all
uv run pytest unit_tests -q      # pure layers only
cd frontend && npm test          # frontend
```
