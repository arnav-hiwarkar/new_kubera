# AuditEase Requirements Lifecycle — Design

Date: 2026-08-26
Status: Approved (pending implementation plan)

## Context

Today an auditor requirement (`requirement_requests`) is just a title/description with a two-state
lifecycle (`open` → `fulfilled`): the company links one DocVault document and the engagement is done.
There is no acceptance review, no way to ask for clarification, no metadata (priority, due date,
entity, responsible person, period), no parent/child grouping, and no bulk creation. Real statutory
audit requirement lists (see `ETHDC_Requirement list M26_v1.xlsx`) need all of this.

This design upgrades requirements into a reviewed submission lifecycle with rich optional metadata,
progressive-disclosure creation UI, linked queries, company-side ETA commitments, an animated
progress overview, and Excel bulk import.

## Goals

- Mandatory fields per requirement: **Requirement ID** (auto-generated `REQ-001` style),
  **Requirement** text, **Status**.
- Statuses: `pending`, `submitted`, `clarification_needed`, `accepted`. "Reject" = mark
  clarification needed; loop repeats until accepted.
- Company can always respond with typed text **and/or** a DocVault document; auditor-set expected
  format is a hint, not a constraint.
- Optional metadata via advanced options on create: additional details, period from/to, entity,
  responsible person, expected format, auditor notes, parent requirement.
- Priority (1–5) visible on the create form by default, defaulting to 1. Due date also visible by
  default, optional, unset by default.
- Auditor can initiate a query directly from any requirement (small button with enlarging hover
  animation); queries link back to their requirement.
- Bulk import of requirements via a simple Excel template (all-or-nothing validation). Attachments
  are not part of bulk import; they are handled later per requirement as usual.
- Company can set an **ETA** ("expected to arrive / complete by") per open requirement; both sides
  see it.
- Both tabs show completed vs pending progress with modern animated UI.

## Non-goals

- No SLA automation, reminders, or escalation rules (due dates/ETAs are display + overdue
  highlighting only).
- No attachments in the Excel template or import flow.
- No change to notification infrastructure beyond new activity events feeding existing systems.
- No per-company entity master data management (entity is free text with suggestions).

## Data model

### `requirement_requests` (existing table, new columns)

| Column | Type | Notes |
|---|---|---|
| `seq_number` | int, not null | Per-engagement counter assigned at insert; display ID = `REQ-{seq:03d}` |
| `priority` | int, not null, server_default 1 | Check constraint between 1 and 5 |
| `due_date` | date, nullable | Set by auditor |
| `company_eta` | date, nullable | Set by company ("expected by") |
| `additional_details` | text, nullable | |
| `period_from` | date, nullable | |
| `period_to` | date, nullable | |
| `entity` | varchar(255), nullable | Free text |
| `responsible_person_id` | UUID, nullable, FK → `company_users.id` | SET NULL on user delete |
| `expected_format` | enum(`text`,`file`,`any`), not null, default `any` | Hint shown to company |
| `auditor_notes` | text, nullable | Visible to auditors only |
| `parent_requirement_id` | UUID, nullable, self-FK | Child requests; deleting a requirement that has children is blocked (400) |
| `clarification_note` | text, nullable | Why status is `clarification_needed`; cleared on resubmit |

### `RequestStatus` enum

Replaces `open` / `fulfilled` with: `pending`, `submitted`, `clarification_needed`, `accepted`.

Migration remaps existing rows: `open → pending`, `fulfilled → accepted`. Each previously fulfilled
requirement's linked document becomes its first `requirement_responses` row so response history
starts complete. Alembic revision alters the Postgres enum type (new type + cast or value-add
strategy per current setup) alongside the column/table additions above.

### `requirement_responses` (new table)

| Column | Type |
|---|---|
| `id` | UUID PK |
| `requirement_id` | UUID FK → `requirement_requests.id`, CASCADE |
| `responded_by` | UUID FK → `company_users.id` |
| `text_answer` | text, nullable |
| `document_id` | UUID FK → DocVault `documents.id`, nullable, SET NULL |
| `created_at` | timestamp |

Append-only. At least one of `text_answer` / `document_id` must be present. Submitting a response to
a document-bearing requirement inserts the same `DocumentAccessOverride` grant for the raising
auditor that fulfillment does today (extended to all auditors with `requirements` area access).

### `queries` (existing table)

Add nullable `requirement_id` FK → `requirement_requests.id` (SET NULL on requirement delete).
No other query changes.

## Status lifecycle

```
pending ──respond──▶ submitted ──accept──▶ accepted (terminal)
   ▲                    │  ▲
   │              clarify│  │resubmit (new response row,
   └────────────────────┘  │clarification_note cleared)
           clarification_needed
```

- `pending → submitted`: company responds (text and/or document). Always allowed regardless of
  `expected_format`.
- `submitted → clarification_needed`: any auditor with `requirements` area access; sets
  `clarification_note` (optional but encouraged).
- `clarification_needed → submitted`: company resubmits; note cleared; append new response row.
- `submitted → accepted`: any auditor with `requirements` area access accepts the latest response;
  terminal; requirement locks against edits and further responses.
- Shared-workspace rule holds: all auditors see everything; edit/delete remain restricted to the
  requirement's creator (`raised_by`) and only while `pending`.

## API surface

All auditor routes remain under `/api/v1/auditor/engagements/{engagement_id}` gated by
`check_auditor_access(..., area="requirements")`; company routes under `/api/v1/auditease/engagements/{engagement_id}`
with manager/admin dependency.

### Auditor

- `POST /requirement-requests` — extended body: `requirement` (text, required), plus optional
  `priority` (1–5, default 1), `due_date`, `additional_details`, `period_from`, `period_to`,
  `entity`, `responsible_person_id`, `expected_format`, `auditor_notes`,
  `parent_requirement_id`. Server assigns `seq_number` (max+1 within transaction) and returns the
  created record including computed `requirement_id` string.
- `PUT /requirement-requests/{req_id}` — owner only; optional metadata editable until `accepted`;
  mandatory requirement text editable only while `pending`.
- `DELETE /requirement-requests/{req_id}` — owner only; only while `pending`.
- `POST /requirement-requests/{req_id}/review` — body `{action: "accept"|"clarify", note?}`;
  `accept` valid only from `submitted`; `clarify` valid from `pending` or `submitted` (pre-flagging
  before anything arrives is allowed) — both set the status per the lifecycle above.
- `GET /requirement-requests/import-template` — streams styled xlsx template (header row +
  instructions sheet + example row), mirroring `asset_import.build_template_xlsx()`.
- `POST /requirement-requests/import` — multipart xlsx upload. Validates every row first;
  all-or-nothing. On failure: 422 with per-row error list. On success: creates all rows in file
  order (sequential seq numbers), logs one activity event, returns summary counts.

### Company

- `GET /requirement-requests` — extended response schema: all new fields plus `latest_response`
  and `responses[]` history.
- `POST /requirement-requests/{req_id}/respond` — JSON body `{text_answer?, document_id?}` (at
  least one). Allowed from `pending` / `clarification_needed`. Sets status `submitted`.
- `PATCH /requirement-requests/{req_id}/eta` — body `{company_eta: date|null}`; allowed while
  status is not `accepted`; company users only.

### Activity events

New events feed the existing activity report: `requirement.submitted`,
`requirement.clarification`, `requirement.accepted`, `requirement.bulk_imported`,
`requirement.eta_set`. Existing `requirement.raised` / `requirement.deleted` unchanged.

## Bulk Excel format

Single sheet, header row exactly:

```
Requirement* | Additional Details | Period From | Period To | Entity | Priority |
Due Date | Responsible Person Email | Expected Format | Auditor Notes | Parent Requirement ID
```

Rules:

- Dates ISO `YYYY-MM-DD`; blank allowed except Requirement.
- Priority: integer 1–5, blank → 1.
- Expected Format: `text` | `file` | `any`, case-insensitive, blank → `any`.
- Responsible Person Email: matched against the client company's users; unknown email = row error.
- Parent Requirement ID: must reference an existing `REQ-xxx` in the same engagement or an earlier
  row in the same file; forward references = row error.
- No attachment columns. Documents are attached later through normal respond/edit flows.
- Validation is all-or-nothing: nothing persists unless every row passes; failures return row
  number + reason pairs rendered in the import modal.

## UI — Auditor Requirements tab

### Progress strip (top of tab)

Animated segmented horizontal bar: accepted (green) · submitted (blue) · clarification needed
(amber) · pending (grey). Segment widths animate with framer-motion layout transitions; counts use
the existing `CountUp` primitive. Clickable count chips filter the list. A "X% complete" label shows
accepted/total.

### Toolbar

**"New Requirement"** (primary) and **"Bulk Import"** buttons. Bulk Import opens a modal:
download-template link, dropzone, validation-error list, success summary.

### Create modal (replaces inline form)

- Header shows auto-preview chip of the next REQ id.
- Always visible: **Requirement** textarea (required), **Priority** 1–5 selector preset to 1,
  **Due date** (empty, optional).
- **"Advanced options"** collapsed section at bottom; expands with smooth `grid-template-rows`
  0fr→1fr transition revealing: Additional details (textarea), Period from/to (dates), Entity
  (free text with suggestion dropdown of values already used in the engagement), Responsible person
  (select of client company users), Expected format (text/file/any radio, default any),
  Auditor notes (textarea), Parent requirement (searchable REQ picker excluding itself and its own
  descendants).

### List

Parent cards with children indented beneath, collapsible via animated chevron
(`AnimatePresence`). Card contents:

- Mono `REQ-014` badge · status badge (color-mapped) · priority chip (P1 quiet grey; P2–P3 cool
  tones; P4–P5 warm/red tones) · due-date pill turning red when overdue · entity/period muted meta
  line · responsible person name chip · company ETA chip when set.
- **Review bar** (status = submitted): **Accept** primary button; **Need clarification** button
  expanding an inline note field before confirming. Actions call the review endpoint; badges
  crossfade via `AnimatePresence`.
- **Query button**: ~28px circular icon button beside actions; scales ~15% with spring ease on
  hover; tooltip "Initiate query". Opens the new-query modal prefilled with title
  "Clarification on REQ-xxx" and message context, creating a query linked to the requirement.
  Linked-query count badge on the button navigates to the Queries tab thread.
- **History (n)** expander per card listing past responses (who/when/text/document download).

## UI — Company Requirements tab

Same shared `RequirementsProgress` strip. Cards mirror auditor layout minus review controls:

- **Respond panel**: "Respond" button on `pending`/`clarification_needed` cards expands an inline
  panel (`animate-scale-in`) with text-answer textarea + DocVault document picker (keeps today's
  DocVault-centric access granting). Submit flips badge to Submitted.
- **Clarification banner**: amber banner showing `clarification_note` until resubmission.
- **ETA control**: "Expected by: — / Set date" chip on open cards; mini date popover; editable
  until accepted. Once set, renders as "ETA Aug 30"; overdue ETAs highlight red.
- Cards where the logged-in user is the named responsible person show a "You're responsible"
  accent dot.

Both sides respect `prefers-reduced-motion` (existing global CSS override handles this).

## Error handling

- Import: per-row errors listed with row numbers; nothing persisted on any failure.
- Invalid transitions (e.g. respond after accept, review without area access) return 400/403 and
  surface via existing toast system.
- React Query cache invalidation happens only after confirmed success; no optimistic writes.

## Testing

Backend (extend `tests/test_auditease.py`, `tests/test_auditease_multi_auditor.py`):

- Full transition matrix incl. invalid-transition rejections.
- Area gating on every new auditor endpoint; company-role gating on respond/eta.
- Seq numbering across sequential creations and bulk import; REQ id format.
- Import: template shape, happy path, each validation failure, all-or-nothing guarantee,
  within-file parent references, email matching.
- Migration correctness covered by manual verification + model tests post-upgrade.
- Response history ordering and DocumentAccessOverride grants per response.

Frontend (vitest, matching existing patterns):

- Progress strip math (counts, percentages) from mock data.
- Create-form validation (required text, priority bounds, parent-picker exclusions).
- Import modal error rendering.

## Edge cases

- `clarify` from `pending`: allowed (pre-flag before anything arrives); status becomes
  `clarification_needed`; company responds directly from there (→ submitted).
- Engagement close still hard-deletes requirements (existing behavior); responses cascade;
  linked queries survive with `requirement_id` set NULL.
- Requirement with children cannot be deleted (400 — delete or re-parent children first).
- Parent picker excludes the candidate requirement itself and any of its descendants (no cycles).
- `seq_number` never reused even after deletes.
