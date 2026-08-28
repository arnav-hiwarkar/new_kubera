# Design Spec: DocVault Universal Approver Selection & Directory Scoping

**Date**: 2026-08-28  
**Status**: Validated  
**Feature**: Universal DocVault Approver Selection for Non-Admins & Admins  

---

## 1. Context & Motivation
In DocVault, any team member with document upload permissions should be able to designate an approver when uploading a document. Previously, the approver picker called the administrative user listing endpoint (`GET /api/v1/users`), which was restricted to Admins with `HTTP 403 Forbidden`, preventing non-admin employees from selecting approvers.

Additionally:
- The approver selection menu should never list the current user (you cannot approve your own document).
- The list must only contain users from the same company who actually have DocVault access (`role == admin` OR `"docvault" in accessible_modules`).
- Soft-deleted (`deleted_at is not None`) and deactivated (`is_active is False`) accounts must never appear.
- If a document is designated for a restricted bucket, only users with access grants to that bucket (plus admins) must be shown.

---

## 2. Architecture & Backend Design

### 2.1 Pydantic Schema: `DocVaultApproverResponse`
In [`app/schemas/docvault.py`](file:///Users/ash/Projects/new_kubera/app/schemas/docvault.py):
```python
class DocVaultApproverResponse(BaseModel):
    id: uuid.UUID
    full_name: Optional[str] = None
    email: str
    role: str  # "admin" | "employee"
    department: Optional[str] = None
    designation: Optional[str] = None

    class Config:
        from_attributes = True
```

### 2.2 Endpoint: `GET /api/v1/docvault/approvers`
In [`app/routers/docvault.py`](file:///Users/ash/Projects/new_kubera/app/routers/docvault.py):
- **Access Control**: Authenticated company user (`Depends(get_current_company_user)`). If the caller is an employee, verifies that `"docvault"` is in `current_user.accessible_modules` (or returns `403 Forbidden`).
- **Query Parameters**:
  - `bucket_id` (`Optional[uuid.UUID]`): Target bucket ID.
- **Query Logic**:
  1. Filter users by company: `CompanyUser.company_id == current_user.company_id`
  2. Exclude current user: `CompanyUser.id != current_user.id`
  3. Filter active accounts: `CompanyUser.deleted_at.is_(None)` and `CompanyUser.is_active == True`
  4. Filter DocVault access:
     - `CompanyUser.role == UserRole.admin` OR
     - `func.jsonb_exists(CompanyUser.accessible_modules, 'docvault')` (or checking `"docvault"` in the array depending on SQLite/PostgreSQL support). To ensure robust cross-DB compatibility (SQLite in tests, PostgreSQL in prod), fetch active users in company and filter by `role == UserRole.admin or "docvault" in (u.accessible_modules or [])`.
  5. If `bucket_id` is supplied:
     - If the bucket has `visibility == BucketVisibility.restricted`:
       - Query `BucketAccessGrant` for `bucket_id`.
       - Allow only users who are `role == UserRole.admin` OR `user.id in bucket_access_user_ids`.
- **Ordering**: Sorted by `full_name` ascending (or `email`).

---

## 3. Frontend Design & Component Updates

### 3.1 Types and API Client
- In `frontend/src/api/types.ts`:
  - Define `DocVaultApproverResponse`.
- In `frontend/src/api/endpoints/docvault.ts`:
  - Add `listApprovers(filters?: { bucket_id?: string })`.
- In `frontend/src/api/hooks/docvault.ts`:
  - Add `useDocVaultApprovers(bucketId?: string)`.

### 3.2 Component Updates: `ApproverPicker.tsx`
- In `frontend/src/pages/company/docvault/ApproverPicker.tsx`:
  - Switch from `useUsers()` to `useDocVaultApprovers(bucketId)`.
  - Display search input with instant query matching on `full_name`, `email`, `department`, and `designation`.
  - Render user avatar initials, role badge (`Admin` or department tag), and email.
  - Automatically exclude self (guaranteed server-side and client-side).
  - Clean error handling and empty states.

---

## 4. Comprehensive Test Plan

### 4.1 Backend Test Cases (`tests/test_docvault_approvals.py`)
1. **Happy Path - Non-Admin Employee Fetching Approvers**:
   - An employee with `docvault` module access calls `GET /api/v1/docvault/approvers`.
   - Returns company admins and other docvault employees.
2. **Anti-Test Case - Self Exclusion**:
   - Verify caller's ID is NEVER included in the approvers list.
3. **Anti-Test Case - Non-DocVault User Exclusion**:
   - Users without `docvault` in `accessible_modules` (and not admins) are excluded.
4. **Anti-Test Case - Deactivated & Soft-Deleted Accounts**:
   - Deactivated (`is_active=False`) and soft-deleted (`deleted_at is not None`) users are excluded.
5. **Anti-Test Case - Cross-Tenant Isolation**:
   - Users from other companies are NEVER returned.
6. **Edge Case - Restricted Bucket Scoping**:
   - When `bucket_id` of a restricted bucket is passed, employees without grant access to that bucket are excluded; admins and granted employees are returned.
7. **Security Gate - Unauthorized Caller**:
   - An employee WITHOUT `docvault` access calling `GET /api/v1/docvault/approvers` receives `HTTP 403 Forbidden`.

### 4.2 Frontend Test Cases (`docvault_approvals.test.tsx`)
1. **Non-Admin Upload & Approver Selection**:
   - Non-admin employee opens `UploadDocumentModal`.
   - Checks "Request document approval".
   - `ApproverPicker` renders eligible approvers (excluding current user).
   - Selecting an approver and uploading sends `needs_approval=true` and `approver_id`.
2. **Empty & Search Filtering**:
   - Searching by name, email, or department filters list correctly in the picker.
