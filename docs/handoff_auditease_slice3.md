# AuditEase — Handover Document

**Module:** AuditEase (Slice 3 Continuation)
**Branch:** `new_frontend`
**Auditor Test Credentials:** `auditor@audit.example.com` / `password123` (Reset during this session)

This document provides a complete summary of all changes made during this session. Another agent can use this context to pick up the build for the next slice (e.g., SecretarialEase / ROC Compliance or finalizing reports).

---

## 1. Backend & Database Changes

### Fixed PostgreSQL `IN (NULL)` Visibility Bug
**The Problem:** All seeded global Schedule III groups (Assets, Liabilities, etc.) were vanishing from the API responses. The queries used `LedgerGroup.company_id.in_([None, company_id])`, but in Postgres, `IN (NULL)` evaluates to NULL (not True), causing all system-seeded groups to be filtered out.
**The Fix:** Updated the filtering logic to explicitly use `or_(LedgerGroup.company_id.is_(None), LedgerGroup.company_id == company_id)`.
*Files modified:* 
- `app/routers/auditease.py`
- `app/services/ledger_groups.py`
- `app/routers/compliance.py` (Fixed preemptively for DocumentType)

### Auditor Entry Endpoints Added
To complete the auditor's ability to propose adjusting entries, the following endpoints were added to the auditor-specific router.
- `GET /api/v1/auditor/engagements/{id}/entries`: Lists all proposed, approved, and rejected entries for an engagement.
- `DELETE /api/v1/auditor/entries/{id}`: Allows an auditor to delete an entry *only* if it is still in the `proposed` state.
*Files modified:*
- `app/routers/auditor_engagements.py`

---

## 2. Frontend Changes

### Auditor Entries Creation & UI
**The Problem:** The auditor had no UI to propose adjusting journal entries.
**The Fix:** Built the complete auditor adjusting entry flow.
- **`AuditorEntriesTab.tsx`**: A dedicated tab that lists all entries with their line items, amounts, and statuses. Includes a "New Entry" button.
- **`NewEntryDrawer` Form**: A slide-out drawer containing a dynamic form with separate sections for **Debit Lines** and **Credit Lines**. It automatically enforces double-entry validation (`sum(debit) == sum(credit)`) and prevents zero-amount lines.
- **Auditor Workspace Integration**: Added the "Entries" tab to the `AuditorEngagementWorkspace.tsx` and updated the top overview cards to display the total number of entries.
- **API Hooks**: Added `useAuditorListEntries`, `useAuditorCreateEntry`, and `useAuditorDeleteEntry` to `auditorEngagements.ts`.

### View-Only Auditor Trial Balance
**The Problem:** The auditor side was using the same `TrialBalanceTable` component, which allowed them to interact with the "Map to Group" and "Create Subgroup" UI, leading to unauthorized errors.
**The Fix:** Added a `readonly` prop to `TrialBalanceTable` and `GroupMappingCell`. When `readonly={true}` is passed (as it is in the Auditor Workspace), the cell simply renders the hierarchical text path (e.g., `Assets › Current Assets`) instead of interactive `<select>` dropdowns.

### UI Bug Fixes & Stability
- **Missing Heroicons Dependency:** The `@heroicons/react` package is not installed in the frontend to maintain stability. Replaced missing imports in `AuditorEntriesTab.tsx` with inline SVG components (`PlusIcon`, `TrashIcon`).
- **Dark Mode Visibility:** The group mapping `<select>` dropdown was invisible in dark mode due to an invalid tailwind class (`bg-surface`). Changed it to `bg-bg-surface` across `GroupMappingCell.tsx`.
- **Component Crashes:** 
  - Fixed a React crash where an object was passed to the `EmptyState` `action` prop instead of a React element.
  - Fixed the `Drawer` component refusing to open because the prop `open` was mistakenly passed as `isOpen`.
  - Fixed a ReferenceError crash in `TrialBalanceTable` by properly destructuring the `readonly` prop.

---

## 3. Current Status & Next Steps

**AuditEase Status:** **Virtually Complete.**
- The company can import a Trial Balance and map ledgers.
- The company can invite an auditor.
- The auditor can review the Trial Balance, raise Queries, and request Requirements.
- **(New)** The auditor can propose Adjusting Journal Entries.
- The company can review and Approve/Reject those entries.

**What's Next?**
1. **Report Generation (AuditEase):** There is a backend endpoint to generate final reports, but the frontend UI to trigger the generation and view the final PDF/HTML statements might need final polishing.
2. **SecretarialEase & ROC Compliance (Phase 3 & 4):** You can now begin building the compliance modules, which rely heavily on the `DocumentType` templating logic already preemptively fixed during this session.
