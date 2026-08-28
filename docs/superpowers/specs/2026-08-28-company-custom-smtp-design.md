# Company Custom SMTP, Auditor Invite Emailing & Email Audit Logs Design Spec

## Overview
This specification details the architecture, design, and security model for enabling multi-tenant custom SMTP configurations per company in Kubera. It allows company administrators to configure and live-test their own email server credentials (e.g. Google Workspace, Office 365, Zoho, custom mail server) with enterprise-grade AES-256-GCM envelope encryption. When auditors are invited to audit engagements, onboarding emails are dispatched using the company's custom email (or automatically falling back to central `kubera@ethdc.in`), with complete delivery audit tracking recorded in `email_logs`.

---

## 1. Zero-Trust Security & Envelope Encryption

### Encryption Scheme
* Sensitive company SMTP credentials (`smtp_password`) are encrypted at rest using AES-256-GCM.
* Encryption Hierarchy:
  * `ROOT_MASTER_KEK` (32 bytes hex in `.env`) decrypts tenant's `CompanyKey.encrypted_kek` $\rightarrow$ derives `company_kek`.
  * `company_kek` encrypts `smtp_password` with a unique 12-byte random nonce $\rightarrow$ stores `(encrypted_password, password_nonce)`.
* **Zero Leakage**:
  * `GET` APIs never return the decrypted password, password hashes, or keys (only `has_password: bool`).
  * Server logs automatically scrub credentials.
* **Server Migration Resilience**:
  * Because encryption keys reside in PostgreSQL under `ROOT_MASTER_KEK`, database dumps and server migrations (`ops/migrate.py`) preserve all company SMTP configurations without re-keying.

---

## 2. Database Models & Schema

### `company_smtp_configs` Table (`CompanySmtpConfig` Model in `app/models/company.py` or `company_smtp.py`)
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | Primary Key, default `uuid4` | Unique ID |
| `company_id` | `UUID` | FK to `companies.id`, unique, cascade delete | Tenant company |
| `host` | `String(255)` | Not Null | Mail server hostname |
| `port` | `Integer` | Not Null, default `587` | Port (587, 465, etc.) |
| `user` | `String(255)` | Not Null | Mailbox username / login |
| `encrypted_password` | `LargeBinary` | Not Null | AES-256-GCM ciphertext |
| `password_nonce` | `LargeBinary` | Not Null | 12-byte encryption nonce |
| `use_tls` | `Boolean` | Not Null, default `True` | STARTTLS toggle |
| `use_ssl` | `Boolean` | Not Null, default `False` | Direct SSL toggle |
| `from_email` | `String(255)` | Not Null | Sender email address |
| `from_name` | `String(255)` | Not Null | Sender display name |
| `is_active` | `Boolean` | Not Null, default `True` | Active status flag |
| `last_tested_at` | `DateTime(UTC)` | Nullable | Last successful test timestamp |
| `created_at` / `updated_at`| `DateTime(UTC)` | Not Null | Timestamps |

### `email_logs` Table (`EmailLog` Model)
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | Primary Key, default `uuid4` | Unique Log ID |
| `company_id` | `UUID` | Nullable, index | Associated company (if any) |
| `sender_email` | `String(255)` | Not Null | Sender email address |
| `sender_name` | `String(255)` | Not Null | Sender display name |
| `recipient_email` | `String(255)` | Not Null | Recipient email address |
| `subject` | `String(500)` | Not Null | Subject line |
| `template_name` | `String(100)` | Not Null | Template used |
| `status` | `String(50)` | Not Null | `"sent"`, `"failed"`, `"queued"` |
| `message_id` | `String(255)` | Nullable | RFC Message-ID |
| `error_message` | `Text` | Nullable | Error details if failed |
| `duration_ms` | `Float` | Nullable | Network latency in ms |
| `source` | `String(100)` | Not Null | Event source (e.g. `"auditease.invite"`, `"cli"`) |
| `created_at` | `DateTime(UTC)` | Not Null | Timestamp |

---

## 3. Resolver Service Layer (`app/services/email/resolver.py`)

* **`get_email_config_for_company(db: AsyncSession, company_id: uuid.UUID) -> Optional[EmailConfig]`**:
  * Loads active `CompanySmtpConfig` and `CompanyKey`.
  * Decrypts password using `company_kek`.
  * Returns `EmailConfig(...)` instance. Returns `None` if unconfigured/inactive.
* **`get_email_service_for_company(db: AsyncSession, company_id: uuid.UUID) -> EmailService`**:
  * Returns `EmailService(config=custom_config)` if configured, or default `EmailService()` (`kubera@ethdc.in`) if unconfigured.
* **`log_email_dispatch(...)`**:
  * Asynchronously records entry in `email_logs`.

---

## 4. REST API Endpoints

All endpoints require Company User authentication with `admin` role:

* **`GET /api/v1/company/smtp`**:
  * Returns `CompanySmtpConfigOut`: `{ configured: bool, host: str, port: int, user: str, from_email: str, from_name: str, use_tls: bool, use_ssl: bool, is_active: bool, has_password: bool, last_tested_at: str }`
* **`PUT /api/v1/company/smtp`**:
  * Body `CompanySmtpConfigUpdate`: updates settings and encrypts new password under tenant KEK if provided.
* **`POST /api/v1/company/smtp/verify`**:
  * Body `CompanySmtpVerifyRequest`: verifies connection (with provided payload or existing saved settings), returns latency and handshake status.
* **`DELETE /api/v1/company/smtp`**:
  * Deletes custom config row, reverting company to central server mail `kubera@ethdc.in`.
* **`GET /api/v1/company/smtp/logs`**:
  * Paginated list of sent email logs for the company.

---

## 5. Auditor Invite Workflow & Email Templating

### Workflow in `POST /api/v1/auditease/engagements/{id}/auditors/invite`:
1. Creates `AuditorEngagementGrant` (or `PendingAuditorInvite`).
2. Checks if auditor email is already registered in `auditors` table.
3. Builds invite URL:
   * **Unregistered**: `https://<DOMAIN>/auditor/register?email=<email>`
   * **Registered**: `https://<DOMAIN>/auditor/login`
4. Resolves email transport: calls `get_email_config_for_company(db, current_user.company_id)`.
5. Dispatches `send_auditor_invite_email_async` via Celery.
6. Records dispatch in `email_logs`.

### Template: `app/services/email/templates/auditor_invite.html`
* Clean, responsive layout with company name, period label, action button, and security disclaimer.

---

## 6. Frontend UI Components

* **`frontend/src/pages/company/settings/CompanySmtpCard.tsx`**:
  * Displayed inside Company Profile Settings.
  * Status badge indicating whether custom SMTP is active or system default is in use.
  * Form inputs for Host, Port, Encryption (TLS/SSL), User, Password, From Email, From Name.
  * Buttons for **Test Connection**, **Save Settings**, and **Reset to Default**.
* **`frontend/src/api/endpoints/companySmtp.ts` & hooks**:
  * API client for fetching, saving, testing, and resetting SMTP settings.

---

## 7. Security, Auth & Anti-Test Specifications

### Security Tests
* RBAC: Employee role and auditors rejected with `403 Forbidden` on all SMTP endpoints.
* Tenant Isolation: Company A cannot read/modify/test Company B's SMTP settings.
* Password Protection: GET responses never expose password or cipher bytes.
* Tamper Tag Verification: Ciphertext modification causes AES-GCM decryption failure.
* Non-blocking Invite: SMTP downtime never rolls back DB grants; failures are logged to `email_logs`.
