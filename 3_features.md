# Kubera — Asset Management / Sales Tracking / KRA & Appraisal
## Draft Requirements for Grill-Me Session (Antigravity/Opus)

**Purpose of this document:** raw requirements below have been cleaned up and annotated with `[DECISION NEEDED]` markers everywhere the original wording leaves something genuinely open. This is meant to be fed into a grill-me session so Opus interrogates *these specific points* rather than re-discovering them from scratch. Do not build from this doc directly — it's an input to the interview, not a spec.

---

## 0. Cross-Cutting Fork — Resolve This First

All three modules below assume some notion of an individual employee acting inside the system:
- Sales Tracking needs to record **who** entered/owns each sale.
- KRA & Appraisal needs employees to **log in and self-report** their own KRA progress, and managers to **log in and approve** their reports.

The current backend has exactly one login per company (`CompanyAdmin`-equivalent), with a `CompanyUser` table that's schema-shaped for roles but doesn't expose employee-level signup/login yet. That was a deliberate V1 scope cut.

**`[DECISION NEEDED]`** Pick one before anything else in this batch gets built:

- **(A) Real employee logins.** Extend `CompanyUser` into actual multi-user auth — employees get their own credentials, log in, see only their own KRAs/sales entries, managers see their reports' data. This is what the KRA requirement as written actually implies ("each employee will be able to write their KRAs"). Biggest lift, but it's the only option where "employee self-reports progress" is literally true.
- **(B) Reference-only employee records, admin-mediated.** `Employee` stays a plain data record (name, manager link) with no login. All entry — sales, KRA progress updates — is done *by the admin, on the employee's behalf*, with the employee just tagged as the "who" on the record. Sales Tracking's "who did it" becomes a dropdown field, not an audit-log actor. KRA's "employee writes their own KRA" becomes "admin records what the employee reported to them." Much smaller lift, but changes the product's actual usage pattern (this stops being self-service for employees).
- **(C) Hybrid — build the login system, but only for KRA.** Sales Tracking stays admin-mediated (reference-only Employee tagging), KRA gets real employee+manager logins since that module doesn't really work without them. Middle ground: only pay the auth-system cost where the requirement genuinely can't be satisfied without it.

This decision should happen before Opus scopes Sales Tracking or KRA in any detail, since the entry point (who can even call these endpoints) depends on it.

---

## 1. Asset Management

### Cleaned requirements
- A per-company asset register: each row is one asset, with a base set of fields (name, cost, purchase date) plus company-defined additional fields.
- Company can add/remove/modify which columns exist for their asset register, beyond the base set.
- Bulk import via xlsx/csv, using the same flexible column-mapping pattern already built for Trial Balance import (arbitrary sheet, arbitrary starting row, user maps source columns to target fields).
- Full CRUD on individual asset entries (view, add, edit, delete) through the app, not just via import.
- Export the current asset register to xlsx.

### Open questions
- `[DECISION NEEDED]` **Custom column model.** Two real options: (i) fully dynamic schema — company literally defines arbitrary typed columns, stored as JSONB `custom_fields` on each `AssetRecord`, with a company-level `AssetFieldDefinition` table describing what those fields are and their type (text/number/date/dropdown); or (ii) a fixed wide table with a fixed set of optional columns. Given the company import-mapping requirement, (i) is almost certainly what's needed — flag it as the assumed default unless the interview surfaces otherwise.
- `[DECISION NEEDED]` What happens to existing rows when a company removes or renames a custom field? Does historical data get orphaned/hidden, or does removal get blocked if data exists in that field?
- `[DECISION NEEDED]` Should assets support a status (e.g. active / under maintenance / disposed)? The requirement doesn't mention it but it's a near-universal need for an asset register — worth asking rather than assuming.
- `[DECISION NEEDED]` Should an asset be linkable to a docVault document (e.g. purchase invoice, warranty card)? Not mentioned, but docVault already exists and this is a natural fit.
- `[DECISION NEEDED]` Depreciation — old build notes mention "fields stored but not calculated." Confirm whether V1 needs even the fields, or whether this is fully out of scope until a later phase.
- Does import validate anything beyond column mapping (e.g. cost must be numeric, date must parse), and what happens on a row-level validation failure — skip the row, block the whole import, or import with flagged errors?

### Suggested additions to raise
- Asset categories/tags (separate from fully custom fields — a first-class grouping mechanism, similar to docVault buckets) for filtering/reporting.
- Assignment/custodian field (which employee or department currently holds the asset) — depends on the §0 decision, since "which employee" needs an Employee reference either way.

---

## 2. Sales Tracking

### Cleaned requirements
- A per-company sales entry log: base fields (date, title, customer, cost, duration) plus company-defined additional fields, same customization pattern as Asset Management.
- Full CRUD on entries.
- Export to xlsx/csv.
- Each entry records who made/owns the sale.

### Open questions
- `[DECISION NEEDED]` Directly depends on §0. If (A) real logins: "who did it" is the authenticated actor, enforced server-side. If (B) reference-only: "who did it" is a selectable `Employee` field on the entry form, set by whoever (the admin) is entering it — not provable as "actually who did it," just "who it's attributed to."
- Same custom-field model question as Asset Management — assume JSONB `custom_fields` + company-level field definitions unless told otherwise, but confirm.
- `[DECISION NEEDED]` Visibility/scoping: can a salesperson see only their own entries, or everyone's? (Only relevant if §0 resolves to (A) or (C) with real logins — otherwise the admin sees everything by definition.) The old build plan's answer was "scoped by manager-hierarchy" — confirm this is still wanted, and that it's the same hierarchy table KRA needs (see §3), built once and shared.
- `[DECISION NEEDED]` Any target/quota concept for Sales Tracking itself (distinct from KRA sales targets), or is this purely a log with no goal-tracking of its own?
- Should entries support a status (e.g. pending / confirmed / cancelled) the way docVault and Asset records might?

### Suggested additions to raise
- Basic aggregate views (totals by employee/period) — the requirement only asks for entry-level CRUD + export, but a running total is a near-zero-cost addition given the data's already structured.
- Duplicate/near-duplicate detection on import (e.g. same customer + date + amount) — worth asking if that's a real-world pain point for them or overkill for V1.

---

## 3. KRA & Appraisal

### Cleaned requirements
- Employee database, importable or manually created, each employee mapped to a manager (self-referencing hierarchy — one direct manager per employee, per the old plan; confirm still true).
- Company defines the KRA tracking structure itself: period/cycle type (yearly, quarterly, custom), and presumably what fields/sections a KRA entry has.
- Employees write their own KRAs for a given period — can create as many KRA items as they want within that period.
- Manager approves the *plan* (the set of KRAs and their targets) before the period starts being tracked.
- During the period, employee freely updates progress against each KRA (`current_value`), which can be numeric, percentage, or free-form status (e.g. "exceeded").
- At period end, manager approves the *final/achieved* state.
- Exportable per-employee and org-wide (target vs. achieved) for the appraisal cycle.

### Open questions
- `[DECISION NEEDED]` Directly depends on §0 — this module is the strongest case for real employee+manager logins (option A or C), since "employee writes their own KRA" and "manager approves" are both described as actions taken by specific people, not admin-mediated data entry.
- `[DECISION NEEDED]` KRA item structure — old build plan modeled `target_type` as an enum (`numeric`, `percentage`, `boolean`, `rating`) with `target_value`/`current_value`. Confirm this still covers it, and clarify: is `target_type` fixed per KRA item, or does the *company* define custom KRA "types"/templates beyond these four (the requirement's "let it be flexible and company-editable" is vague on whether that means field-level customization or entirely custom KRA categories)?
- `[DECISION NEEDED]` Multiple KRAs per employee per period, each potentially a different type/weight — at appraisal/export time, is there any aggregation (weighted score, overall rating) or is the export purely a list of each KRA's target vs. achieved with no roll-up number? The requirement doesn't ask for a combined score but it's a very common appraisal-system feature, worth surfacing explicitly rather than assuming either way.
- `[DECISION NEEDED]` What happens if a manager rejects the plan, or rejects the final achievement — is there a revision loop (employee edits and resubmits), or is reject terminal for that KRA?
- `[DECISION NEEDED]` `KraPeriod` — is the cycle (yearly/quarterly/custom) a single company-wide setting applied to everyone, or can different employees/departments be on different cycles? Old plan assumed one setting for the whole company; the new requirement text doesn't explicitly reconfirm that.
- What happens to an employee's KRA history when they change managers mid-period, or leave the company? Not mentioned — worth a decision even if the answer is "out of scope for V1, freeze on manager change."
- Does "cross off" KRAs mean a boolean completion flag distinct from `current_value`, or is that just describing what updating a boolean/rating-type KRA looks like in the UI? Read literally it sounds like there might be a completion checkbox in addition to the numeric progress tracking — worth clarifying it's not a fifth concept.

### Suggested additions to raise
- KRA templates at the company level (predefined KRA categories/descriptions a manager can assign to multiple employees, rather than every employee typing theirs from scratch) — reduces friction for common roles (e.g. every salesperson gets a "revenue target" KRA pre-filled).
- Manager comment/feedback field at each approval gate, separate from a pure approve/reject — appraisal systems almost always need qualitative feedback alongside the number.
- Whether KRA and Sales Tracking should actually be linked — e.g. a sales-target KRA auto-populating `current_value` from actual Sales Tracking totals, rather than the employee manually re-entering a number that already exists elsewhere in the system. Not asked for, but given both modules exist in the same app, worth at least asking whether it's wanted (even if the answer is "no, keep them separate for V1").

---

## 4. Shared Infrastructure Across All Three

Regardless of how §0 resolves, these are reusable rather than rebuilt per module:

- **Flexible column-mapper import utility** — already built for Trial Balance (Phase 2 of the backend). Asset Management and Sales Tracking should reuse it as a shared service, not reimplement it.
- **JSONB `custom_fields` + field-definition pattern** — if the dynamic-column decision goes the way flagged above, this pattern is identical across Asset Management and Sales Tracking and should be one shared mechanism (e.g. a generic `CustomFieldDefinition` + `custom_fields` JSONB column pattern), not two separate implementations.
- **Manager-hierarchy table** — needed by both Sales Tracking (if scoping visibility by manager) and KRA (approval routing). Build once, shared, per the old build plan's intent.
- **Export-to-xlsx utility** — same underlying mechanism for Asset Management, Sales Tracking, and KRA exports; build once.
