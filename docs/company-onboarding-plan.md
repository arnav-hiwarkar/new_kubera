# Implementation Plan — Company Distribution & Onboarding

Status: approved design (grilling session 2026-07-16). Pre-launch, no tenant data to preserve.

## Overview
Change company creation into a two-step flow: operator **initializes** a company shell + pending
admin from the backend and receives a one-shot **activation key** (48h TTL); the admin **activates**
by setting their own password, then is force-routed through a **company profile** onboarding gate.
Operator can **list** and **hard-delete** companies via internal-key-gated endpoints.

---

## 1. Data model & migration

Single Alembic migration (pre-launch, simple defaults, no backfill).

### `companies` table — new columns (`app/models/company.py`)
Profile fields:
- `legal_name` `String(255)` nullable
- `cin` `String(21)` nullable
- `pan` `String(10)` nullable
- `gstin` `String(15)` nullable
- `tan` `String(10)` nullable
- `address_line1`, `address_line2`, `city`, `state` `String`, `pincode` `String(6)` nullable
- `contact_email` `String(255)` nullable, `contact_phone` `String(20)` nullable
- `date_of_incorporation` `Date` nullable
- `website` `String(255)` nullable
- `industry` `String(255)` nullable
- `logo_path` `String` nullable (points at encrypted file, same convention as docvault)
- `profile_completed` `Boolean` not null, `server_default='false'`

Activation fields (on `companies`, since key is per-company/first-admin):
- `activation_key_hash` `String(255)` nullable
- `activation_expires_at` `DateTime(timezone=True)` nullable
- `activation_used_at` `DateTime(timezone=True)` nullable

> `CompanyUser` already has `is_active` and the `__pending__` password convention — no new columns
> needed there. `full_name` server-defaults to "Unknown".

### FK cascade (required for hard delete — see §5)
Add `ondelete="CASCADE"` to every `company_id` FK across models (company_keys, company_users,
docvault, assets, sales, kra, compliance, auditease, notifications, activity_log, custom_fields, …),
OR delete app-side in dependency order inside the delete endpoint. **Decision: add DB-level
`ON DELETE CASCADE`** in the migration (`ALTER TABLE … DROP CONSTRAINT … ADD CONSTRAINT … ON DELETE CASCADE`)
— cleaner and avoids ordering bugs. The self-FK `company_users.manager_id` needs care (nullable, same table).

---

## 2. Backend endpoints (`app/routers/auth.py` unless noted)

### 2.1 Initialize company — MODIFY `POST /api/v1/auth/companies`
- Still gated by `X-Internal-API-Key`.
- Request changes to `{ name, admin_email }` (drop the `admin.password`).
- Creates `Company`, `CompanyKey` (unchanged KEK logic), and a **pending admin `CompanyUser`**:
  `hashed_password="__pending__"`, `is_active=False`, `role=admin`, `full_name` left default.
- Generate key: `secrets.token_urlsafe(24)`; store `activation_key_hash = hash_password(key)`
  (bcrypt, reuse `app/auth.hash_password`), `activation_expires_at = utcnow() + 48h`.
- Activity log `company.created` (ActorType.internal — already used at auth.py:94).
- **Response returns the plaintext key once**: `{ company, admin, activation_key, activation_expires_at }`.

### 2.2 Reissue key — NEW `POST /api/v1/auth/companies/{id}/reissue-key`
- `X-Internal-API-Key` gated. Only valid while admin is still pending (`is_active=False`).
- Mints a fresh key + new 48h window, clears `activation_used_at`. Returns plaintext key once.

### 2.3 Activate — NEW `POST /api/v1/auth/company/activate` (unauthenticated)
- Request `{ email, activation_key, password, full_name }`.
- Look up admin by email; validate: pending (`is_active=False`), key hash matches,
  `activation_expires_at > now`, not already used.
- On success: `hashed_password = hash_password(password)`, `full_name` set, `is_active=True`,
  set `activation_used_at`, null out `activation_key_hash`/`activation_expires_at` (one-shot).
- **No JWT issued.** Returns `204`/success; frontend redirects to login.
- **Generic errors**: single "Invalid or expired activation details" for all failure modes
  (wrong email, wrong key, expired, used) — no email enumeration.
- Password policy: min length 8, enforced in schema validator.

### 2.4 Company login — MODIFY `POST /api/v1/auth/company/login` (auth.py:115)
- Add `is_active` check → reject inactive/pending users with the same generic 401.
  (Today it only checks password; `__pending__` fails verify anyway, but make intent explicit.)

### 2.5 Company profile — NEW (own router or in auth.py)
- `GET /api/v1/company/profile` (auth: any company user) → returns all profile fields +
  `profile_completed` + `logo` availability. Used by the frontend onboarding gate.
- `PUT /api/v1/company/profile` (auth: `require_admin`) → update fields; validate PAN/GSTIN/CIN
  regex server-side; on save recompute `profile_completed` (all required present); write an
  `activity_log` entry per update (`company.profile_updated`).
- `POST /api/v1/company/profile/logo` (`require_admin`) → `UploadFile`, validate PNG/JPG/SVG + ≤2MB,
  store via existing `app/services/document_access.py` encrypted pipeline under the company dir,
  set `logo_path` (replace old file if present).
- `GET /api/v1/company/profile/logo` (any company user) → decrypt + stream the logo.

Required-for-completion fields: `legal_name, cin, pan, address_line1, city, state, pincode,
contact_email, contact_phone`. GSTIN/TAN/logo/etc. optional.

### 2.6 List all companies — NEW `GET /api/v1/auth/companies`
- `X-Internal-API-Key` gated. Returns all companies with status
  (`profile_completed`, admin email, `is_active`, activation pending/expired, created_at).

### 2.7 Delete company — NEW `DELETE /api/v1/auth/companies/{id}`
- `X-Internal-API-Key` gated. **Confirmation safety rail**: request body must include
  `confirm_name` that exactly matches `company.name`, else 400.
- Hard delete: rely on DB `ON DELETE CASCADE` (§1) to remove all tenant rows, then delete the
  on-disk directory `{VAULT_STORAGE_PATH}/{company_id}/` (encrypted files).
- Irreversible; log to a server-side app log before deletion.

---

## 3. Schemas (`app/schemas/auth.py` + new `app/schemas/company.py`)
- `CompanyInitRequest { name, admin_email }`, `CompanyInitResponse { company, admin, activation_key, activation_expires_at }`.
- `ActivationRequest { email, activation_key, password (min 8), full_name }`.
- `CompanyProfileOut` / `CompanyProfileUpdate` with field validators (PAN `^[A-Z]{5}[0-9]{4}[A-Z]$`,
  GSTIN 15-char pattern, CIN 21-char pattern).
- `CompanyListItem`, `CompanyDeleteRequest { confirm_name }`.
- Remove/deprecate `CompanyUserCreate.password` usage in the create path.

## 4. Security / rate-limiting
- Add a lightweight per-IP+email attempt counter for `/company/activate` and `/company/login`
  (in-memory or Redis — Redis is already configured for Celery; prefer Redis so it survives workers).
  Lock/deny after N failures for a cooldown window. Generic 429 on trip.

## 5. Key risks / notes
- **FK cascade is the critical piece** — without `ON DELETE CASCADE` (or ordered app-side deletes),
  the delete endpoint will fail on FK violations. Enumerate every model with `company_id` in the migration.
- Deleting the `CompanyKey` makes encrypted files cryptographically dead, so hard delete is genuinely final.
- `company_users.email` is globally unique — fine for activation lookup, but means an email can't be
  reused across companies. Acceptable for now.

---

## 6. Frontend (`frontend/src/`)
- **`/activate` route** (`pages/company/CompanyActivate.tsx`): email + product key → set password + full_name
  → success → redirect to `/company/login`. Link from `CompanyLogin.tsx` ("First time? Activate your account").
- **Shared profile form** (`components/company/CompanyProfileForm.tsx`) used in two modes:
  - Onboarding: rendered by a **completion gate** — after login, `GET /company/profile`; if
    `!profile_completed`, force-route to onboarding and block the rest of the app until saved.
  - Settings: admin-editable section; non-admins get read-only view.
  - zod schema mirrors backend PAN/GSTIN/CIN validation; logo upload widget (PNG/JPG/SVG ≤2MB).
- Add the profile-completion check to the company auth guard (`auth/company/`), alongside `ModuleGuard`.
- Regenerate API types: `npm run gen:api` after backend is in place.

## 7. Suggested build order
1. Migration (columns + FK cascade) + model updates.
2. Backend: init (modified) + reissue + activate + login guard. Test via curl.
3. Backend: profile GET/PUT + logo up/down.
4. Backend: list + delete (with cascade verified).
5. Rate-limiting.
6. Frontend: activate page + login link.
7. Frontend: profile form + onboarding gate + settings section.
8. `gen:api`, end-to-end test of the full flow.
