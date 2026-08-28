# DocVault Universal Approver Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable non-admin employees and admins to search and select eligible DocVault reviewers when uploading documents, while strictly enforcing company boundary, active DocVault access, restricted bucket access, and self-exclusion.

**Architecture:** A dedicated `GET /api/v1/docvault/approvers` endpoint provides scoped, non-sensitive directory data of DocVault reviewers to all authorized company users, excluding the caller and non-eligible members. Frontend `ApproverPicker` seamlessly queries this endpoint with instant client-side searching.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, React 18, TanStack Query v5, TailwindCSS, Vitest, Pytest.

## Global Constraints
- Only users with active DocVault access (`role == admin` OR `"docvault" in accessible_modules`) are eligible approvers.
- The requesting user MUST NEVER appear in the approver selection list.
- Soft-deleted (`deleted_at is not None`) and inactive (`is_active is False`) users MUST NEVER appear.
- If a restricted `bucket_id` is supplied, only users with granted access (plus admins) are returned.
- Non-admin callers without `docvault` module access receive `HTTP 403 Forbidden`.

---

### Task 1: Backend Schema & `GET /api/v1/docvault/approvers` Endpoint

**Files:**
- Modify: `app/schemas/docvault.py`
- Modify: `app/routers/docvault.py`
- Test: `tests/test_docvault_approvals.py`

**Interfaces:**
- Produces:
  - `DocVaultApproverResponse(id: UUID, full_name: Optional[str], email: str, role: str, department: Optional[str], designation: Optional[str])`
  - `GET /api/v1/docvault/approvers?bucket_id=<uuid>`

- [ ] **Step 1: Write failing backend test cases for `GET /api/v1/docvault/approvers`**

Add tests to `tests/test_docvault_approvals.py`:
- `test_list_approvers_success_for_non_admin_and_excludes_caller`
- `test_list_approvers_excludes_non_docvault_users_and_inactive`
- `test_list_approvers_filters_by_restricted_bucket`
- `test_list_approvers_forbidden_for_user_without_docvault_module`

- [ ] **Step 2: Run pytest to verify tests fail**

Run: `.venv/bin/pytest tests/test_docvault_approvals.py -k test_list_approvers`
Expected: FAIL with 404 Not Found

- [ ] **Step 3: Implement `DocVaultApproverResponse` schema**

In `app/schemas/docvault.py`:
```python
class DocVaultApproverResponse(BaseModel):
    id: uuid.UUID
    full_name: Optional[str] = None
    email: str
    role: str
    department: Optional[str] = None
    designation: Optional[str] = None

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Implement `list_docvault_approvers` in `app/routers/docvault.py`**

In `app/routers/docvault.py`:
```python
@router.get("/approvers", response_model=List[DocVaultApproverResponse])
async def list_docvault_approvers(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    bucket_id: Optional[uuid.UUID] = Query(None),
):
    if current_user.role != UserRole.admin and "docvault" not in (current_user.accessible_modules or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to the DocVault module",
        )

    # 1. Fetch active company members excluding current user
    stmt = (
        select(CompanyUser)
        .where(
            CompanyUser.company_id == current_user.company_id,
            CompanyUser.id != current_user.id,
            CompanyUser.deleted_at.is_(None),
            CompanyUser.is_active == True,
        )
        .order_by(func.coalesce(CompanyUser.full_name, CompanyUser.email).asc())
    )
    result = await db.execute(stmt)
    all_users = result.scalars().all()

    # 2. Filter users who have docvault access
    eligible = [
        u for u in all_users
        if u.role == UserRole.admin or "docvault" in (u.accessible_modules or [])
    ]

    # 3. If bucket_id is restricted, further filter
    if bucket_id:
        b_res = await db.execute(
            select(Bucket).where(
                Bucket.id == bucket_id,
                Bucket.company_id == current_user.company_id,
            )
        )
        bucket = b_res.scalar_one_or_none()
        if bucket and bucket.visibility == BucketVisibility.restricted:
            grants_res = await db.execute(
                select(BucketAccessGrant.company_user_id).where(
                    BucketAccessGrant.bucket_id == bucket_id
                )
            )
            granted_ids = set(grants_res.scalars().all())
            eligible = [
                u for u in eligible
                if u.role == UserRole.admin or u.id in granted_ids
            ]

    return eligible
```

- [ ] **Step 5: Run backend tests to verify they pass**

Run: `.venv/bin/pytest tests/test_docvault_approvals.py`
Expected: PASS all tests

- [ ] **Step 6: Commit backend changes**

```bash
git add app/schemas/docvault.py app/routers/docvault.py tests/test_docvault_approvals.py
git commit -m "feat(docvault): add GET /api/v1/docvault/approvers with scoped filtering"
```

---

### Task 2: Frontend API Types, Endpoint & React Query Hook

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/endpoints/docvault.ts`
- Modify: `frontend/src/api/hooks/docvault.ts`

**Interfaces:**
- Consumes: `GET /api/v1/docvault/approvers`
- Produces:
  - `DocVaultApproverResponse` type
  - `docvaultApi.listApprovers(filters?: { bucket_id?: string })`
  - `useDocVaultApprovers(bucketId?: string)`

- [ ] **Step 1: Add type definitions in `frontend/src/api/types.ts`**

```typescript
export interface DocVaultApproverResponse {
  id: string
  full_name?: string | null
  email: string
  role: 'admin' | 'employee'
  department?: string | null
  designation?: string | null
}
```

- [ ] **Step 2: Add API endpoint in `frontend/src/api/endpoints/docvault.ts`**

```typescript
listApprovers: (filters?: { bucket_id?: string }) =>
  companyClient.get<DocVaultApproverResponse[]>('/api/v1/docvault/approvers', { query: filters }),
```

- [ ] **Step 3: Add React Query hook in `frontend/src/api/hooks/docvault.ts`**

```typescript
export function useDocVaultApprovers(bucketId?: string | null) {
  return useQuery({
    queryKey: ['docvault', 'approvers', bucketId ?? 'all'],
    queryFn: () => docvaultApi.listApprovers(bucketId ? { bucket_id: bucketId } : undefined),
  })
}
```

- [ ] **Step 4: Check TypeScript compile check**

Run: `npx tsc -b` in `frontend`
Expected: PASS with 0 errors

- [ ] **Step 5: Commit frontend API changes**

```bash
git add frontend/src/api/types.ts frontend/src/api/endpoints/docvault.ts frontend/src/api/hooks/docvault.ts
git commit -m "feat(frontend): add useDocVaultApprovers API client and hook"
```

---

### Task 3: Update `ApproverPicker.tsx` Component

**Files:**
- Modify: `frontend/src/pages/company/docvault/ApproverPicker.tsx`

**Interfaces:**
- Consumes: `useDocVaultApprovers(bucketId)`
- Produces: `<ApproverPicker value={approverId} onChange={setApproverId} bucketId={bucketId} />`

- [ ] **Step 1: Replace `useUsers()` with `useDocVaultApprovers()` in `ApproverPicker.tsx`**

In `frontend/src/pages/company/docvault/ApproverPicker.tsx`:
- Call `const { data: approvers = [], isLoading } = useDocVaultApprovers(bucketId)`
- Filter `approvers` by `search` query on `full_name`, `email`, `designation`, and `department`.
- Render search box, avatar initials, role badge, email, and clear selection button.

- [ ] **Step 2: Verify TypeScript compilation**

Run: `npx tsc -b` in `frontend`
Expected: PASS with 0 errors

- [ ] **Step 3: Commit ApproverPicker changes**

```bash
git add frontend/src/pages/company/docvault/ApproverPicker.tsx
git commit -m "feat(docvault): wire ApproverPicker to useDocVaultApprovers"
```

---

### Task 4: Frontend Tests & Full Verification

**Files:**
- Modify: `frontend/src/pages/company/docvault/docvault_approvals.test.tsx`

- [ ] **Step 1: Update mock in `docvault_approvals.test.tsx` for `listApprovers`**

Add `listApprovers: vi.fn()` to `docvaultApi` mock in test and write test verifying:
- Non-admin employee user can search and select an admin or peer approver.
- Caller is not shown in the list.

- [ ] **Step 2: Run frontend test suite**

Run: `npm run test` in `frontend`
Expected: PASS (all tests green)

- [ ] **Step 3: Run backend test suite**

Run: `.venv/bin/pytest tests/test_docvault_approvals.py tests/test_docvault.py tests/test_docvault_bucket_rbac.py`
Expected: PASS (all tests green)

- [ ] **Step 4: Run production build check**

Run: `npm run build` in `frontend`
Expected: PASS with exit code 0

- [ ] **Step 5: Commit test updates**

```bash
git add frontend/src/pages/company/docvault/docvault_approvals.test.tsx
git commit -m "test(docvault): add universal approver selection frontend tests"
```
