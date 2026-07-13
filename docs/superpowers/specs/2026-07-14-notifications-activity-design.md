# Notifications & Activity Log Module

**Date:** 2026-07-14
**Branch:** `new_frontend`
**Modules:** Notifications (`/api/v1/notifications`), Activity Log (`/api/v1/activity-log`)
**Status:** Approved — ready for implementation plan

---

## 1. Backend additions
None required. The backend routes (`app/routers/notifications.py` and `app/routers/activity.py`) and schemas are already implemented and provide the necessary endpoints.

## 2. Frontend architecture
We will build a simple UI for both modules that replaces the `ModulePlaceholder` in `frontend/src/routes/company.routes.tsx`.

```
frontend/src/api/hooks/notifications.ts
frontend/src/api/endpoints/notifications.ts
frontend/src/api/hooks/activity.ts
frontend/src/api/endpoints/activity.ts

frontend/src/pages/company/notifications/NotificationsPage.tsx
frontend/src/pages/company/activity/ActivityLogPage.tsx
```

## 3. Notifications UI
- A simple page listing all notifications.
- API: Polling every 30 seconds via React Query `refetchInterval`.
- List Item: Shows the notification message and created_at timestamp.
- Unread notifications are visually highlighted (e.g., bold text or a dot indicator).
- A "Mark as Read" button for unread notifications, triggering `PATCH /api/v1/notifications/{id}/read`.
- Lifecycle: Notifications are kept in history, not deleted.

## 4. Activity Log UI
- A simple audit trail page listing activity for the company.
- Access: Company side only.
- List Item: Shows "User X did Y on [Timestamp]" based on the API response.
- Columns: Date/Time, User, Action, Entity Type.
- Read-only, no actions.
