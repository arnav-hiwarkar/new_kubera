# AuditEase Requirements — Machine Upload & Modern DocVault Picker Implementation Plan

> **For:** Antigravity (Claude / Gemini)  
> **Source Spec:** [`docs/superpowers/specs/2026-08-28-auditease-requirements-upload-docvault-design.md`](file:///Users/ash/Projects/new_kubera/docs/superpowers/specs/2026-08-28-auditease-requirements-upload-docvault-design.md)  
> **Target Files:**
> - `frontend/src/components/auditease/requirements/DocVaultPickerModal.tsx`
> - `frontend/src/components/auditease/requirements/RespondPanel.tsx`
> - `frontend/src/components/auditease/requirements/DocVaultPickerModal.test.tsx`
> - `frontend/src/components/auditease/requirements/RespondPanel.test.tsx`
> - `tests/test_requirement_submissions.py`

---

## Overview of Tasks

1. **Task 1 (Backend Security & Access Verification Tests):** Add and verify integration tests in `tests/test_requirement_submissions.py` ensuring machine uploads route to dedicated engagement buckets, auditors can download submitted files, and auditors are strictly blocked (404) from unsubmitted company documents.
2. **Task 2 (Modern DocVault Picker Modal Redesign):** Rebuild `DocVaultPickerModal.tsx` into a modern modal featuring a left Bucket Rail, multi-field search, tag filtering, "Selected Only" tab toggle, animated document cards with checkmark morphs, and a floating selection tray using `framer-motion`.
3. **Task 3 (RespondPanel Dropzone & Staging Redesign):** Upgrade `RespondPanel.tsx` with an interactive drag-and-drop file dropzone, visual drag-over feedback, unified local + vault document staging cards with removal actions, and seamless multi-part submission.
4. **Task 4 (Frontend Unit Test Suite):** Write comprehensive unit tests for `DocVaultPickerModal.test.tsx` and `RespondPanel.test.tsx` testing search, bucket filtering, staging, drag-and-drop, and form submission.
5. **Task 5 (Full Verification):** Run backend pytest test suite, frontend vitest test suite, TypeScript typecheck (`tsc -b`), and linter.

---

## Detailed Task Breakdown

### Task 1: Backend Security & Access Verification Tests

- [ ] **Step 1.1**: Open `tests/test_requirement_submissions.py` and inspect existing test cases.
- [ ] **Step 1.2**: Add test case `test_auditor_cannot_access_unsubmitted_company_documents`:
  - Create Company A and Auditor A with accepted engagement.
  - Upload Document 1 (in General/custom bucket) and Document 2 (in Engagement bucket).
  - Submit only Document 2 to a requirement.
  - Verify Auditor A can download Document 2 via `GET /api/v1/auditor/documents/{doc2_id}/download`.
  - Verify Auditor A is blocked with 404 when attempting to download unsubmitted Document 1 via `GET /api/v1/auditor/documents/{doc1_id}/download`.
  - Verify Auditor A is blocked with 404 when attempting to fetch metadata via `GET /api/v1/auditor/documents/{doc1_id}`.
- [ ] **Step 1.3**: Add test case `test_employee_user_picker_bucket_scoping`:
  - Create admin user and employee user for Company.
  - Create a public bucket (visibility=everyone) and a restricted bucket (visibility=restricted, not granted to employee).
  - Verify employee calling `GET /api/v1/docvault/buckets` only receives the public bucket.
  - Verify employee calling `GET /api/v1/docvault/documents` only receives documents from accessible buckets or uncategorized.
- [ ] **Step 1.4**: Run `uv run pytest tests/test_requirement_submissions.py` and verify all tests pass.

---

### Task 2: Modern DocVault Picker Modal (`DocVaultPickerModal.tsx`)

- [ ] **Step 2.1**: Refactor `DocVaultPickerModal.tsx` using `framer-motion`:
  - Structure layout into two columns: Left **Bucket Rail** and Right **Document Grid/Explorer**.
  - Left Bucket Rail:
    - "All Buckets" with total count.
    - List of company buckets with folder icon, item count, and lock icon if restricted.
    - Active selection indicator pill.
  - Right Explorer:
    - Search input matching `title`, `tags`, `original_filename`, `bucket_name`.
    - Tag chips filter bar.
    - "Selected Only (N)" tab toggle.
    - "Select all visible" / "Deselect all" toggle.
    - Document Cards: Title, version badge (`v1`, `v2`), bucket name tag, tags pills, formatted size, updated date, and animated checkbox.
    - Empty states for no search matches or empty bucket.
  - Floating / Docked Selection Tray:
    - Slide-up bottom bar with `AnimatePresence`.
    - Selected document chips with removal `X`.
    - "Attach Selected (N)" button with layer icon.
- [ ] **Step 2.2**: Verify styling adheres to project theme variables (`bg-surface`, `border-border`, `accent`, dark mode support).

---

### Task 3: Interactive Dropzone & File Staging in `RespondPanel.tsx`

- [ ] **Step 3.1**: Enhance `RespondPanel.tsx`:
  - Implement drag-and-drop file dropzone (`onDragOver`, `onDragLeave`, `onDrop`) with visual highlight when files are dragged over the dropzone.
  - Include "Browse from Computer" hidden file input trigger and "Select from DocVault" modal trigger.
  - Unified file staging section:
    - Local files staged with blue/emerald file icon, file name, size, and remove button.
    - DocVault files staged with purple/blue vault icon, title, bucket, and remove button.
    - Animated entrance and exit for staged items with `AnimatePresence`.
  - Invalidate `['auditease', 'requirements']`, `['docvault', 'documents']`, and `['company', 'activity']` queries on successful response submission.
- [ ] **Step 3.2**: Check error handling and validation (ensure disabled submit state when both text and files are empty).

---

### Task 4: Frontend Unit Test Suite

- [ ] **Step 4.1**: Create `frontend/src/components/auditease/requirements/DocVaultPickerModal.test.tsx`:
  - Mock `useBuckets` and `useDocuments`.
  - Test bucket rail navigation and filtering.
  - Test search input filtering by title, tag, and filename.
  - Test "Selected Only" filter toggle.
  - Test multi-selection and `onConfirm` callback payload.
- [ ] **Step 4.2**: Create `frontend/src/components/auditease/requirements/RespondPanel.test.tsx`:
  - Test drag-over dropzone styling and file drops.
  - Test file staging list and remove button actions.
  - Test DocVault picker modal trigger and selection staging.
  - Test response form submit calling mutation with proper `FormData`.
- [ ] **Step 4.3**: Run `npm test` in `frontend/` and verify all tests pass.

---

### Task 5: End-to-End Verification

- [ ] **Step 5.1**: Run backend test suite: `uv run pytest`.
- [ ] **Step 5.2**: Run frontend test suite: `npm test` in `frontend/`.
- [ ] **Step 5.3**: Run frontend TypeScript typecheck: `npm run build` in `frontend/`.
- [ ] **Step 5.4**: Run frontend linter: `npm run lint` in `frontend/`.
