import re
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.access_modules import ALL_MODULES, validate_accessible_modules
from tests.conftest import create_test_company, get_company_token

GATED_ROUTES = {
    "/api/v1/docvault": "docvault",
    "/api/v1/auditease": "auditease",
    "/api/v1/sales": "sales",
    "/api/v1/kra": "kra",
    "/api/v1/notifications": "notifications",
    "/api/v1/activity-log": "activity",
}

def test_every_module_router_has_a_server_side_gate():
    """A module listed in the UI must be enforced server-side, not just by
    ModuleGuard.tsx. See KUB-001."""
    from app.main import app

    def guards(route):
        found = set()
        def walk(dep, depth=0):
            if depth > 5:
                return
            for sub in dep.dependencies:
                if getattr(sub.call, "__name__", "") == "checker":
                    for cell in (sub.call.__closure__ or ()):
                        if isinstance(cell.cell_contents, str):
                            found.add(cell.cell_contents)
                walk(sub, depth + 1)
        if getattr(route, "dependant", None):
            walk(route.dependant)
        return found

    missing = []
    for route in app.routes:
        path = getattr(route, "path", "")
        for prefix, module in GATED_ROUTES.items():
            if path.startswith(prefix) and module not in guards(route):
                missing.append((path, module))
    assert not missing, f"endpoints missing their module gate: {missing}"

@pytest.mark.asyncio
async def test_module_gate_behavior(client: AsyncClient):
    """Test that a user with empty accessible_modules gets 403 on gated routes."""
    # 1. Setup company and admin
    await create_test_company(client)
    admin_token = await get_company_token(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Create employee with no modules
    employee_email = "restricted@testco.com"
    employee_password = "Valid1!Pass"
    create_resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": employee_email,
            "password": employee_password,
            "full_name": "Restricted User",
            "role": "employee",
            "accessible_modules": []
        }
    )
    assert create_resp.status_code == 201

    # 3. Login as employee
    login_resp = await client.post(
        "/api/v1/auth/company/login",
        json={"email": employee_email, "password": employee_password}
    )
    assert login_resp.status_code == 200
    emp_token = login_resp.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # 4. Check each module's read endpoint
    endpoints = [
        "/api/v1/docvault/documents",
        "/api/v1/auditease/engagements",
        "/api/v1/sales",
        "/api/v1/kra",
        "/api/v1/notifications",
        "/api/v1/activity-log"
    ]

    for endpoint in endpoints:
        resp = await client.get(endpoint, headers=emp_headers)
        assert resp.status_code == 403, f"Endpoint {endpoint} should be gated (returned {resp.status_code})"


# --- Positive path: the gate must let granted users through, not blanket-deny ---

GATED_READ_ENDPOINTS = {
    "docvault": "/api/v1/docvault/documents",
    "auditease": "/api/v1/auditease/engagements",
    "sales": "/api/v1/sales",
    "kra": "/api/v1/kra",
    "notifications": "/api/v1/notifications",
    "activity": "/api/v1/activity-log",
}


async def _make_employee(client: AsyncClient, admin_headers: dict, email: str, modules: list[str]):
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": email,
            "password": "Valid1!Pass",
            "full_name": email.split("@")[0],
            "role": "employee",
            "accessible_modules": modules,
        },
    )
    assert resp.status_code == 201, resp.text
    login = await client.post(
        "/api/v1/auth/company/login",
        json={"email": email, "password": "Valid1!Pass"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_granted_module_is_reachable_and_others_stay_blocked(client: AsyncClient):
    """The gate must be per-module, not an all-or-nothing switch: granting one
    module opens exactly that module and nothing else."""
    await create_test_company(client)
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client)}"}

    for module, endpoint in GATED_READ_ENDPOINTS.items():
        headers = await _make_employee(client, admin_headers, f"only-{module}@testco.com", [module])

        resp = await client.get(endpoint, headers=headers)
        assert resp.status_code == 200, (
            f"{module} granted but {endpoint} returned {resp.status_code}: {resp.text}"
        )

        for other, other_endpoint in GATED_READ_ENDPOINTS.items():
            if other == module:
                continue
            blocked = await client.get(other_endpoint, headers=headers)
            assert blocked.status_code == 403, (
                f"user granted only {module} reached {other_endpoint} "
                f"({blocked.status_code})"
            )


@pytest.mark.asyncio
async def test_admin_bypasses_every_module_gate(client: AsyncClient):
    """require_module admits admins regardless of accessible_modules; an admin
    locked out of their own tenant would be a worse failure than the bug."""
    await create_test_company(client)
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client)}"}

    for endpoint in GATED_READ_ENDPOINTS.values():
        resp = await client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 200, f"admin blocked on {endpoint}: {resp.text}"


@pytest.mark.asyncio
async def test_gate_rejects_before_authentication_is_bypassed(client: AsyncClient):
    """No token at all must still be rejected — the module gate must not have
    replaced the auth check on these routers."""
    for endpoint in GATED_READ_ENDPOINTS.values():
        resp = await client.get(endpoint)
        assert resp.status_code in (401, 403), f"{endpoint} returned {resp.status_code}"


# --- Write-side validation: an admin cannot grant a module that does not exist ---


@pytest.mark.asyncio
async def test_unknown_module_rejected_on_create_and_update(client: AsyncClient):
    await create_test_company(client)
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client)}"}

    bad = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "typo@testco.com",
            "password": "Valid1!Pass",
            "full_name": "Typo",
            "role": "employee",
            "accessible_modules": ["docvualt"],
        },
    )
    assert bad.status_code == 422, bad.text

    good = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "ok@testco.com",
            "password": "Valid1!Pass",
            "full_name": "Ok",
            "role": "employee",
            "accessible_modules": ["docvault"],
        },
    )
    assert good.status_code == 201, good.text
    user_id = good.json()["id"]

    bad_update = await client.patch(
        f"/api/v1/users/{user_id}",
        headers=admin_headers,
        json={"accessible_modules": ["docvault", "superuser"]},
    )
    assert bad_update.status_code == 422, bad_update.text

    # The rejected write must not have partially applied.
    still = await client.get(f"/api/v1/users/{user_id}", headers=admin_headers)
    assert still.json()["accessible_modules"] == ["docvault"]


@pytest.mark.asyncio
async def test_update_without_modules_key_leaves_grants_untouched(client: AsyncClient):
    """UserUpdate.accessible_modules is optional; the validator must not turn an
    omitted field into a revocation."""
    await create_test_company(client)
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client)}"}

    created = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "keep@testco.com",
            "password": "Valid1!Pass",
            "full_name": "Keep",
            "role": "employee",
            "accessible_modules": ["sales", "kra"],
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    renamed = await client.patch(
        f"/api/v1/users/{user_id}",
        headers=admin_headers,
        json={"full_name": "Keep Renamed"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["accessible_modules"] == ["sales", "kra"]


def test_validate_accessible_modules_unit():
    assert validate_accessible_modules([]) == []
    assert validate_accessible_modules(["sales", "sales"]) == ["sales"]
    # The legacy combined grant must survive validation, not be treated as unknown.
    assert validate_accessible_modules(["compliance"]) == ["roc", "secretarial"]
    with pytest.raises(ValueError):
        validate_accessible_modules(["nope"])
    with pytest.raises(ValueError):
        validate_accessible_modules(["Sales"])  # ids are case-sensitive


# --- Drift guard: the constants only help if both sides agree ---


def test_backend_and_frontend_module_lists_match():
    """ALL_MODULES exists so the gate and MODULE_DEFINITIONS cannot drift apart.
    If they do, an admin can grant a module no router enforces, or vice versa."""
    modules_ts = Path(__file__).parents[1] / "frontend/src/auth/company/modules.ts"
    source = modules_ts.read_text()
    block = source.split("MODULE_DEFINITIONS = [", 1)[1].split("] as const", 1)[0]
    frontend_ids = set(re.findall(r"id:\s*'([^']+)'", block))
    assert frontend_ids == set(ALL_MODULES), (
        f"only in frontend: {sorted(frontend_ids - ALL_MODULES)}; "
        f"only in backend: {sorted(ALL_MODULES - frontend_ids)}"
    )


def test_every_module_id_is_a_named_constant():
    """The gates pass bare strings; those strings must be the canonical ids."""
    for module in GATED_ROUTES.values():
        assert module in ALL_MODULES


# --- An admin must not be able to grant something outside the intended shape,
#     and a non-admin must not be able to grant modules at all. ---


@pytest.mark.asyncio
async def test_non_admin_cannot_create_or_modify_module_grants(client: AsyncClient):
    """accessible_modules is an admin-only lever. An employee — even one who
    somehow obtains another user's id — must not be able to grant themselves
    or anyone else a module via these endpoints."""
    await create_test_company(client)
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client)}"}

    employee_headers = await _make_employee(client, admin_headers, "plain@testco.com", [])

    create_resp = await client.post(
        "/api/v1/users",
        headers=employee_headers,
        json={
            "email": "self-promoted@testco.com",
            "password": "Valid1!Pass",
            "full_name": "Self Promoted",
            "role": "employee",
            "accessible_modules": ["docvault", "auditease", "sales", "kra", "notifications", "activity"],
        },
    )
    assert create_resp.status_code == 403, create_resp.text

    whoami = await client.get("/api/v1/users/me", headers=employee_headers)
    self_id = whoami.json()["id"]
    self_update = await client.patch(
        f"/api/v1/users/{self_id}",
        headers=employee_headers,
        json={"accessible_modules": ["docvault"]},
    )
    assert self_update.status_code == 403, self_update.text


@pytest.mark.asyncio
async def test_malformed_module_payloads_are_rejected(client: AsyncClient):
    """Type coercion and unknown-id validation must both hold: a non-list, a
    non-string element, an empty string, and whitespace/case variants of a
    real id must all fail closed rather than silently normalizing to something
    the admin didn't intend."""
    await create_test_company(client)
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client)}"}

    bad_payloads = [
        {"accessible_modules": "docvault"},          # string instead of list
        {"accessible_modules": [1, 2]},               # non-string elements
        {"accessible_modules": [None]},               # null element
        {"accessible_modules": [""]},                 # empty string
        {"accessible_modules": [" docvault"]},        # leading whitespace
        {"accessible_modules": ["DocVault"]},         # wrong case
        {"accessible_modules": [{"id": "docvault"}]}, # object instead of string
    ]

    for i, extra in enumerate(bad_payloads):
        payload = {
            "email": f"malformed{i}@testco.com",
            "password": "Valid1!Pass",
            "full_name": "Malformed",
            "role": "employee",
            **extra,
        }
        resp = await client.post("/api/v1/users", headers=admin_headers, json=payload)
        assert resp.status_code == 422, f"payload {extra} should be rejected, got {resp.status_code}: {resp.text}"
