# Design Specification: KUB-020 Missing Authorization on Asset Disposal

**Status:** Approved  
**Author:** AI Pair Programmer & System Architect  
**Date:** 2026-09-04  
**Target Release:** Immediate Security Hardening  
**Issue Reference:** KUB-020 (High-severity missing authorization)  
**Corpus / Repo:** new_kubera (FastAPI + React + Postgres)  

---

## 1. Context & Vulnerability Description

### 1.1 The Vulnerability (KUB-020)
In `app/routers/assets.py:849-931`, `dispose_asset` allows any authenticated company user—including an employee with `accessible_modules == []`—to dispose of capitalized assets:

```python
@router.post("/{asset_id}/dispose", response_model=AssetResponse)
async def dispose_asset(
    asset_id: uuid.UUID,
    body: AssetDisposalRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Db,
):
    ...
```

Disposal is an irreversible accounting transaction:
- Transitions `asset.lifecycle_status` from `capitalized` to `disposed`.
- Sets `disposal_date`, `disposal_type`, `sale_proceeds`, `buyer_name`, and `disposal_it_proceeds`.
- Removes the asset from the active depreciation base and triggers gain/loss recognition during financial year depreciation runs.
- Has **no reversal path** in the codebase (`delete_draft_asset` explicitly documents that capitalized assets "never" get deleted and can only leave through disposal).

While `_load_asset(asset_id, current_user.company_id, db)` enforces company scoping, the endpoint lacks intra-tenant module and role gating.

### 1.2 Frontend Discrepancy & Role Drift
`frontend/src/pages/company/assets/AssetDetailPage.tsx:242-253` only displays the "Dispose Asset" button when:
```typescript
const isAdmin = profile?.role === 'admin'
const canApprove = isAdmin || profile?.role === 'manager'
...
{canApprove && (
  <Button variant="secondary" size="sm" onClick={() => setDisposalOpen(true)}>
    Dispose Asset
  </Button>
)}
```
Because `UserRole` (`app/models/company.py:80-83`) only defines `admin` and `employee` (`manager` was removed in prior schema consolidation), `canApprove` is effectively `isAdmin`. The security boundary was enforced solely in the browser client, exactly mirroring KUB-001.

### 1.3 Inconsistencies in `app/routers/assets.py`
The router previously exhibited three divergent patterns:
1. `Reader` (`require_assets_module`): used for draft creation, updates, and read queries.
2. `Admin` (`require_admin`): used for `delete_draft_asset`.
3. Hand-rolled admin check with bare `get_current_company_user`: used for `approve_asset` and `reject_asset`.
   - In `approve_asset` line 765, `if current_user.role != UserRole.admin and unit.created_by == current_user.id:` was completely unreachable dead code because line 745 already 403s every non-admin.
4. Bare `get_current_company_user` with zero checks: used for `dispose_asset`.

---

## 2. Production Impact Analysis

> [!NOTE]
> **Will this change break anything on the current deployment to production?**
> **No.** 
> 1. **Admins:** In `app/auth.py`, `user_has_module(user, module_id)` returns `True` for `admin` role unconditionally. Admins pass `require_assets_module` and `require_admin`. Valid disposal requests by admins will continue working unchanged.
> 2. **Employees:** In production, employees never had access to the disposal button in the frontend (it was guarded by `canApprove`, which resolved to false for employees). Legitimate employees do not dispose of assets; only an attacker manually posting to the API could exploit this endpoint.
> 3. **Other routes in `assets.py`:** All other routes already required `Reader` (`require_assets_module`) or `Admin`. Putting `require_assets_module` at the router level does not disrupt any legitimate user flow.
> 4. **Frontend:** Removing `profile?.role === 'manager'` cleans up dead code without altering runtime behavior.

---

## 3. Architecture & Design Decisions

### 3.1 Gating Strategy: Router Module Gate + Route Admin Dependency
1. **Router-Level Module Gate:**
   Mount `require_assets_module` on `router = APIRouter(...)` in `app/routers/assets.py`:
   ```python
   router = APIRouter(
       prefix="/api/v1/assets",
       tags=["assets"],
       dependencies=[Depends(require_assets_module)],
   )
   ```
   This mirrors `app/routers/depreciation.py` and `app/routers/financial_years.py`. Every route under `/api/v1/assets` is immediately protected from users lacking module access.
2. **Route-Level Admin Dependency on `dispose_asset`:**
   ```python
   @router.post("/{asset_id}/dispose", response_model=AssetResponse)
   async def dispose_asset(
       asset_id: uuid.UUID,
       body: AssetDisposalRequest,
       current_user: Admin,
       db: Db,
   ):
   ```
   Uses the existing `Admin = Annotated[CompanyUser, Depends(require_admin)]` shorthand.

### 3.2 Normalization of `approve_asset` and `reject_asset`
- Update `approve_asset` and `reject_asset` to take `current_user: Admin`.
- Remove manual `if current_user.role != UserRole.admin: raise HTTPException(403)` blocks.
- Remove dead SoD code in `approve_asset` line 765.

### 3.3 Segregation of Duties (SoD)
- **Decision:** Do NOT bar the creator (`created_by`) or approver (`approved_by`) from disposing an asset if they are an Admin.
- **Rationale:** Small-to-medium businesses frequently operate with a single administrator. Barring the creator/approver would permanently lock single-admin companies out of disposing their assets.
- **Accounting Control:** Non-repudiation and audit logging.
  - `asset.disposed_by = current_user.id` is saved on the asset record.
  - `log_activity` records an `asset.disposed` event with `disposal_date`, `disposal_type`, `sale_proceeds`, and actor ID.

### 3.4 Pure Predicate Helper
To support unit testing without HTTP/DB dependencies:
```python
def can_dispose_asset(user: CompanyUser, asset: Asset) -> tuple[bool, str | None]:
    """Pure authorization and lifecycle predicate for asset disposal."""
    if user.role != UserRole.admin:
        return False, "Insufficient permissions"
    if asset.lifecycle_status != AssetLifecycleStatus.capitalized:
        return False, f"Only a capitalized asset can be disposed of (this asset is {asset.lifecycle_status.value})"
    return True, None
```

### 3.5 Status Codes & Error Semantics
| Scenario | Caller | Asset State / Tenant | HTTP Code | Detail Message | Gating Point |
|---|---|---|---|---|---|
| No Token | None | Any | `401 Unauthorized` | "Not authenticated" | `get_current_company_user` |
| Invalid Token | Tampered | Any | `401 Unauthorized` | "Could not validate credentials" | `get_current_company_user` |
| Zero Modules | Employee (`accessible_modules: []`) | Any | `403 Forbidden` | "No access to the assets module" | `require_assets_module` (router gate) |
| Non-Asset Module | Employee (`accessible_modules: ["sales"]`) | Any | `403 Forbidden` | "No access to the assets module" | `require_assets_module` (router gate) |
| Has Asset Module, Non-Admin | Employee (`accessible_modules: ["assets"]`) | Any | `403 Forbidden` | "Insufficient permissions" | `require_admin` (`Admin`) |
| Non-Existent Asset | Admin | Non-existent UUID | `404 Not Found` | "Asset not found" | `_load_asset` |
| Cross-Tenant Asset | Admin (Tenant A) | Belongs to Tenant B | `404 Not Found` | "Asset not found" | `_load_asset` |
| Invalid Lifecycle | Admin | Company-owned, `draft` / `ready` / `disposed` | `409 Conflict` | "Only a capitalized asset can be disposed of (this asset is ...)" | Handler lifecycle check |
| Domain Validation Failed | Admin | Company-owned, `capitalized` | `422 Unprocessable` | Domain error from `validate_disposal` | `validate_disposal` |
| Malformed UUID | Any | Invalid UUID string | `422 Unprocessable` | FastAPI validation error | Path parsing |
| Valid Request | Admin | Company-owned, `capitalized` | `200 OK` | `AssetResponse` | Successful commit |

### 3.6 Information-Leakage & Oracle Prevention
FastAPI evaluates dependencies before calling the handler body:
1. `require_assets_module` executes first.
2. `require_admin` executes second.
3. If either fails, a `403 Forbidden` exception is raised immediately.
`_load_asset` is never executed for unauthorized callers. Probing arbitrary UUIDs (existing, non-existent, or cross-tenant) always returns `403 Forbidden` to unprivileged callers, completely preventing endpoint exploitation as an existence oracle.

---

## 4. Frontend Hardening

### 4.1 `AssetDetailPage.tsx`
Replace lines 95-96:
```typescript
const isAdmin = profile?.role === 'admin'
const canApprove = isAdmin
const canDispose = isAdmin
```
And gate the button:
```typescript
{canDispose && (
  <Button variant="secondary" size="sm" onClick={() => setDisposalOpen(true)}>
    Dispose Asset
  </Button>
)}
```

### 4.2 `AssetDisposalModal.tsx`
Catch 403 errors specifically:
```typescript
} catch (err) {
  if (err instanceof ApiError && err.status === 403) {
    toast.error(err.message || 'You do not have permission to dispose of assets.')
    onClose()
  } else {
    toast.error(err instanceof Error ? err.message : 'Failed to dispose asset')
  }
}
```

---

## 5. Scope Boundaries

- **In Scope for KUB-020:**
  - `app/routers/assets.py`: Router module dependency, `dispose_asset` admin gate, normalization of `approve_asset` / `reject_asset`, truthful docstring.
  - `frontend/src/pages/company/assets/AssetDetailPage.tsx` and `AssetDisposalModal.tsx`.
  - `tests/test_module_enforcement.py`: Add `/api/v1/assets` to `GATED_ROUTES` and add generic test `test_no_route_has_bare_company_user_without_gate`.
  - Complete 4-category test suite.
- **Explicitly Deferred:**
  - `POST /api/v1/depreciation/runs`: Tracked under KUB-008.
  - `GET /api/v1/custom-fields/{module}`: Tracked under KUB-001.

---

## 6. Comprehensive Test Plan

### Category 1: Pure Unit Tests (`tests/test_asset_validation.py`)
- `test_can_dispose_asset_matrix`: Table-driven tests evaluating `can_dispose_asset(user, asset)` across all permutations of role (`admin`, `employee`) and lifecycle status (`draft`, `ready`, `capitalized`, `disposed`). Verifies that only `(admin, capitalized)` returns `(True, None)`.
- `test_can_dispose_asset_creator_approver_allowed_for_admin`: Verifies that an admin who is both the creator and approver is permitted to dispose of the asset.

### Category 2: Functional / Integration Tests (`tests/test_asset_disposal.py`)
- `test_successful_asset_disposal`: Verify admin happy path continues passing.
- `test_employee_with_assets_module_cannot_dispose`: Employee with `accessible_modules: ["assets"]` receives `403 Insufficient permissions`. Verifies asset remains `capitalized` in the DB.
- `test_employee_with_zero_modules_cannot_dispose`: Employee with `accessible_modules: []` receives `403 No access to the assets module`. Verifies asset remains `capitalized` in the DB.
- `test_employee_with_unrelated_module_cannot_dispose`: Employee with `accessible_modules: ["sales"]` receives `403 No access to the assets module`.

### Category 3: Edge-Case Tests (`tests/test_asset_disposal.py`)
- `test_disposal_auth_checked_before_lifecycle_state`: Non-admin calling dispose on draft/ready/disposed asset receives `403`, not `409`.
- `test_disposal_auth_checked_before_asset_existence`: Non-admin calling dispose on non-existent UUID receives `403`, not `404`.
- `test_disposal_cross_tenant_returns_404_for_admin`: Admin of Company A attempting to dispose Company B's asset receives `404 Not Found`.
- `test_disposal_malformed_uuid_returns_422`: Calling with non-UUID path parameter returns `422`.
- `test_disposal_double_dispose_returns_409`: First call succeeds (200), immediate second call returns `409 Conflict`, leaving original disposal details intact.

### Category 4: Anti-Exploit Tests (`tests/test_asset_disposal.py` & `tests/test_module_enforcement.py`)
- `test_kub_020_zero_module_exploit_prevented`: Reproduces the exact exploit: zero-module employee POSTs valid disposal payload against capitalized asset. Asserts `403`, queries DB to verify `lifecycle_status`, `disposal_date`, `sale_proceeds`, and `disposed_by` are untouched, and asserts zero `asset.disposed` activity logs were recorded.
- `test_kub_020_employee_with_module_exploit_prevented`: Same verification for an employee with the `assets` module.
- `test_assets_router_gated_in_module_enforcement`: In `tests/test_module_enforcement.py`, asserts `"/api/v1/assets"` is in `GATED_ROUTES` and all `/api/v1/assets/*` routes carry the `"assets"` module gate.
- `test_no_route_has_bare_company_user_without_gate`: Generic static reflection test asserting no route in the entire application uses `get_current_company_user` without a module or role gate unless included in `ALLOWED_BARE_ROUTES`.
