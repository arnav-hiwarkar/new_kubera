"""P1a — fixed-asset master data: categories, IT blocks, suppliers, lookups."""
import pytest
from httpx import AsyncClient

from tests.asset_helpers import admin_headers, make_user, seed_masters, user_headers

MASTERS = "/api/v1/asset-masters"


@pytest.mark.asyncio
async def test_seeded_globals_visible_to_every_company(client: AsyncClient):
    await seed_masters()
    AH = await admin_headers(client, "am_seed@a.com")

    blocks = (await client.get(f"{MASTERS}/it-blocks", headers=AH)).json()
    by_code = {b["code"]: b for b in blocks}
    # Statutory Appendix I rates we must not get wrong.
    assert by_code["PM-40-COMP"]["dep_rate"] == 40.0
    assert by_code["PM-15"]["dep_rate"] == 15.0
    assert by_code["BLD-10"]["dep_rate"] == 10.0
    assert by_code["INT-25"]["dep_rate"] == 25.0
    # Seeded rows are global, not owned by the company.
    assert all(b["company_id"] is None for b in blocks)

    cats = (await client.get(f"{MASTERS}/categories", headers=AH)).json()
    parents = [c for c in cats if c["parent_id"] is None]
    assert {"Buildings", "Motor vehicles", "Computers and data processing units"} <= {
        c["name"] for c in parents
    }

    # A leaf carries the depreciation defaults that make the create form short.
    laptops = next(c for c in cats if c["name"] == "End user devices (desktops, laptops, printers)")
    assert laptops["default_useful_life_months"] == 36
    assert laptops["default_dep_method"] == "slm"
    assert laptops["default_residual_pct"] == 5.0
    assert laptops["tag_prefix"] == "COMP"
    assert laptops["default_it_block_code"] == "PM-40-COMP"
    assert "network_ids" in laptops["applicable_field_groups"]

    # Motor cars default to blocked ITC — Sec 17(5) — which is the whole reason
    # the category carries an ITC default.
    cars = next(c for c in cats if c["name"].startswith("Motor cars"))
    assert cars["default_itc_treatment"] == "blocked"
    assert "registration" in cars["applicable_field_groups"]


@pytest.mark.asyncio
async def test_category_two_level_depth_enforced(client: AsyncClient):
    AH = await admin_headers(client, "am_depth@a.com")

    parent = await client.post(
        f"{MASTERS}/categories", json={"name": "Tooling"}, headers=AH
    )
    assert parent.status_code == 201, parent.text
    pid = parent.json()["id"]

    child = await client.post(
        f"{MASTERS}/categories",
        json={
            "name": "Jigs and fixtures",
            "parent_id": pid,
            "default_useful_life_months": 180,
            "default_dep_method": "wdv",
            "default_residual_pct": 5,
            "tag_prefix": "TOOL",
        },
        headers=AH,
    )
    assert child.status_code == 201, child.text
    cid = child.json()["id"]

    # Third level is rejected: the tree is category -> subcategory only.
    grandchild = await client.post(
        f"{MASTERS}/categories", json={"name": "Deeper", "parent_id": cid}, headers=AH
    )
    assert grandchild.status_code == 400
    assert "two level" in grandchild.json()["detail"].lower()


@pytest.mark.asyncio
async def test_category_duplicate_name_under_same_parent_rejected(client: AsyncClient):
    AH = await admin_headers(client, "am_dup@a.com")
    p = (await client.post(f"{MASTERS}/categories", json={"name": "Plant"}, headers=AH)).json()

    first = await client.post(
        f"{MASTERS}/categories", json={"name": "Lathes", "parent_id": p["id"]}, headers=AH
    )
    assert first.status_code == 201
    # Case-insensitive duplicate under the same parent.
    dup = await client.post(
        f"{MASTERS}/categories", json={"name": "lathes", "parent_id": p["id"]}, headers=AH
    )
    assert dup.status_code == 409
    # Same name under a different parent is fine.
    p2 = (await client.post(f"{MASTERS}/categories", json={"name": "Workshop"}, headers=AH)).json()
    ok = await client.post(
        f"{MASTERS}/categories", json={"name": "Lathes", "parent_id": p2["id"]}, headers=AH
    )
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_global_rows_not_writable_by_a_company(client: AsyncClient):
    await seed_masters()
    AH = await admin_headers(client, "am_global@a.com")
    cats = (await client.get(f"{MASTERS}/categories", headers=AH)).json()
    global_cat = next(c for c in cats if c["company_id"] is None)

    patch = await client.patch(
        f"{MASTERS}/categories/{global_cat['id']}",
        json={"default_useful_life_months": 999},
        headers=AH,
    )
    assert patch.status_code == 403
    assert "seeded" in patch.json()["detail"].lower()


@pytest.mark.asyncio
async def test_supplier_crud_gstin_and_state_code(client: AsyncClient):
    AH = await admin_headers(client, "am_sup@a.com")

    bad = await client.post(
        f"{MASTERS}/suppliers",
        json={"code": "S1", "name": "Bad GST Traders", "gstin": "NOTAGSTIN"},
        headers=AH,
    )
    assert bad.status_code == 422

    ok = await client.post(
        f"{MASTERS}/suppliers",
        json={
            "code": "s-001",
            "name": "Acme Furnishings",
            # lower case on the way in; stored upper-cased
            "gstin": "27abcde1234f1z5",
            "contact_person": "R. Rao",
            "email": "sales@acme.test",
            "state": "Maharashtra",
        },
        headers=AH,
    )
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["gstin"] == "27ABCDE1234F1Z5"
    # State code is derived from the GSTIN, not typed by the user — it drives the
    # CGST/SGST vs IGST decision.
    assert body["state_code"] == "27"

    dup = await client.post(
        f"{MASTERS}/suppliers", json={"code": "S-001", "name": "Other"}, headers=AH
    )
    assert dup.status_code == 409

    listed = (await client.get(f"{MASTERS}/suppliers", headers=AH)).json()
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_lookups_are_scoped_per_kind(client: AsyncClient):
    AH = await admin_headers(client, "am_look@a.com")

    for kind, name in [
        ("branch", "Head Office"),
        ("cost_centre", "Admin"),
        ("department", "Finance"),
        ("location", "Pune Plant"),
    ]:
        resp = await client.post(
            f"{MASTERS}/lookups", json={"kind": kind, "name": name}, headers=AH
        )
        assert resp.status_code == 201, resp.text

    branches = (await client.get(f"{MASTERS}/lookups?kind=branch", headers=AH)).json()
    assert [b["name"] for b in branches] == ["Head Office"]

    # Same name, different kind -> allowed.
    assert (
        await client.post(
            f"{MASTERS}/lookups", json={"kind": "location", "name": "Head Office"}, headers=AH
        )
    ).status_code == 201
    # Same name, same kind, different case -> rejected.
    assert (
        await client.post(
            f"{MASTERS}/lookups", json={"kind": "branch", "name": "head office"}, headers=AH
        )
    ).status_code == 409


@pytest.mark.asyncio
async def test_branch_lookup_carries_state_for_place_of_supply(client: AsyncClient):
    AH = await admin_headers(client, "am_branch@a.com")
    resp = await client.post(
        f"{MASTERS}/lookups",
        json={"kind": "branch", "name": "Bengaluru Office", "gstin": "29ABCDE1234F1Z5"},
        headers=AH,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["state_code"] == "29"


@pytest.mark.asyncio
async def test_location_lookup_supports_hierarchy(client: AsyncClient):
    AH = await admin_headers(client, "am_loc@a.com")
    site = (
        await client.post(
            f"{MASTERS}/lookups", json={"kind": "location", "name": "Pune Plant"}, headers=AH
        )
    ).json()
    room = await client.post(
        f"{MASTERS}/lookups",
        json={"kind": "location", "name": "Shop Floor A", "parent_id": site["id"]},
        headers=AH,
    )
    assert room.status_code == 201, room.text
    assert room.json()["parent_id"] == site["id"]

    # A parent of a different kind is nonsense and must be rejected.
    dept = (
        await client.post(
            f"{MASTERS}/lookups", json={"kind": "department", "name": "Ops"}, headers=AH
        )
    ).json()
    bad = await client.post(
        f"{MASTERS}/lookups",
        json={"kind": "location", "name": "Orphan", "parent_id": dept["id"]},
        headers=AH,
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_masters_are_tenant_isolated_but_share_globals(client: AsyncClient):
    await seed_masters()
    A = await admin_headers(client, "am_t1@a.com")
    B = await admin_headers(client, "am_t2@b.com")

    await client.post(f"{MASTERS}/suppliers", json={"code": "X", "name": "A-only"}, headers=A)
    await client.post(f"{MASTERS}/lookups", json={"kind": "branch", "name": "A-HO"}, headers=A)

    assert (await client.get(f"{MASTERS}/suppliers", headers=B)).json() == []
    assert (await client.get(f"{MASTERS}/lookups?kind=branch", headers=B)).json() == []
    # ...but both see the same seeded global blocks.
    assert len((await client.get(f"{MASTERS}/it-blocks", headers=B)).json()) == len(
        (await client.get(f"{MASTERS}/it-blocks", headers=A)).json()
    )


@pytest.mark.asyncio
async def test_masters_writes_are_admin_only_reads_are_not(client: AsyncClient):
    AH = await admin_headers(client, "am_perm@a.com")
    await make_user(client, AH, "am_emp@a.com")
    EH = await user_headers(client, "am_emp@a.com")

    await client.post(f"{MASTERS}/suppliers", json={"code": "S", "name": "Readable"}, headers=AH)

    # Employee with module access can read the masters (needed to fill the form)...
    got = await client.get(f"{MASTERS}/suppliers", headers=EH)
    assert got.status_code == 200
    assert len(got.json()) == 1
    # ...but cannot create them.
    assert (
        await client.post(f"{MASTERS}/suppliers", json={"code": "N", "name": "No"}, headers=EH)
    ).status_code == 403
    assert (
        await client.post(f"{MASTERS}/categories", json={"name": "No"}, headers=EH)
    ).status_code == 403


@pytest.mark.asyncio
async def test_module_access_enforced_server_side(client: AsyncClient):
    """accessible_modules was previously browser-only. Asset endpoints check it."""
    AH = await admin_headers(client, "am_mod@a.com")
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": "am_nomod@a.com",
            "password": "pass1234",
            "full_name": "No Module",
            "role": "employee",
            "accessible_modules": [],  # deliberately not granted 'assets'
        },
        headers=AH,
    )
    assert resp.status_code == 201
    NH = await user_headers(client, "am_nomod@a.com")
    assert (await client.get(f"{MASTERS}/suppliers", headers=NH)).status_code == 403


@pytest.mark.asyncio
async def test_seed_is_idempotent(client: AsyncClient):
    await seed_masters()
    AH = await admin_headers(client, "am_idem@a.com")
    first = len((await client.get(f"{MASTERS}/categories", headers=AH)).json())
    await seed_masters()
    second = len((await client.get(f"{MASTERS}/categories", headers=AH)).json())
    assert first == second
