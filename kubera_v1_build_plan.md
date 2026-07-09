Kubera — V1 Backend Build Plan

**Status:** Agreed spec, post-interview. Supersedes both prior documents. Built fresh — not a continuation of the old backend. **Builders:** Antigravity (Claude Opus, Gemini 3.1 Pro). **Goal of this pass:** A working, testable backend + database (via Swagger/OpenAPI) covering docVault, AuditEase, SecretarialEase, and ROC Compliance. Asset Management, Sales Tracking, and KRA & Appraisal are explicitly **out of scope** for this pass — schema should not be designed to preclude them, but no code for them ships now.

---

## 0. Key Decisions Log

These were the open questions/conflicts between the two source documents, and how they were resolved:

|Area|Decision|
|---|---|
|Encryption key model|**Per-company KEK**, not a single global KEK. A root master KEK (env var) wraps each company's auto-generated KEK. Company KEK, encrypted under root, stored in Postgres (never plaintext). Per-document-version DEKs remain envelope-encrypted under the company's KEK — same two-layer pattern as before, one more layer added.|
|User model|Single `CompanyAdmin`-equivalent access in V1, but modeled as a full `CompanyUser` table with a `role` column (defaulting to `admin`) so multi-employee logins (needed later for KRA) don't require a schema rewrite. Only admin-role signup is exposed via API in V1.|
|V1 module scope|docVault → AuditEase → SecretarialEase → ROC Compliance. Asset Mgmt / Sales / KRA deferred entirely.|
|Non-editable document toggle|Locks versioning completely — no re-upload/new version accepted once a document is marked non-editable.|
|Document status transitions|Manual only in V1 (admin/auditor sets status by hand). No automatic overdue detection yet — `due_date_rule` field exists on ROC/Secretarial doc types for future use, but nothing computes off it yet.|
|Engagement closure|Manual — company admin explicitly closes an `AuditEngagement`. Auto-close on period end is a future enhancement.|
|Multi-auditor access|Flat — any auditor invited to an engagement has full, equal access to it. No lead/member distinction in V1.|
|Requirement requests & queries|Plain REST, poll-based. No websockets/real-time in V1.|
|Report generation|Backend supports a JSON `ReportTemplate` schema (placeholder tokens like `{{pnl_table}}`) now, but only one hardcoded default template is shipped/used in V1. The template _editor_ is future work — this just avoids a rewrite later.|
|Ledger taxonomy|Schedule III–aligned groups/sub-groups **seeded** as system defaults; companies can add their own sub-groups/sub-sub-groups on top.|
|SecretarialEase / ROC|Share one `DocumentType` + template mechanism, differentiated by a `domain` enum (`secretarial` / `roc`). Avoids duplicate models for what is functionally the same pattern.|
|Auditor signup|Hybrid — auditors can self-register an account independently (open signup), but that account has **zero engagement access** until a company explicitly invites them to a specific engagement. Invite is what grants access, not what creates the account.|
|Audit/activity log|A generic, cross-module `ActivityLog` table (actor, action, entity_type, entity_id, company_id, timestamp, metadata JSON) is built now and used by every module.|
|Notifications|A basic in-app `Notification` table (recipient, type, payload, read_at) — status changes, invites, query replies write to it. No email/SMS delivery in V1.|
|Global search|Basic search across docVault by title/tags/bucket/status (Postgres `ILIKE`/trigram — no external search engine).|
|Infra scope this pass|Full Docker Compose: `api`, `worker`, `beat`, `postgres`, `redis`. **No `nginx` yet** — that's a deployment-phase concern, not a testing-phase one.|
|Backup|Nightly Celery Beat job: `pg_dump` + tar of `/data/vault`, written to a local backup dir. Off-VM shipping left as an env-var target to fill in later. Included now since it's cheap.|
|Explicitly deferred|Rate limiting/login lockout, health-check endpoints, soft-delete outside docVault, company compliance profile fields (CIN/PAN/GST/AGM date), auditor zip-bundle download, subscription/billing, automatic overdue computation, real-time chat.|

---

## 1. Architecture Principles

- **Monolith, modular routers.** One FastAPI app, one Postgres database. Routers namespaced per module: `/api/v1/docvault`, `/api/v1/auditease`, `/api/v1/secretarial`, `/api/v1/roc`.
- **Multi-tenant, shared tables.** Every company-owned table carries `company_id` FK. `TenantScopedMixin` base model + a `get_tenant_scope` dependency injects the `company_id` filter automatically from the authenticated principal. **This is the highest-risk area** — every module ships with a cross-tenant-leak boundary test.
- **Async everywhere.** SQLAlchemy 2.0 async engine, `asyncpg`, async handlers throughout.
- **Background jobs via Celery + Redis.** File encryption/decryption on upload, PDF/report generation, xlsx export, nightly backup.
- **Deployment (this pass).** Docker Compose: `api`, `worker`, `beat`, `postgres`, `redis`. No `nginx`, no TLS termination yet — local/testing only.

---

## 2. Auth Architecture

Two fully separate identity systems — different tables, different login flows, different JWT issuer scope (`principal_type` claim distinguishes them; tokens are never valid cross-system).

### 2.1 Company side

- `Company`: profile, one row per client. Created internally only (Kubera team, via an API-key-protected internal endpoint or CLI seed — no public self-serve signup).
- `CompanyUser`: id, company_id, email, hashed_password, `role` (enum, default `admin`), timestamps. V1 only ever creates/exposes `admin`-role users via the public API — table is shaped for future roles without a migration.
- On company creation: a per-company KEK is generated, wrapped under the root master KEK (env), and stored (encrypted) alongside the company row or in a dedicated `CompanyKey` table.
- JWT access + refresh for `CompanyUser` login.

### 2.2 Auditor side

- `Auditor`: independent identity. **Open self-registration** — anyone can create an auditor account (email/password) directly. This account has no engagement access on its own.
- `AuditEngagement` grants access. A `CompanyUser` invites an auditor (by email) to a specific engagement:
    - If no `Auditor` account exists for that email → invite link lets them set a password, creating the account, immediately linked to that engagement.
    - If an account already exists → the invite just adds a new engagement grant (`AuditorEngagementGrant`: auditor_id, engagement_id, status, invited_at, accepted_at).
- Engagement-scoped access only — no standing/global access to a company. Within an assigned, active engagement, an auditor has full access (no per-ledger sub-scoping; no lead/member distinction — see §0).
- Engagement closure is manual (company admin action). On closure, existing grants for that engagement become inactive; historical data stays queryable by the company, not by the auditor.

---

## 3. docVault (Phase 1 — build first)

Central document store. Every other module writes into this rather than handling its own storage.

### 3.1 Data model

- `Document`: id, company_id, current_version_id, bucket_id (nullable), status, title, doc_type_id (nullable — set by SecretarialEase/ROC), tags (array), is_editable (bool, default true), created_by, timestamps.
- `DocumentVersion`: id, document_id, storage_path (random UUID filename), original_filename, mime_type, size_bytes, checksum, encrypted_dek, uploaded_by, uploaded_at, version_number.
- `Bucket`: id, company_id, name, created_by.
- `DocumentAccessOverride`: document_id, principal (user or auditor), permission level — used specifically to grant auditors access to individual documents attached via requirement requests/queries (see §4.6), not for general ACLs.
- Status enum (shared base): `uploaded`, `pending_approval`, `action_required`, `verified`, `submitted`, `overdue`, `archived`. Manual transitions only in V1.

### 3.2 Storage layout

- `/data/vault/{company_id}/{uuid}.enc` — flat per-company folder, fully randomized filenames. All human-readable metadata lives only in Postgres.

### 3.3 Encryption

- Root master KEK (env, never in DB) wraps each company's KEK (`CompanyKey`, encrypted at rest).
- Each `DocumentVersion` gets its own DEK, AES-256-GCM, encrypted under the company's KEK.
- Decrypt-on-read only — file is decrypted into memory/short-lived stream when served to an authorized request; never persisted unencrypted.

### 3.4 Versioning

- Re-upload creates a new immutable `DocumentVersion`; `Document.current_version_id` advances. Old versions remain retrievable. If `Document.is_editable = false`, re-upload is rejected outright.

### 3.5 Search

- `GET /docvault/documents/search?q=` — matches title, tags, bucket name, status via Postgres `ILIKE`/trigram index. No external search engine.

### 3.6 Endpoints

- `POST/GET/DELETE /docvault/buckets`
- `POST /docvault/documents` (upload, multipart, optional bucket_id, is_editable flag)
- `POST /docvault/documents/{id}/versions` (re-upload; 409 if not editable)
- `GET /docvault/documents` (filter: bucket, status, tag, doc_type)
- `GET /docvault/documents/search`
- `GET /docvault/documents/{id}`, `GET /docvault/documents/{id}/download`, `GET /docvault/documents/{id}/versions`
- `PATCH /docvault/documents/{id}` (status, bucket, tags, is_editable)
- `DELETE /docvault/documents/{id}` (soft delete → archived)

### 3.7 Backup (infra task within this phase)

- Nightly Celery Beat job: `pg_dump` + tar `/data/vault` → local backup dir. Destination is an env var (one-line change to point off-VM later).

---

## 4. AuditEase (Phase 2)

Depends on: docVault, Auditor auth (§2.2).

### 4.1 Trial Balance import

- Flexible column-mapping importer: any xlsx/csv, any sheet, any starting row, user maps source columns → `ledger_code` (optional), `ledger_name`, `opening_balance`, `debit`, `credit`, `closing_balance`.
- On import: check `sum(debit) == sum(credit)` across the sheet — mismatch is a **warning**, not a block; import proceeds either way.

### 4.2 Ledger group taxonomy

- Four hardcoded top-level groups: Asset, Liability, Income, Expenditure.
- Schedule III–aligned sub-groups **seeded** as system defaults (e.g. Share Capital, Reserves & Surplus, Current Liabilities, Revenue from Operations, etc.).
- Companies can add their own custom sub-groups and optional sub-sub-groups on top of the seed data. One combined `LedgerGroup` table (self-referencing parent_id, up to 3 levels: group → sub-group → sub-sub-group), with a `has_children` flag driving whether the UI/API requires a further selection.
- `POST /auditease/ledgers/{id}/map-group` assigns/reassigns/removes a ledger's group mapping.

### 4.3 Audit engagements

- `AuditEngagement`: company_id, period label, status (`invited`, `active`, `closed`), created_by, timestamps. Closure is manual (§2.2).
- `AuditorEngagementGrant`: auditor_id, engagement_id, status, invited_at, accepted_at.

### 4.4 Audit entries

- `AuditEntry`: engagement_id, created_by (auditor), code, description, status (`proposed`, `approved`, `rejected`), timestamps.
- `AuditEntryLine`: entry_id, ledger_id, side (`debit`/`credit`), amount. Generic list-of-lines model covers 1:1, 1:many, and many:many without special-casing by type. All ledgers in one entry must be distinct.
- Validation (app layer): entry can only be submitted if `sum(debit lines) == sum(credit lines)`.
- Approval: company admin approves/rejects with optional comment. Modeled as a generic single-step approval table now, extensible to multi-step later without a schema rewrite.

### 4.5 Statement generation

- PnL and Balance Sheet auto-generated (Schedule III format) from ledger-group mappings + approved entries.
- `ReportTemplate` entity (JSON, placeholder tokens) exists in the schema now; V1 ships and uses exactly one hardcoded default template — no template editor yet.
- Annual report = PnL + BS + Notes-to-Accounts placeholder, exported as PDF, stored back into docVault under a dedicated "Final Reports" bucket.

### 4.6 Requirement requests & queries

- `RequirementRequest`: engagement_id, raised_by (auditor), description, status (`open`, `fulfilled`), fulfilled_document_id (nullable, FK to docVault Document, set when company attaches a doc). Attaching a document here creates a `DocumentAccessOverride` grant scoped to that auditor/engagement — auditors never get general docVault access.
- `Query`: engagement_id, opened_by, status (`open`, `closed`).
- `QueryMessage`: query_id, sender (company or auditor), text, attached_document_id (nullable, same access-override pattern as above). Chat-style thread, REST + polling (`GET /auditease/engagements/{id}/queries/{qid}/messages`).

### 4.7 Endpoints

- `POST/PUT /auditease/trial-balance/import`, `GET /auditease/trial-balance`
- `POST /auditease/ledgers/{id}/map-group`
- `POST /auditease/engagements`, `GET /auditease/engagements`, `GET /auditease/engagements/{id}`, `PATCH /auditease/engagements/{id}/close`
- `POST /auditease/engagements/{id}/invite-auditor`
- `POST /auditease/engagements/{id}/entries` (auditor), `PATCH /auditease/entries/{id}/approve|reject` (admin)
- `POST/GET /auditease/engagements/{id}/requirement-requests`, `PATCH .../{req_id}/fulfill`
- `POST/GET /auditease/engagements/{id}/queries`, `POST/GET .../{qid}/messages`, `PATCH .../{qid}/close`
- `POST /auditease/engagements/{id}/generate-statements`, `GET .../statements`
- `POST /auditease/engagements/{id}/generate-annual-report`

Auditor-side mirror under `/api/v1/auditor/engagements/...` for the same operations, scoped to the auditor's own grants.

---

## 5. SecretarialEase & ROC Compliance (Phases 3–4, shared mechanism)

Depends on: docVault. Both modules are thin layers over the same pattern, split by a `domain` field — not separate tables.

### 5.1 Data model

- `DocumentType`: company_id (nullable = system-shipped base type), domain (`secretarial` | `roc`), name, template_file_id (docVault reference), metadata_schema (JSON — configurable fields, e.g. MoM requires meeting_date, attendees, resolutions), due_date_rule (string, e.g. "30 days from AGM date" — stored, **not** computed against in V1).
- Seeded base types:
    - Secretarial: Minutes of Meeting, Board Resolution, general Directorial Meeting record.
    - ROC: AOC-4, MGT-7, ADT-1, DIR-12, DPT-3.
- Companies can create additional custom types in either domain (own template + own metadata schema).
- `MeetingRecord`: company_id, doc_type_id, structured metadata (per schema), linked docVault document. Used for both secretarial records and ROC filings (name is a holdover — functionally a "typed record," domain distinguishes them).

### 5.2 Flow

- Create/select a `DocumentType` → download its template → fill offline → upload → stored in docVault, auto-tagged/bucketed by type/domain, linked via `MeetingRecord`.

### 5.3 Endpoints

- `POST/GET /secretarial/document-types`, `PUT/DELETE /secretarial/document-types/{id}`
- `POST/GET /secretarial/meeting-records`
- `POST/GET /roc/document-types`, `PUT/DELETE /roc/document-types/{id}`
- `POST/GET /roc/meeting-records`

(Both sets hit the same underlying service/table with `domain` fixed by the router — kept as separate route prefixes for clarity in Swagger, not separate implementations.)

---

## 6. Cross-cutting: Activity Log & Notifications

Built once in Phase 0, used by every module from Phase 1 onward.

- `ActivityLog`: id, company_id, actor_type (`company_user` | `auditor` | `internal`), actor_id, action (string, e.g. `document.uploaded`, `entry.approved`), entity_type, entity_id, metadata (JSON), created_at. Every state-changing endpoint writes one row here. No UI/query endpoints beyond a basic `GET /activity-log?entity_type=&entity_id=` in V1.
- `Notification`: id, recipient_type, recipient_id, type, payload (JSON), read_at (nullable), created_at. Written on: status changes, engagement invites, query replies, requirement-request fulfillment. In-app only — `GET /notifications`, `PATCH /notifications/{id}/read`. No email/SMS delivery in V1.

---

## 7. Build Sequence

|Phase|Module|New infra introduced|
|---|---|---|
|0|Scaffolding|Docker Compose (api, worker, beat, postgres, redis), async SQLAlchemy base, `TenantScopedMixin` + scoping dependency, root KEK + per-company KEK generation, `CompanyUser` + `Auditor` auth, `ActivityLog`, `Notification`|
|1|docVault|Envelope encryption (2-layer), versioning, buckets, search, backup job|
|2|AuditEase|Auditor invite/grant system, flexible TB importer, seeded Schedule III taxonomy, double-entry validation, `ReportTemplate` schema + default template, requirement requests, query threads|
|3|SecretarialEase|`DocumentType` + `metadata_schema` pattern, seed data|
|4|ROC Compliance|Reuses `DocumentType` pattern (domain=`roc`), seeded ROC form types, `due_date_rule` field (unused for now)|

Each phase ships with: Alembic migration(s), pytest coverage for the happy path + a cross-tenant-leak boundary test, and full Swagger/OpenAPI docs.

## 8. Explicitly Out of Scope for This Pass

Asset Management, Sales Tracking, KRA & Appraisal, `nginx`/TLS/deployment, subscription & billing, real-time (websocket) chat, automatic overdue computation, rate limiting/login lockout, health-check endpoints, soft-delete outside docVault, company compliance profile fields (CIN/PAN/GST/AGM date), auditor zip-bundle export. None of these are precluded by the schema above — they're deferred, not designed against.
