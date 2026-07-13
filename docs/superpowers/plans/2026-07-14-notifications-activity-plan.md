# Plan: Notifications & Activity Log Module

**Date:** 2026-07-14

## Phase A: API Layer (Frontend)
1. Add `frontend/src/api/endpoints/notifications.ts` using `companyClient.get` and `companyClient.patch`.
2. Add `frontend/src/api/endpoints/activity.ts` using `companyClient.get`.
3. Add `frontend/src/api/hooks/notifications.ts` exposing `useNotifications` (with a 30s refetch interval) and `useMarkNotificationRead`.
4. Add `frontend/src/api/hooks/activity.ts` exposing `useActivityLog`.

## Phase B: UI Components
1. **ActivityLogPage**: `frontend/src/pages/company/activity/ActivityLogPage.tsx`. Use the standard `DataTable` or a simple list to show `created_at`, `action`, `entity_type`, and `user_id`.
2. **NotificationsPage**: `frontend/src/pages/company/notifications/NotificationsPage.tsx`. A vertical list (or table) showing the notification message, date, and a "Mark as read" button if `read_at` is null.
3. Update `frontend/src/routes/company.routes.tsx` to replace `ModulePlaceholder` for `/company/app/notifications` and `/company/app/activity` with the new pages.

## Phase C: Testing & Verification
1. Add `frontend/src/pages/company/activity/activity.test.tsx`.
2. Add `frontend/src/pages/company/notifications/notifications.test.tsx`.
3. Run `tsc -b`, `npm run lint`, `npm run build`, `npm run test` on the frontend.
4. E2E test via live server.

## Phase D: Commit
Commit with standard backend/frontend message format.
