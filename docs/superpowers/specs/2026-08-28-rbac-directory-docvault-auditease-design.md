# RBAC Hardening: Directory Access, Manager Role Removal, DocVault & AuditEase Permissions

## Problem Statement & Context
Currently in Kubera, some administrative actions and sections (such as directory browsing, bucket creation/deletion, and engagement creation/invite/close in AuditEase) are partially accessible or exposed to non-admin users. Additionally, a `manager` role exists in the database and user management interface which is no longer desired.

This design hardens role-based access control across Kubera, establishes strict admin-only boundaries, and removes the `manager` role type across frontend and backend.

---

## 1. Scope & Core Requirements

1. **Directory Access**:
   - Non-admin users must not see the Directory link in navigation.
   - Non-admin users navigating directly to `/app/users` via URL are automatically redirected to `/app` (Dashboard).
   - Backend endpoint `GET /api/v1/users` remains strictly restricted to admin users.

2. **Manager Role Removal & Dashboard Clean-up**:
   - Remove `manager` role from the database enum and models (migrating existing manager records to `employee`).
   - Remove `manager` option from the user creation/editing modal.
   - Remove the "Managers" stat card from the Users Directory.
   - Remove the "Team members / Active directory" stat card from the main Dashboard, avoiding unnecessary user list queries on dashboard load.

3. **DocVault Bucket Governance**:
   - Non-admin users with access to the DocVault module cannot create, rename, manage access, or delete buckets.
   - Frontend `BucketRail` hides "+ New" bucket button and all edit/delete/access action buttons for non-admins.
   - Backend endpoints (`POST /api/v1/docvault/buckets`, `DELETE /api/v1/docvault/buckets/{id}`, `PATCH /api/v1/docvault/buckets/{id}`, `PATCH /api/v1/docvault/buckets/{id}/access`) strictly require admin privileges (`require_admin`).

4. **AuditEase Engagement Creation & Management**:
   - Non-admin users cannot create new engagements (hidden in UI, `POST /api/v1/auditease/engagements` requires admin).
   - Non-admin users cannot invite auditors (hidden in UI, `POST /api/v1/auditease/engagements/{id}/auditors/invite` requires admin).
   - Non-admin users cannot edit auditor permissions or revoke auditors (`PATCH/DELETE /api/v1/auditease/engagements/{id}/auditors/{id}` requires admin).
   - Non-admin users cannot close or delete engagements (hidden in UI, `PATCH /api/v1/auditease/engagements/{id}/close` and `DELETE /api/v1/auditease/engagements/{id}` require admin).

---

## 2. Architecture & Detailed Changes

### 2.1 Backend Changes

#### Data Migration & Models
- **Alembic Migration**:
  - Update `company_users` where `role = 'manager'` to `role = 'employee'`.
  - Recreate or alter `user_role` postgres enum type to `('admin', 'employee')`.
- **`app/models/company.py`**:
  ```python
  class UserRole(str, enum.Enum):
      admin = "admin"
      employee = "employee"
  ```
- **`app/auth.py`**:
  - Update `get_visible_user_ids` and remove obsolete `UserRole.manager` logic.
  - Deprecate or remove `require_manager_or_admin` in favor of `require_admin`.

#### DocVault Router (`app/routers/docvault.py`)
- `POST /api/v1/docvault/buckets`: Change `current_user` dependency from `get_current_company_user` to `require_admin`.
- `DELETE /api/v1/docvault/buckets/{bucket_id}`: Change `current_user` dependency from `get_current_company_user` to `require_admin`.

#### AuditEase Router (`app/routers/auditease.py`)
- `POST /api/v1/auditease/engagements`: Change dependency to `require_admin`.
- `PATCH /api/v1/auditease/engagements/{engagement_id}/close`: Change dependency to `require_admin`.
- `DELETE /api/v1/auditease/engagements/{engagement_id}`: Change dependency to `require_admin`.
- `POST /api/v1/auditease/engagements/{engagement_id}/auditors/invite`: Change dependency to `require_admin`.
- `PATCH /api/v1/auditease/engagements/{engagement_id}/auditors/{auditor_id}`: Change dependency to `require_admin`.
- `DELETE /api/v1/auditease/engagements/{engagement_id}/auditors/{auditor_id}`: Change dependency to `require_admin`.

---

### 2.2 Frontend Changes

#### Navigation & Shell
- **`frontend/src/config/navigation.ts`**:
  - Add `adminOnly?: boolean` to navigation item interface.
  - Set `adminOnly: true` on `{ label: 'Directory', to: '/app/users', icon: Users, adminOnly: true }`.
- **`frontend/src/layouts/CompanyShell.tsx`**:
  - Update navigation filtering:
    ```ts
    const accessibleNav = companyNav
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => {
          if (item.adminOnly && profile?.role !== 'admin') return false
          if (!item.moduleId) return true
          return hasModuleAccess(profile, item.moduleId)
        }),
      }))
      .filter((section) => section.items.length > 0)
    ```

#### Route Protection
- **`frontend/src/auth/company/AdminGuard.tsx`**:
  - Create route wrapper checking `profile?.role === 'admin'`.
  - If not admin, `<Navigate to="/app" replace />`.
- **`frontend/src/routes/company.routes.tsx`**:
  - Wrap `/app/users` in `<AdminGuard><UsersDirectory /></AdminGuard>`.

#### Dashboard (`frontend/src/pages/company/Dashboard.tsx`)
- Remove the "Team members" / "Active directory" `StatCard`.
- Remove `useQuery` listing all company users.

#### Users Directory & Modal
- **`frontend/src/pages/company/UsersDirectory.tsx`**:
  - Remove "Managers" `StatCard`.
  - Update role count state to calculate only `admin` and `employee`.
- **`frontend/src/pages/company/users/UserModal.tsx`**:
  - Remove `'manager'` from role state type.
  - Remove `<option value="manager">Manager</option>` from select input.
- **`frontend/src/api/enums.ts` & `types.ts`**:
  - Update `USER_ROLE` constant to `['admin', 'employee'] as const`.

#### DocVault Page (`frontend/src/pages/company/docvault/BucketRail.tsx`)
- Guard the "+ New" button with `{isAdmin && ...}`.
- Guard the bucket action buttons (pencil rename, user access management, X delete) with `{isAdmin && ...}`.

#### AuditEase UI
- **`frontend/src/pages/company/auditease/EngagementsPage.tsx`**:
  - `actions`: Render `"New engagement"` button only if `isAdmin`.
  - DataTable actions: Render `"Invite"`, `"Close"`, and `"Delete"` buttons only if `isAdmin`.
- **`frontend/src/pages/company/auditease/EngagementWorkspace.tsx`**:
  - Header actions: Render `"Invite auditor"` and `"Close"` buttons only if `isAdmin`.
  - Pass `canManage={isAdmin}` to `AuditorsTab`.
- **`frontend/src/pages/company/auditease/AuditorsTab.tsx`**:
  - Show "Edit access" and "Remove" buttons only when `canManage` (admin).
  - Update disclaimer text to `"Only admins can change access."`

---

## 3. Error Handling & Edge Cases
- **Direct API requests**: Non-admin requests to guarded endpoints return `403 Forbidden`.
- **Direct URL visits**: Non-admin visits to `/app/users` redirect gracefully to `/app` without flashing forbidden screens.
- **Legacy manager tokens**: Any existing session for a user previously assigned `manager` will now resolve to `employee` role post-migration, ensuring consistent permission checks.

---

## 4. Verification Plan
1. **Backend Tests**:
   - Run existing pytest test suite to check for any regressions.
   - Add/update unit and integration tests verifying `403 Forbidden` for non-admin users on:
     - `POST /api/v1/docvault/buckets`
     - `DELETE /api/v1/docvault/buckets/{id}`
     - `POST /api/v1/auditease/engagements`
     - `PATCH /api/v1/auditease/engagements/{id}/close`
     - `DELETE /api/v1/auditease/engagements/{id}`
     - `POST /api/v1/auditease/engagements/{id}/auditors/invite`
     - `PATCH /api/v1/auditease/engagements/{id}/auditors/{id}`
     - `DELETE /api/v1/auditease/engagements/{id}/auditors/{id}`
2. **Frontend Tests & Build**:
   - Run `npm run test` across frontend unit tests (updating mocks for navigation, user directory, and auditease permissions).
   - Run `npm run build` or `npm run typecheck` to verify TypeScript compile-time safety.
3. **Git & Push**:
   - Commit all changes to the `fine-tune` branch.
   - Push `fine-tune` branch to GitHub remote.
