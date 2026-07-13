# Plan: Page Permissions & User Access Control

**Date:** 2026-07-14

## Phase A: Backend Schema & Migration
1. Add `accessible_modules: Mapped[list[str]] = mapped_column(JSONB, server_default='[]', nullable=False)` to `CompanyUser` in `app/models/company.py`. (Use SQLAlchemy JSON or JSONB).
2. Update `UserCreate`, `UserUpdate`, `UserResponse` in `app/schemas/users.py`.
3. Update `app/routers/users.py` to pass `accessible_modules` in `create_user` and `update_user`.
4. Generate Alembic migration and apply to dev DB via `engine.execute(ALTER TABLE...)` due to the env.py quirk.

## Phase B: Frontend API & Auth Guard
1. Run `npm run gen:api` and update `frontend/src/api/types.ts`.
2. Update `frontend/src/auth/authGuards.tsx`:
   - Create a helper `hasModuleAccess(profile, moduleId)`
   - Create `<ModuleGuard moduleId="...">` to wrap specific routes in `company.routes.tsx`.
3. Apply `<ModuleGuard>` to routes in `company.routes.tsx`.

## Phase C: Sidebar & Users Directory
1. Update `CompanySidebar.tsx` to conditionally render nav items based on `hasModuleAccess`.
2. Update `frontend/src/pages/company/users/UserModal.tsx`:
   - Add a "Module Access" section with Checkboxes or Switches for each module.
   - Map form state to the `accessible_modules` array.

## Phase D: Testing & Verification
1. Fix any frontend tests (`users.test.tsx` or `authGuards.test.tsx`).
2. Run backend `pytest`.
3. Run frontend `tsc -b`, `lint`, `test`.
4. Live E2E: Create a user with limited permissions, login as them, verify sidebar and direct URL access is blocked for unauthorized modules.

## Phase E: Commit
Commit all changes with co-author signature.
