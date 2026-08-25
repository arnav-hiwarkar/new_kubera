# Multi-Auditor Engagements — Design

**Date:** 2026-08-25
**Module:** AuditEase
**Status:** Approved, ready for planning

## Problem

An AuditEase engagement supports exactly one auditor. Inviting a new auditor silently
revokes the previous one (`invite-auditor` bulk-revokes grants), the response schema
carries singular `auditor_email`/`auditor_grant_status` fields, and the UI copy assumes
replacement. Real audits have teams: a senior reviewing entries, a junior raising
requirement requests, a specialist who should only see the trial balance.

The single-auditor limit is endpoint logic, not schema — `AuditorEngagementGrant` is
already many-to-many capable. Separately, no engagement action is written to
`activity_logs` today, so there is no per-auditor history even though the logging
infrastructure (`ActorType.auditor`) exists.

## Goal

Multiple auditors per engagement with:

1. The existing single-auditor protocol preserved per auditor: access only while the
   engagement is active, access lost on close/removal, past work always visible to the
   company.
2. Per-area access control — each auditor can be limited to specific parts of
   AuditEase (trial balance, entries, requirements, queries, documents).
3. An **Auditors tab** on the company engagement workspace: list auditors, inspect each
   one's time-by-time activity log, export it as PDF/Excel, invite/remove auditors,
   and edit their area access.
4. Proper authorization on both frontend and server for every new surface.

## Decisions made during brainstorming

- **Per-area on/off toggles** (not read/write levels, not preset roles).
- **Full access by default** on invite; the company trims areas afterward if needed.
- Activity log captures **workspace actions + access events**.
- Activity report exports as **PDF + Excel**, reusing the reporting stack.
- **Admin/manager only** can manage auditors; other module users view read-only.
- Auditors on an engagement share one workspace — everyone sees all entries,
  requirements, and queries regardless of author.

## Approach

Permissions live as a JSONB map on `AuditorEngagementGrant`. This mirrors
`CompanyUser.accessible_modules` (already a JSONB list in this codebase), requires no
new tables, and keeps all multi-auditor behavior in the grant row. A normalized
per-(grant, area) table was considered and rejected: six fixed booleans don't justify
the joins.

## Data model

### AuditorEngagementGrant (app/models/auditease.py)

- Add `area_permissions`: JSONB, NOT NULL, server-default = full-access map:
  `{"trial_balance": true, "entries": true, "requirements": true, "queries": true,
  "documents": true}`. Existing rows are backfilled by the default — current behavior
  is preserved exactly.
- Add unique constraint on `(auditor_id, engagement_id)`.

### Grant lifecycle

Statuses stay `invited → accepted → revoked`, with these changes:

- **Invite adds** instead of replaces. The bulk-revoke logic in `invite-auditor`
  is deleted.
- Inviting an email whose prior grant is `revoked` **resurrects that same row**
  (status back to `invited`, `accepted_at` cleared, permissions reset to full access
  unless the invite payload specifies areas). This keeps the unique constraint intact
  while allowing re-invite after removal.
- **Remove** sets status `revoked`. Nothing the auditor created is deleted or
  anonymized — `AuditEntry.created_by`, requirement requests, queries keep pointing at
  the auditor and remain visible to the company forever.
- **Close** keeps its existing bulk-revoke of all grants and pending-invite cleanup.
  Irreversible, unchanged.

### ActivityLog (app/models/activity_log.py)

- Add nullable indexed `engagement_id` column. The existing `entity_id` points at the
  target entity (e.g. an entry ID); engagement-scoped filtering needs its own column.

### PendingAuditorInvite

Unchanged. Registration still auto-converts matching invites into full-access grants.

## Access control

### Server side (authoritative)

- `check_auditor_access()` (app/routers/auditor_engagements.py) becomes a dependency
  factory taking an optional area: `check_auditor_access(area="entries")`. Rules:
  grant live (`invited`/`accepted`) AND engagement `active` AND — when an area is
  given — that area enabled in `area_permissions`.
- Every auditor endpoint declares its area:

| Endpoint group | Area gate |
|---|---|
| Trial balance view | `trial_balance` |
| Entries create/list/delete | `entries` |
| Requirement requests | `requirements` |
| Queries open/reply/close | `queries` |
| Document get/download | `documents` |

- Accept and engagement listing need no area.
- Document downloads already require a live grant via
  `auditor_can_access_document()` (app/services/document_access.py) — this generalizes
  to multiple grants without change.
- Company-side mutation endpoints (invite, update permissions, remove) get
  `Depends(require_manager_or_admin)`. Read endpoints (list auditors, activity,
  report export) stay available to any company user with module access.
- Existing engagement CRUD/report endpoints are not touched — no unrelated permission
  refactoring in this feature.

A disabled area returns `403` with message "Your access to <Area> was removed by the
company." Revoked auditors fail every check immediately, including downloads.

### Frontend (mirror, never the only gate)

- Auditors tab: mutation buttons render only for `admin`/`manager`; read-only users
  see list, timeline, and export controls.
- Auditor workspace: tabs for disabled areas are hidden; direct API calls still hit
  server checks.
- Existing `ModuleGuard` and the separate company/auditor token namespaces unchanged.

## API surface

New endpoints under `/api/v1/auditease/engagements/{engagement_id}/auditors`:

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/` | List grants hydrated with name/email/status/areas/timestamps; unregistered invites marked pending | any company user |
| POST | `/invite` | `{email, area_permissions?}`, defaults full access | manager/admin |
| PATCH | `/{auditor_id}` | Update `area_permissions` only | manager/admin |
| DELETE | `/{auditor_id}` | Revoke grant | manager/admin |
| GET | `/{auditor_id}/activity` | Paginated log (`?limit=&offset=`) | any company user |
| GET | `/{auditor_id}/activity-report` | `?format=xlsx\|pdf` via reporting stack | any company user |

`POST /invite-auditor` (single-auditor version) is removed; the frontend ships in the
same change.

**Breaking response change:** `AuditEngagementResponse.auditor_email` /
`auditor_grant_status` are replaced by an `auditors` array of
`{auditor_id, name, email, status, area_permissions, invited_at, accepted_at}`.
The engagements list page shows auditor names/count.

## Activity logging

First writers in this domain, using the existing `log_activity` service:

| Event | Actor |
|---|---|
| `auditor.invited` | company user |
| `auditor.grant_accepted` | auditor |
| `auditor.permissions_updated` | company user |
| `auditor.access_revoked` | company user |
| `engagement.closed` (one row, metadata lists all revoked auditor ids) | company user |
| `entry.created` / `entry.deleted` | auditor |
| `requirement.raised` / `requirement.deleted` | auditor |
| `query.opened` / `query.replied` / `query.closed` | auditor |
| `document.downloaded` | auditor |

Each row records actor type/id, action, target entity type/id, and the new
`engagement_id`.

The report builder filters `ActivityLog` by `engagement_id` + actor and renders a
time-by-time table (timestamp, action, entity summary) using the existing workbook/PDF
services — same pipeline as the financial reports.

## Frontend

### Auditors tab (company EngagementWorkspace)

- New tab alongside overview/trial-balance/mapping/entries/requirements/queries/reports.
- Table: name, email, status badge (`invited` / `accepted` / `revoked`, plus
  pending-registration marker), area chips, accepted date.
- Row actions (manager/admin): **Edit access** modal with the five area toggles;
  **Remove** with confirm dialog stating past work stays visible.
- Expandable per-auditor activity timeline + Export PDF / Excel buttons.
- Invite modal extends `InviteAuditorModal`: email + five pre-checked area checkboxes;
  the "inviting replaces the current auditor" copy is removed.

### Shared workspace attribution

Entries, requirements, and query threads display creator names — teammates' names for
auditors, full attribution for the company.

## Error handling & edge cases

| Case | Behavior |
|---|---|
| Invite while engagement closed | 409 (existing rule) |
| Duplicate live grant for same auditor | 400 |
| Duplicate pending invite (unregistered email) | 409 "invite already pending" |
| Remove last/only auditor | Allowed; engagement continues with zero auditors |
| Permission change mid-session | Enforced on next request; UI surfaces the 403 message |
| Close | Revokes all grants, logs one `engagement.closed` event naming every revoked auditor, deletes pending invites |
| Re-invite after removal | Resurrects the revoked row; constraint safe |
| Cross-tenant requests | All new endpoints resolve engagement via `_get_owned_engagement` |

## Testing

- Update `test_engagement_lifecycle` (tests/test_auditease.py): replacement assertions
  become multi-auditor assertions.
- New API tests:
  - Multi-invite leaves existing grants untouched; unique constraint holds.
  - Area enforcement returns 403 for each disabled area across all five endpoint groups.
  - Remove → re-invite cycle resurrects the same grant.
  - Role gating: employee forbidden on mutations, manager allowed; read open.
  - Each wired event produces an activity row with correct actor and engagement_id.
  - Activity report xlsx/pdf export smoke tests.
  - Cross-tenant isolation on all new endpoints.
- Frontend verified manually: hidden tabs, role-gated buttons, creator attribution.

## Out of scope

- Read/write level distinctions within an area.
- Configurable company-level permission templates.
- Auditor-side views of other auditors' logs.
- Retroactive activity data (logging starts with this feature).
