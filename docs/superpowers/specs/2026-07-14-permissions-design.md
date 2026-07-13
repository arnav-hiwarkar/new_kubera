# Page Permissions & User Access Control

**Date:** 2026-07-14
**Branch:** `new_frontend`
**Status:** Approved — ready for implementation

## 1. Backend Additions

### DB Model & Schema
- Add a JSONB column `accessible_modules` to `CompanyUser` (`app/models/company.py`), default `[]`.
- Update `UserCreate`, `UserUpdate`, and `UserResponse` in `app/schemas/users.py` to include `accessible_modules: list[str] = Field(default_factory=list)`.
- Generate Alembic migration and apply to dev DB.

### API
- The `/api/v1/users` router already maps `body.dict()` or explicit fields. We will update `create_user` and `update_user` to accept and save `accessible_modules`.
- The `get_me` endpoint will now return `accessible_modules` so the frontend knows what the current user can access.

## 2. Frontend Architecture

### Module Constants
- We define a list of known modules: `['dashboard', 'docvault', 'sales', 'assets', 'kra', 'auditease', 'compliance', 'notifications', 'activity']`.

### Sidebar Navigation
- `CompanySidebar.tsx` will filter its navigation links. If the user is an `admin`, show all. If `manager` or `employee`, only show links whose corresponding module ID is included in `profile.accessible_modules`.

### Route Guarding
- Add a simple `ModuleGuard` component in `frontend/src/auth/authGuards.tsx` that checks if the user has access to the current route's module, redirecting to `/app` (or the first accessible module) if unauthorized.

### Users Directory UI
- The existing `frontend/src/pages/company/users/UserModal.tsx` will be expanded. Below the role/department fields, we will render a section "Module Access".
- Render a list of checkbox toggles for each known module.
- For Admins being edited, this section can be disabled or hidden (since Admins always have full access), or just read-only.
