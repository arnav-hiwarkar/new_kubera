# RBAC Hardening: Directory, Manager Role Removal, DocVault & AuditEase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce strict RBAC across Kubera: restrict Directory access to admins with seamless redirect for non-admins, remove the `manager` role completely (database, models, UI), remove dashboard directory stat cards, restrict DocVault bucket mutations (create/rename/access/delete) to admins, and restrict AuditEase engagement creation, auditor invitation/management, and closure/deletion to admins.

**Architecture:** Database enum and row migration converts `manager` to `employee`. FastAPI dependencies enforce `require_admin` on all administrative API endpoints in users, docvault, and auditease routers. The React frontend introduces an `AdminGuard` for `/app/users`, filters sidebar navigation, removes manager stats & user options, and hides restricted action controls across DocVault and AuditEase.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL / SQLite (test), React 18, React Router v6, TanStack Query, Tailwind CSS, Pytest, Vitest.

## Global Constraints

- Python dependencies managed via `uv run pytest`
- Frontend dependencies managed via `pnpm`
- All backend admin endpoints return HTTP 403 Forbidden when accessed by non-admin users
- Non-admin navigation to `/app/users` redirects to `/app` (Dashboard)
- Working branch: `fine-tune`

---

### Task 1: Database Migration & User Role Model Hardening

**Files:**
- Create: `alembic/versions/d8e9f0a1b2c3_remove_manager_role_and_migrate_to_employee.py`
- Modify: `app/models/company.py:79-84`
- Modify: `app/auth.py:160-185`
- Modify: `app/routers/users.py:96-106, 360-375`
- Modify: `app/routers/assets.py:740-755, 815-825`
- Create: `tests/test_user_role_rbac.py`

**Interfaces:**
- Consumes: SQLAlchemy async models, `CompanyUser`, `UserRole`, `require_admin`
- Produces: `UserRole.admin = "admin"`, `UserRole.employee = "employee"`, sanitized `require_admin` dependencies

- [ ] **Step 1: Write failing test for UserRole and user endpoints**

Create `tests/test_user_role_rbac.py`:
```python
import pytest
from httpx import AsyncClient
from app.models.company import UserRole


@pytest.mark.asyncio
async def test_user_role_enum_values():
    assert [e.value for e in UserRole] == ["admin", "employee"]
    assert not hasattr(UserRole, "manager")


@pytest.mark.asyncio
async def test_create_user_manager_role_rejected(company_admin_client: AsyncClient):
    payload = {
        "email": "testmgr@example.com",
        "password": "Password123!",
        "full_name": "Test Manager",
        "role": "manager",
    }
    response = await company_admin_client.post("/api/v1/users", json=payload)
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_user_role_rbac.py -v`
Expected: FAIL due to `UserRole.manager` still existing and accepting "manager".

- [ ] **Step 3: Create Alembic Migration & Update Backend Models and Routers**

Create `alembic/versions/d8e9f0a1b2c3_remove_manager_role_and_migrate_to_employee.py`:
```python
"""remove_manager_role_and_migrate_to_employee

Revision ID: d8e9f0a1b2c3
Revises: f1a2b3c4d5e6
Create Date: 2026-08-28 04:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update any existing manager accounts to employee
    op.execute("UPDATE company_users SET role = 'employee' WHERE role = 'manager'")


def downgrade() -> None:
    pass
```

In `app/models/company.py`:
```python
class UserRole(str, enum.Enum):
    admin = "admin"
    employee = "employee"
```

In `app/auth.py`:
Update `get_visible_user_ids` and `require_manager_or_admin`:
```python
async def get_visible_user_ids(user: CompanyUser, db: AsyncSession) -> list[uuid.UUID]:
    if user.role == UserRole.admin:
        return []  # Indicates all users
    return [user.id]

require_manager_or_admin = require_role(UserRole.admin)
```

In `app/routers/users.py`:
Update lines checking manager assignment:
```python
# In create_user and update_user:
if body.manager_id:
    m_res = await db.execute(
        select(CompanyUser).where(
            CompanyUser.id == body.manager_id,
            CompanyUser.company_id == current_user.company_id,
            CompanyUser.role == UserRole.admin
        )
    )
    if not m_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Invalid manager_id")
```

In `app/routers/assets.py`:
Update approval checks from `(UserRole.admin, UserRole.manager)` to `(UserRole.admin,)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_user_role_rbac.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add alembic/versions/d8e9f0a1b2c3_remove_manager_role_and_migrate_to_employee.py app/models/company.py app/auth.py app/routers/users.py app/routers/assets.py tests/test_user_role_rbac.py
git commit -m "feat(auth): remove manager role and update user role model"
```

---

### Task 2: DocVault Bucket Security Hardening

**Files:**
- Modify: `app/routers/docvault.py:125-143, 231-254`
- Create: `tests/test_docvault_bucket_rbac.py`

**Interfaces:**
- Consumes: `require_admin` dependency
- Produces: Admin-only bucket creation & deletion endpoints

- [ ] **Step 1: Write failing test for DocVault bucket RBAC**

Create `tests/test_docvault_bucket_rbac.py`:
```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_non_admin_cannot_create_bucket(company_employee_client: AsyncClient):
    res = await company_employee_client.post("/api/v1/docvault/buckets", json={"name": "Restricted Bucket"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_and_delete_bucket(company_admin_client: AsyncClient):
    create_res = await company_admin_client.post("/api/v1/docvault/buckets", json={"name": "Admin Bucket"})
    assert create_res.status_code == 201
    bucket_id = create_res.json()["id"]

    del_res = await company_admin_client.delete(f"/api/v1/docvault/buckets/{bucket_id}")
    assert del_res.status_code == 204
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_docvault_bucket_rbac.py -v`
Expected: FAIL on `test_non_admin_cannot_create_bucket` with status code 201 != 403.

- [ ] **Step 3: Update DocVault Router**

In `app/routers/docvault.py`:
Update `create_bucket` and `delete_bucket`:
```python
@router.post("/buckets", response_model=BucketResponse, status_code=status.HTTP_201_CREATED)
async def create_bucket(
    bucket: BucketCreate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    new_bucket = Bucket(
        name=bucket.name,
        company_id=current_user.company_id,
        created_by=current_user.id
    )
    db.add(new_bucket)
    await db.flush()
    await log_activity(db, current_user.company_id, current_user.id, "bucket.created", "bucket", new_bucket.id, {"name": bucket.name})
    await db.commit()
    await db.refresh(new_bucket)
    return new_bucket


@router.delete("/buckets/{bucket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bucket(
    bucket_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(Bucket).where(and_(Bucket.id == bucket_id, Bucket.company_id == current_user.company_id)))
    bucket = result.scalar_one_or_none()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket not found")

    docs = await db.execute(select(Document.id).where(Document.bucket_id == bucket_id).limit(1))
    if docs.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Bucket is not empty")
        
    await db.delete(bucket)
    await log_activity(db, current_user.company_id, current_user.id, "bucket.deleted", "bucket", bucket.id)
    await db.commit()
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_docvault_bucket_rbac.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add app/routers/docvault.py tests/test_docvault_bucket_rbac.py
git commit -m "feat(docvault): restrict bucket creation and deletion to admins"
```

---

### Task 3: AuditEase Engagement Lifecycle & Auditor Access Security Hardening

**Files:**
- Modify: `app/routers/auditease.py:910-1035, 1105-1165`
- Create: `tests/test_auditease_rbac.py`

**Interfaces:**
- Consumes: `require_admin` dependency
- Produces: Admin-only engagement creation, close, delete, and auditor management endpoints

- [ ] **Step 1: Write failing test for AuditEase RBAC**

Create `tests/test_auditease_rbac.py`:
```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_non_admin_cannot_create_engagement(company_employee_client: AsyncClient):
    res = await company_employee_client.post("/api/v1/auditease/engagements", json={"period_label": "FY 2024-25"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_close_or_invite_auditor(
    company_admin_client: AsyncClient,
    company_employee_client: AsyncClient,
):
    # Admin creates engagement
    create_res = await company_admin_client.post("/api/v1/auditease/engagements", json={"period_label": "FY 2024-25"})
    assert create_res.status_code == 201
    eng_id = create_res.json()["id"]

    # Non-admin tries to invite auditor
    invite_res = await company_employee_client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "auditor@example.com"}
    )
    assert invite_res.status_code == 403

    # Non-admin tries to close engagement
    close_res = await company_employee_client.patch(f"/api/v1/auditease/engagements/{eng_id}/close")
    assert close_res.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auditease_rbac.py -v`
Expected: FAIL on `test_non_admin_cannot_create_engagement` with status code 201 != 403.

- [ ] **Step 3: Update AuditEase Router Dependencies**

In `app/routers/auditease.py`:
Replace `get_current_company_user` and `require_manager_or_admin` with `require_admin` on:
- `create_engagement`: `current_user: Annotated[CompanyUser, Depends(require_admin)]`
- `close_engagement`: `current_user: Annotated[CompanyUser, Depends(require_admin)]`
- `delete_engagement`: `current_user: Annotated[CompanyUser, Depends(require_admin)]`
- `invite_auditor`: `current_user: Annotated[CompanyUser, Depends(require_admin)]`
- `update_auditor_access`: `current_user: Annotated[CompanyUser, Depends(require_admin)]`
- `remove_engagement_auditor`: `current_user: Annotated[CompanyUser, Depends(require_admin)]`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auditease_rbac.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add app/routers/auditease.py tests/test_auditease_rbac.py
git commit -m "feat(auditease): restrict engagement creation, lifecycle, and auditor management to admins"
```

---

### Task 4: Frontend Directory Gating, Navigation & Dashboard Cleanup

**Files:**
- Create: `frontend/src/auth/company/AdminGuard.tsx`
- Create: `frontend/src/auth/company/AdminGuard.test.tsx`
- Modify: `frontend/src/config/navigation.ts`
- Modify: `frontend/src/layouts/CompanyShell.tsx`
- Modify: `frontend/src/routes/company.routes.tsx`
- Modify: `frontend/src/pages/company/Dashboard.tsx`
- Modify: `frontend/src/pages/company/UsersDirectory.tsx`
- Modify: `frontend/src/pages/company/users/UserModal.tsx`
- Modify: `frontend/src/api/enums.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/company/UsersDirectory.test.tsx`

**Interfaces:**
- Consumes: `useCompanyAuth` hook, `profile.role`
- Produces: `AdminGuard` component, admin-only directory navigation & route guard, manager-free user management

- [ ] **Step 1: Write failing test for AdminGuard and Directory navigation filtering**

Create `frontend/src/auth/company/AdminGuard.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { AdminGuard } from './AdminGuard'
import * as auth from '@/auth/company'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: vi.fn(),
}))

describe('AdminGuard', () => {
  it('renders children when user is admin', () => {
    vi.mocked(auth.useCompanyAuth).mockReturnValue({
      profile: { role: 'admin' },
    } as any)

    render(
      <MemoryRouter initialEntries={['/app/users']}>
        <Routes>
          <Route path="/app/users" element={<AdminGuard><div>Admin Secret</div></AdminGuard>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText('Admin Secret')).toBeInTheDocument()
  })

  it('redirects to /app when user is employee', () => {
    vi.mocked(auth.useCompanyAuth).mockReturnValue({
      profile: { role: 'employee' },
    } as any)

    render(
      <MemoryRouter initialEntries={['/app/users']}>
        <Routes>
          <Route path="/app/users" element={<AdminGuard><div>Admin Secret</div></AdminGuard>} />
          <Route path="/app" element={<div>Dashboard Home</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.queryByText('Admin Secret')).not.toBeInTheDocument()
    expect(screen.getByText('Dashboard Home')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter frontend test AdminGuard`
Expected: FAIL because `AdminGuard.tsx` does not exist yet.

- [ ] **Step 3: Implement AdminGuard, Navigation, Dashboard, and Users Directory Updates**

Create `frontend/src/auth/company/AdminGuard.tsx`:
```tsx
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useCompanyAuth } from '@/auth/company'

interface AdminGuardProps {
  children: ReactNode
}

export function AdminGuard({ children }: AdminGuardProps) {
  const { profile } = useCompanyAuth()
  if (profile?.role !== 'admin') {
    return <Navigate to="/app" replace />
  }
  return <>{children}</>
}
```

In `frontend/src/config/navigation.ts`:
Add `adminOnly?: boolean` to items in `companyNav`:
```ts
export const companyNav: NavSection[] = [
  {
    items: [
      { label: 'Dashboard', to: '/app', icon: LayoutDashboard, moduleId: 'dashboard' },
      { label: 'Directory', to: '/app/users', icon: Users, adminOnly: true },
    ],
  },
  ...
]
```

In `frontend/src/layouts/CompanyShell.tsx`:
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

In `frontend/src/routes/company.routes.tsx`:
Wrap `UsersDirectory` with `AdminGuard`:
```tsx
import { AdminGuard } from '@/auth/company/AdminGuard'
...
{ path: 'users', element: <AdminGuard><UsersDirectory /></AdminGuard> },
```

In `frontend/src/pages/company/Dashboard.tsx`:
Remove `usersApi.list()` query and remove the `StatCard` for "Team members" / "Active directory".

In `frontend/src/pages/company/UsersDirectory.tsx`:
Remove `"Managers"` StatCard and calculate counts only for `admin` and `employee`.

In `frontend/src/pages/company/users/UserModal.tsx`:
Remove `'manager'` from role options and state:
```tsx
const [role, setRole] = useState<'admin' | 'employee'>('employee')
...
<option value="admin">Admin</option>
<option value="employee">Employee</option>
```

In `frontend/src/api/enums.ts`:
```ts
export const USER_ROLE = ['admin', 'employee'] as const
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm --filter frontend test`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add frontend/src/auth/company/AdminGuard.tsx frontend/src/auth/company/AdminGuard.test.tsx frontend/src/config/navigation.ts frontend/src/layouts/CompanyShell.tsx frontend/src/routes/company.routes.tsx frontend/src/pages/company/Dashboard.tsx frontend/src/pages/company/UsersDirectory.tsx frontend/src/pages/company/users/UserModal.tsx frontend/src/api/enums.ts frontend/src/pages/company/UsersDirectory.test.tsx
git commit -m "feat(ui): add AdminGuard for Directory, remove manager role, clean up dashboard cards"
```

---

### Task 5: Frontend DocVault & AuditEase Permission Gates

**Files:**
- Modify: `frontend/src/pages/company/docvault/BucketRail.tsx:201-255`
- Modify: `frontend/src/pages/company/auditease/EngagementsPage.tsx:130-180`
- Modify: `frontend/src/pages/company/auditease/EngagementWorkspace.tsx:45-55, 130-145`
- Modify: `frontend/src/pages/company/auditease/AuditorsTab.tsx:120-210`
- Modify: `frontend/src/pages/company/docvault/docvault.test.tsx`

**Interfaces:**
- Consumes: `useCompanyAuth` hook, `profile.role === 'admin'`
- Produces: Gated UI controls for bucket management, engagement creation/invite/close/delete

- [ ] **Step 1: Write test verifying non-admin UI gates in DocVault and AuditEase**

In `frontend/src/pages/company/docvault/docvault.test.tsx` (and/or auditease tests):
Add tests verifying that `+ New` button and bucket action buttons are hidden when `profile.role === 'employee'`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter frontend test docvault`
Expected: FAIL if non-admin sees "+ New" button.

- [ ] **Step 3: Update Frontend Gating in DocVault & AuditEase**

In `frontend/src/pages/company/docvault/BucketRail.tsx`:
```tsx
{/* Only admin can create buckets */}
{isAdmin && (
  <button
    onClick={() => setCreating((c) => !c)}
    className="flex items-center gap-1 text-sm text-accent hover:underline"
  >
    <Plus className="h-3.5 w-3.5" />
    New
  </button>
)}

{/* Only admin can see rename/access/delete bucket action buttons */}
{isAdmin && deletable && (
  <div className="grid grid-rows-[0fr] ...">
    ...
  </div>
)}
```

In `frontend/src/pages/company/auditease/EngagementsPage.tsx`:
```tsx
const isAdmin = profile?.role === 'admin'
...
actions={isAdmin ? <Button onClick={() => setCreateOpen(true)}>New engagement</Button> : undefined}

// In table actions column:
{isAdmin && e.status !== 'closed' && (
  <Button size="sm" variant="ghost" onClick={() => setInviteFor(e)}>Invite</Button>
)}
{isAdmin && (e.status === 'invited' || e.status === 'active') && (
  <Button size="sm" variant="ghost" onClick={() => setCloseFor(e)}>Close</Button>
)}
{isAdmin && e.status !== 'active' && (
  <Button size="sm" variant="ghost" className="text-status-action" onClick={() => setDeleteFor(e)}>Delete</Button>
)}
```

In `frontend/src/pages/company/auditease/EngagementWorkspace.tsx`:
```tsx
const isAdmin = profile?.role === 'admin'
...
{!closed && (
  <div className="flex shrink-0 gap-2">
    {isAdmin && (
      <Button variant="secondary" onClick={() => setInviteOpen(true)}>
        Invite auditor
      </Button>
    )}
    {isAdmin && (eng.status === 'invited' || eng.status === 'active') && (
      <Button variant="secondary" onClick={() => setCloseOpen(true)}>
        Close
      </Button>
    )}
  </div>
)}
```

In `frontend/src/pages/company/auditease/AuditorsTab.tsx`:
Ensure `canManage={isAdmin}` is used and disclaimer updated to `"Only admins can change access."`

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter frontend test`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add frontend/src/pages/company/docvault/BucketRail.tsx frontend/src/pages/company/auditease/EngagementsPage.tsx frontend/src/pages/company/auditease/EngagementWorkspace.tsx frontend/src/pages/company/auditease/AuditorsTab.tsx frontend/src/pages/company/docvault/docvault.test.tsx
git commit -m "feat(ui): gate DocVault bucket actions and AuditEase engagement actions to admin only"
```

---

### Task 6: Full Verification & Remote Push

**Files:** None

- [ ] **Step 1: Run complete backend test suite**

Run: `uv run pytest -v`
Expected: All backend tests PASS.

- [ ] **Step 2: Run complete frontend test suite & typecheck**

Run: `pnpm --filter frontend test -- --run && pnpm --filter frontend build`
Expected: All frontend tests PASS and TypeScript compilation succeeds.

- [ ] **Step 3: Push fine-tune branch to remote**

```bash
git push -u origin fine-tune
```
Expected: Successfully pushed to GitHub remote `fine-tune` branch.
