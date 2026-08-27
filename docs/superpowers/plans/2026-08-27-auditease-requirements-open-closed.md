# AuditEase Requirements — Open/Closed Redesign Implementation Plan

> **For:** Antigravity (Claude / Gemini)  
> **Source Spec:** [`docs/superpowers/specs/2026-08-27-auditease-requirements-redesign-design.md`](file:///Users/ash/Projects/new_kubera/docs/superpowers/specs/2026-08-27-auditease-requirements-redesign-design.md)  
> **Branch Baseline:** `graph`  
> **Alembic Head:** `a4b5c6d7e8f9`  

---

## Overview of Tasks

1. **Task 1 (Backend Models & Migration):** Update `RequestStatus` enum, `RequirementRequest`, `RequirementResponse`, add `RequirementResponseDocument`. Create and test Alembic migration.
2. **Task 2 (Backend Services):** Create `app/services/requirements.py`, move `grant_document_access_to_auditors` to `app/services/document_access.py`, rewrite `app/services/requirement_import.py` for 4-column format.
3. **Task 3 (Backend Schemas & Routers):** Update `app/schemas/auditease.py`, rewrite routes in `app/routers/auditor_engagements.py` (close, reopen, edit, delete guards) and `app/routers/auditease.py` (multipart respond).
4. **Task 4 (Backend Test Suite):** Rewrite model/import unit tests, update integration tests in `test_auditease.py` & `test_auditease_multi_auditor.py`, add `test_requirement_submissions.py`.
5. **Task 5 (Frontend API & Contract Alignment):** Update `frontend/src/api/enums.ts`, regenerate `schema.d.ts`, update `types.ts`, endpoints, and TanStack query hooks.
6. **Task 6 (Frontend Primitives & Metrics):** Rewrite `progress.ts`, create `RequirementStatePill.tsx`, `StackedDocsBadge.tsx`, `DocumentChip.tsx`.
7. **Task 7 (Frontend Components & Modals):** Create `RequirementsOverview.tsx`, `SubmissionTimeline.tsx`, `RespondPanel.tsx`, rewrite `NewRequirementModal.tsx` and `BulkImportModal.tsx`, create `RequirementCard.tsx`.
8. **Task 8 (Frontend Pages & Tab Integration):** Rewrite `pages/auditor/RequirementsTab.tsx` and `pages/company/auditease/RequirementsTab.tsx`.
9. **Task 9 (Frontend Test Suite):** Create `progress.test.ts`, `RequirementsOverview.test.tsx`, `RequirementCard.test.tsx`, `RespondPanel.test.tsx`, rewrite `NewRequirementModal.test.tsx`.
10. **Task 10 (End-to-End Verification):** Run migrations roundtrip, full backend pytest suite, frontend typecheck, tests, and linter.

---

## Detailed Task Breakdown

### Task 1: Backend Models & Alembic Migration

- [ ] **Step 1.1**: In `app/models/auditease.py`:
  - Replace `RequestStatus` with `open = "open"`, `closed = "closed"`.
  - Delete `ExpectedFormat` enum.
  - Slim `RequirementRequest`: keep `id`, `engagement_id`, `raised_by`, `seq_number` (int, not null), `description`, `status` (default open), `priority` (default 1), `due_date`, `closed_by`, `closed_at`.
  - Replace `RequirementResponse`: keep `id`, `requirement_id`, `round_number` (int, not null), `responded_by`, `text_answer`, `created_at`, add `documents = relationship("RequirementResponseDocument", cascade="all, delete-orphan", lazy="raise")`.
  - Add `RequirementResponseDocument`: `id`, `response_id` (FK `requirement_responses.id`, cascade), `document_id` (FK `documents.id`, ondelete="SET NULL", nullable=True), `filename` (String(255), not null), unique constraint on `(response_id, document_id)`.
- [ ] **Step 1.2**: Generate and edit Alembic migration `alembic/versions/<rev>_requirements_open_closed.py` with down_revision `a4b5c6d7e8f9`:
  - Create table `requirement_response_documents`.
  - Backfill `requirement_response_documents` from legacy `requirement_responses.document_id`.
  - Add `round_number` to `requirement_responses`, backfill with window function `row_number()`, set NOT NULL, add unique constraint `uq_req_response_round`.
  - Drop FK and column `requirement_responses.document_id`.
  - Swap Postgres enum `request_status` (`open`, `closed`) casting `'accepted'` → `'closed'`, others → `'open'`.
  - Backfill `seq_number` on `requirement_requests`, set NOT NULL.
  - Drop 11 columns from `requirement_requests` (`title`, `additional_details`, `period_from`, `period_to`, `entity`, `responsible_person_id`, `expected_format`, `auditor_notes`, `parent_requirement_id`, `clarification_note`, `company_eta`) and drop type `expected_format`.
  - Add `closed_by`, `closed_at` (backfilling `closed_at = updated_at` where status is closed).
  - Implement lossy downgrade.
- [ ] **Step 1.3**: Run `uv run alembic upgrade head` and verify.

---

### Task 2: Backend Services Layer

- [ ] **Step 2.1**: Move `grant_document_access_to_auditors` into `app/services/document_access.py`.
- [ ] **Step 2.2**: Create `app/services/requirements.py` implementing:
  - `next_seq(db: AsyncSession, engagement_id: uuid.UUID) -> int`
  - `submission_document_title(req_display_id: str, round_number: int, filename: str) -> str`
  - `submission_document_tags(engagement_id: uuid.UUID, req_display_id: str) -> list[str]`
  - `validate_document_ids(db: AsyncSession, company_id: uuid.UUID, document_ids: Sequence[uuid.UUID]) -> None`
  - `create_submission(db: AsyncSession, *, req, engagement_id, company_id, user_id, text_answer, files, document_ids) -> RequirementResponse`
  - `enrich_requirements(db: AsyncSession, engagement_id: uuid.UUID, req_list: Sequence[RequirementRequest]) -> list[dict]` (batch queries for responses, documents with versions metadata, raiser/closer names, query count, display id).
- [ ] **Step 2.3**: Rewrite `app/services/requirement_import.py`:
  - 4-column headers: `["S. No.", "Requirement", "Due Date", "Priority"]`.
  - Update `build_template_xlsx()` to 2 sheets ("Instructions" + "Requirements").
  - `parse_rows()` parses `description`, `due_date`, `priority`. Skips blank spacer rows.
  - `import_requirements()` continues `seq_number` from engagement max + 1. All-or-nothing rollback on `RowError`.

---

### Task 3: Backend Schemas & Routers

- [ ] **Step 3.1**: In `app/schemas/auditease.py`:
  - `RequirementRequestCreate`: `description` (min_length=1), `priority` (1-5, default 1), `due_date` (optional).
  - `RequirementResponseDocumentOut`: `document_id`, `filename`, `size_bytes`, `mime_type`.
  - `RequirementSubmissionOut`: `id`, `requirement_id`, `round_number`, `responded_by`, `responded_by_name`, `text_answer`, `created_at`, `documents`.
  - `RequirementRequestResponse`: `id`, `engagement_id`, `raised_by`, `raised_by_name`, `seq_number`, `requirement_id_str`, `description`, `status`, `priority`, `due_date`, `closed_by`, `closed_by_name`, `closed_at`, `submissions`, `submission_count`, `document_count`, `linked_query_count`, `created_at`, `updated_at`.
- [ ] **Step 3.2**: In `app/routers/auditor_engagements.py`:
  - Remove dead helpers (`_next_seq`, `_validate_refs`, `_would_cycle`, `_apply_metadata`, `review_requirement`).
  - Import `next_seq`, `enrich_requirements` from `app/services/requirements`.
  - Update `create_requirement`.
  - Update `update_requirement`: allow any auditor with `requirements` area; 400 if `closed`; update description, priority, due_date; log `requirement.updated`.
  - Update `delete_requirement`: allow any auditor with `requirements` area; 400 if any `RequirementResponse` exists; log `requirement.deleted`.
  - Add `POST /engagements/{id}/requirement-requests/{req_id}/close` (sets status=closed, closed_by, closed_at, logs `requirement.closed`).
  - Add `POST /engagements/{id}/requirement-requests/{req_id}/reopen` (sets status=open, closed_by=None, closed_at=None, logs `requirement.reopened`).
  - Update `download_requirement_import_template` and `import_requirements_endpoint`.
- [ ] **Step 3.3**: In `app/routers/auditease.py`:
  - Remove `RequirementRespond`, `CompanyEtaUpdate`, `set_requirement_eta`, and `grant_document_access_to_auditors`.
  - Import `enrich_requirements`, `create_submission` from `app/services/requirements`.
  - Rewrite `respond_requirement` to accept multipart Form/File parameters (`text_answer`, `document_ids`, `files`). Return 400 if closed, 422 if empty. Call `create_submission` and log `requirement.submitted`.
- [ ] **Step 3.4**: In `app/services/account_admin.py`: update docstring for `requirement_response_documents`.

---

### Task 4: Backend Test Suite

- [ ] **Step 4.1**: Rewrite `unit_tests/test_requirement_models.py` (column assertions, defaults, round_number uniqueness, join table constraints).
- [ ] **Step 4.2**: Rewrite `unit_tests/test_requirement_import.py` (4-column template, valid parsing, missing requirement, invalid dates/priority, ignore S. No.).
- [ ] **Step 4.3**: Update `tests/test_auditease.py`:
  - Rewrite `test_requirements_and_queries` for Open/Closed lifecycle and multi-round responses.
  - Delete `test_requirement_parenting_guards`.
  - Rewrite `test_requirement_bulk_import_roundtrip` for 4 columns.
- [ ] **Step 4.4**: Create `tests/test_requirement_submissions.py`:
  - Multi-file uploads in one round.
  - Mixed text + uploaded files + DocVault picked documents.
  - Round numbering increment (1 → 2).
  - Auditor access overrides verification.
  - Document title convention & tag verification.
  - Deleted document preserves join row with `document_id is None`.
  - Cross-tenant document ID rejection (404, atomic rollback).
- [ ] **Step 4.5**: Update `tests/test_auditease_multi_auditor.py` (close, reopen, multipart respond, updated activity log assertions).
- [ ] **Step 4.6**: Update `tests/test_account_admin.py` (verify `requirement_response_documents` purge cascade).
- [ ] **Step 4.7**: Run `uv run pytest` across the entire backend test suite.

---

### Task 5: Frontend API Types, Enums & Hooks

- [ ] **Step 5.1**: In `frontend/src/api/enums.ts`: update `REQUEST_STATUS = ['open', 'closed'] as const` and remove legacy RequestStatus entries from `STATUS_TONE`.
- [ ] **Step 5.2**: Regenerate `frontend/src/api/schema.d.ts` using `npm run gen:api` (with backend running).
- [ ] **Step 5.3**: In `frontend/src/api/types.ts`: add `RequirementSubmission` and `RequirementSubmissionDocument` aliases.
- [ ] **Step 5.4**: In `frontend/src/api/endpoints/auditorEngagements.ts`: remove `reviewRequirement`, add `closeRequirement` and `reopenRequirement`.
- [ ] **Step 5.5**: In `frontend/src/api/endpoints/auditease.ts`: remove `setRequirementEta`, update `respondRequirement` to accept `FormData`.
- [ ] **Step 5.6**: In `frontend/src/api/hooks/auditorEngagements.ts`: remove `useAuditorReviewRequirement`, add `useAuditorCloseRequirement` and `useAuditorReopenRequirement`.
- [ ] **Step 5.7**: In `frontend/src/api/hooks/auditease.ts`: remove `useSetRequirementEta`, update `useRespondToRequirement` signature.

---

### Task 6: Frontend Primitives & Derived State

- [ ] **Step 6.1**: Rewrite `frontend/src/components/auditease/requirements/progress.ts`:
  - Types: `DisplayState = 'awaiting' | 'responded' | 'closed'`, `RequirementFilter = DisplayState | 'overdue'`.
  - Functions: `deriveState`, `isOverdue`, `matchesFilter`, `computeCounts`, `overdueCount`, `documentTotal`, `percentComplete`.
- [ ] **Step 6.2**: Delete `RequirementsProgress.tsx` and `RequirementsProgress.test.tsx`.
- [ ] **Step 6.3**: Create `RequirementStatePill.tsx` with explicit tone mapping (`awaiting` → neutral, `responded` → info, `closed` → success).
- [ ] **Step 6.4**: Create `StackedDocsBadge.tsx` (layered document icon with count).
- [ ] **Step 6.5**: Create `DocumentChip.tsx` (file extension icon, filename, size, download trigger, disabled state when deleted).

---

### Task 7: Frontend Panels, Timeline & Modals

- [ ] **Step 7.1**: Create `RequirementsOverview.tsx`:
  - Concentric SVG Donut (animating on mount only).
  - 4 `StatCard` metric tiles: Requirements, Documents in, Awaiting review, Overdue.
  - 4 filter pill toggle buttons.
- [ ] **Step 7.2**: Create `SubmissionTimeline.tsx` (vertical timeline, round headers, respondent, timestamp, text answer, 2-col document grid, history mode).
- [ ] **Step 7.3**: Create `RespondPanel.tsx` (textarea, `FileUploadDropzone` with `multiple`, DocVault multi-select, staged file list with per-item remove, submit button).
- [ ] **Step 7.4**: Rewrite `requirementForm.ts` and `NewRequirementModal.tsx` for the 3 fields (Description textarea, Priority, Due Date).
- [ ] **Step 7.5**: Update `BulkImportModal.tsx` copy for 4-column format.
- [ ] **Step 7.6**: Create `RequirementCard.tsx` (collapsed row with mono ID, truncated text, state pill, due date, stacked docs badge; expandable into timeline and actions).

---

### Task 8: Frontend Pages Integration

- [ ] **Step 8.1**: Rewrite `frontend/src/pages/auditor/RequirementsTab.tsx`:
  - Mount `RequirementsOverview`, action header (Bulk import, New requirement), and `RequirementCard` list.
  - Wire actions: Edit (modal), Initiate Query (linked query button with counter), Close, Reopen, Delete (if 0 submissions).
- [ ] **Step 8.2**: Rewrite `frontend/src/pages/company/auditease/RequirementsTab.tsx`:
  - Mount `RequirementsOverview` and `RequirementCard` list.
  - Wire Respond action opening inline `RespondPanel`.
  - Clean distinct empty states (no requirements / all closed / filter empty).

---

### Task 9: Frontend Tests

- [ ] **Step 9.1**: Create `progress.test.ts` (state derivation, overdue checks, count metrics).
- [ ] **Step 9.2**: Create `RequirementsOverview.test.tsx` (render counts, filter toggles, donut geometry).
- [ ] **Step 9.3**: Create `RequirementCard.test.tsx` (collapsed/expanded states, badges, keyboard navigation).
- [ ] **Step 9.4**: Create `RespondPanel.test.tsx` (file staging, multi-select, FormData assembly).
- [ ] **Step 9.5**: Rewrite `NewRequirementModal.test.tsx` (3-field validation, default priority).
- [ ] **Step 9.6**: Run `npm test` across vitest suite.

---

### Task 10: End-to-End Verification

- [ ] **Step 10.1**: Run `uv run alembic downgrade -1 && uv run alembic upgrade head` to verify migration roundtrip.
- [ ] **Step 10.2**: Run `uv run pytest` to ensure 100% backend test pass.
- [ ] **Step 10.3**: Run `cd frontend && npm run build` for TypeScript compiler verification.
- [ ] **Step 10.4**: Run `cd frontend && npm test` for vitest suite.
- [ ] **Step 10.5**: Run `cd frontend && npm run lint` to guarantee `--max-warnings 0`.
