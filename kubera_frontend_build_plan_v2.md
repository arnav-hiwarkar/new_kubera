# Kubera — Frontend V1 Build Plan (Revision 2)

**Supersedes:** `kubera_frontend_build_plan.md` (v1). That version assumed a backend shape (two-portal, single-admin, httpOnly cookie auth) that's since diverged. This version is built against `kubera_full_api_reference.md` — verify that doc confirms the "old modules untouched" assumption below before starting.

---

## 0. Key Decisions Log (changes from v1 in bold)

| Area | Decision |
|---|---|
| Styling | React + Tailwind + shadcn/ui — unchanged. |
| **Role model** | **Three roles on one auth system: `admin`, `manager`, `employee`, distinguished by `role` + `manager_id` hierarchy — not the single-admin model v1 assumed.** UI must branch by role: admin sees everything and configuration screens, manager sees their own data + direct reports', employee sees only their own. |
| **Auditor portal** | **Assumed still separate and unchanged** (own login, own JWT scope, engagement-scoped access) — confirm against the full reference doc. If confirmed, the two-portal structure from v1 still holds: `/company/*` (admin/manager/employee, one system) and `/auditor/*` (fully separate). |
| **Token storage** | **Both `access_token` and `refresh_token` come back in the JSON login response — no httpOnly cookie.** Keep both in memory only (React state/context), never in `localStorage`/`sessionStorage`. Tradeoff: a full page reload logs the user out (no persistence). This is the deliberate V1 choice — simpler than building a cookie flow, and safer than persisting tokens somewhere JS-accessible. Silent-refresh-on-401 still applies, just using the in-memory refresh token instead of a cookie. |
| Data fetching | TanStack Query + Axios — unchanged, `withCredentials` no longer needed since there's no cookie involved. |
| Forms | React Hook Form + Zod — unchanged. |
| **Custom fields** | **Generic, module-scoped custom field system (`/custom-fields/{module}`) now exists as a real backend feature** — build one shared `DynamicField` renderer component (text/number/date/dropdown) driven by this endpoint, used by both Asset Management and Sales Tracking forms. Don't build per-module custom field UIs separately. |
| Testing | Vitest + React Testing Library — unchanged. |
| **Build order** | **Auth shell (3 roles) → docVault → AuditEase → SecretarialEase/ROC → Custom Fields infra → Asset Management → Sales Tracking → KRA & Appraisal.** Extends v1's order to cover the three new modules, custom fields built once right before the two modules that consume it. |
| **Visual direction** | **Sharp, premium, dark, confident — high-end SaaS feel.** See §1 for guardrails — this is one of the three directions AI-generated design defaults to, so it needs a genuinely specific point of view, not just "dark mode with an accent color." |
| **Access control on legacy modules** | **Confirmed, deliberate:** docVault, AuditEase, SecretarialEase, and ROC Compliance currently allow any authenticated company user (admin, manager, or employee) full access — no role restriction. This is intentional for V1 testing, not a bug to route around with frontend guards. Access management for these modules is a deferred phase. Don't build role-gating UI for these four modules; role-gating only applies where the API reference doc says it applies (Users, Assets, Sales, KRA). |
| Old frontend folder | **Reference for visual/UX inspiration only** — layout ideas, component groupings, anything about how the old attempt organized its screens that's worth keeping. **Do not reuse its code, API integration logic, or auth patterns** — it predates this backend and may not match current endpoint shapes at all. |
| Repo layout | `/frontend` directory in the existing repo — unchanged. |
| Dev serving | `npm run dev`, not containerized for V1 — unchanged. |

---

## 1. Visual Direction Brief

"Dark, confident, high-end SaaS" is a legitimate direction, but it's also one of the three looks AI-generated design clusters around by default (near-black background, single bright accent, done). For Kubera specifically — a compliance and audit tool used by senior people at Indian private companies who spend their day in trial balances, board minutes, and ROC filings — the distinctive version of "premium and dark" should come from *that* world, not from generic SaaS dark-mode.

Before writing any component code, Opus should:
1. Propose a compact token system: 4–6 named colors (not just "dark background + one accent" — real premium dark UIs usually have 2–3 tonal darks plus a considered accent, not pure black), a display/body typeface pairing that isn't the default Inter-everywhere choice, and one signature layout or interaction element specific to this product (a possibility worth considering, not a mandate: something in how documents, ledgers, or approval states are visually represented — Kubera's whole job is making dense compliance data legible, so the signature moment could come from *that*, e.g. a distinctive way of showing document status or audit-trail state, rather than a generic hero/dashboard flourish).
2. Show that plan before building the first real screen, not after.
3. Build to the quality floor regardless of direction: responsive to mobile, visible keyboard focus states, respects reduced-motion.

---

## 2. Phase 0 — Auth Shell (3 roles + Auditor portal)

- Vite + React + TypeScript, Tailwind + shadcn/ui installed and themed per the visual direction plan.
- Axios instance, base URL from env var. Response interceptor: on 401, attempt silent refresh using the in-memory refresh token; if that fails, clear state and redirect to login.
- `AppAuthContext` (covers admin/manager/employee — one login system, role read from the login response) and `AuditorAuthContext` (separate, per the assumed-unchanged Auditor system) — confirm this split against the full reference doc before building; if Auditor auth changed, adjust accordingly.
- Route guards: role-aware. `/app/*` requires `AppAuthContext`; certain sub-routes (settings, custom field config, user management) additionally require `role === 'admin'`. `/auditor/*` requires `AuditorAuthContext`.
- Login pages for both portals, plus whatever the actual employee-creation flow is (likely admin-created, not self-serve — confirm against the reference doc) rather than assuming a signup page exists for employees.
- Tests: login flow per role, role-gated route redirects (employee hitting an admin-only route gets bounced), silent refresh behavior, session lost on reload (confirm this is expected, not a bug, given the token-storage decision).

## 3. Phase 1 — docVault (admin/manager scope)

Same as v1's plan (list/filter/search, upload, versioning, buckets, status changes) — re-verify field names and endpoint paths against the full reference doc rather than the original backend build plan, in case anything shifted. Add: role-based visibility if the reference doc indicates docVault access differs by role now (verify — this wasn't part of the original design).

## 4. Phase 2 — AuditEase (admin + auditor portals)

Same scope as v1's Phase 2 (TB import/mapping, ledger group mapping, engagements, audit entries, requirement requests, queries, statement generation) — re-verify against the full reference doc.

## 5. Phase 3 — SecretarialEase & ROC UI

Same as v1's Phase 3 — re-verify field/endpoint names.

## 6. Phase 4 — Custom Fields Infrastructure

Build once, before Asset Management and Sales Tracking:
- Admin-only settings screen: list/create/edit/deactivate custom fields per module (`asset_management`, `sales_tracking`), with `field_type` (text/number/date/dropdown), `is_required`, `dropdown_options`, `display_order`.
- Shared `DynamicField` component: given a field definition + current value, renders the right input type and validates per `field_type`/`is_required`. Consumed by both Asset and Sales create/edit forms via `custom_fields: { field_key: value }`.
- Tests: each field type renders correctly, required validation, dropdown options render from the fetched definition.

## 7. Phase 5 — Asset Management

- List view: filter by `category`, `status`; scoped by role per the reference doc's visibility rules.
- Create/edit form: standard fields (`asset_name`, `serial_number`, `category`, `status`, `purchase_cost`, `custodian_id`) + `DynamicField`-rendered custom fields.
- Import flow: file upload → local header parse → mapping UI (source column → standard field or custom field key) → submit as multipart with the `mappings` JSON array per the reference doc's contract.
- Export button hitting the Excel export endpoint.
- Custodian reassignment (likely a user picker, admin/manager only).
- Tests: import mapping UI logic, custom field rendering in the form, status/category filter behavior.

## 8. Phase 6 — Sales Tracking

- List view, scoped by role/hierarchy automatically per backend.
- `GET /sales/aggregate` → dashboard funnel/bar chart (pick a charting approach — recharts is already an approved library elsewhere in this stack).
- Create/edit form: standard fields (`client_name`, `product_service`, `amount`, `status`, `closing_date`) + `DynamicField` custom fields, reusing the Phase 4 component.
- Status transitions (`lead` → `negotiation` → `won`/`lost`) as a clear, obvious control — this is the kind of state the visual direction's "legible status" signature element should probably show up in.
- Import/export, same pattern as Assets.
- Tests: aggregate chart renders from mock data, status transition control, form validation.

## 9. Phase 7 — KRA & Appraisal

- Manager view: team member list, create KRA for a team member (`title`, `description`, `weightage`, `cycle`).
- KRA detail view with the actual status flow from the reference doc: `draft → pending_approval → approved → in_progress → review_submitted → completed` (or `rejected`), each transition gated by role per the reference doc's rules.
- Employee view: their own KRAs for the current cycle, self-rating + comment input, submit for review.
- Manager review view: rating + comment + approve/reject/complete actions.
- Cycle filter (`cycle` query param, e.g. "Q1-2026").
- Tests: status-flow gating (employee can't jump to `approved`, manager can't submit `employee_self_rating`), cycle filtering, form validation per role.

---

## 10. Build Sequence Summary

| Phase | Scope | Depends on |
|---|---|---|
| 0 | Auth shell, both portals, 3-role guards | Full API reference confirmed |
| 1 | docVault | Phase 0 |
| 2 | AuditEase | Phase 0, 1 |
| 3 | SecretarialEase + ROC | Phase 1 |
| 4 | Custom Fields infra | Phase 0 |
| 5 | Asset Management | Phase 4 |
| 6 | Sales Tracking | Phase 4 |
| 7 | KRA & Appraisal | Phase 0 |

Each phase: Vitest coverage, git commit, stop for your manual test pass before proceeding — same pattern as the backend build.

## 11. Explicitly Out of Scope

Final brand system beyond Phase 0's direction pass, e2e/Playwright tests, full mobile-first redesign (responsive baseline only), notifications UI, activity log UI, containerizing the frontend, any module not covered by the full API reference doc.
