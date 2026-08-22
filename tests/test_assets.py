"""P1d — the fixed asset register end to end: quick-add, explode, enrichment,
lifecycle transitions, documents, and the locks that protect capitalized assets.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.asset_helpers import (
    admin_headers,
    make_user,
    set_company_gstin,
    user_headers,
)

ASSETS = "/api/v1/assets"
ACQ = "/api/v1/asset-acquisitions"
MASTERS = "/api/v1/asset-masters"

# Smallest valid PNG, so uploads exercise the real encrypt-then-write path.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


async def _leaf_category(client, headers, name_startswith="End user devices"):
    cats = (await client.get(f"{MASTERS}/categories", headers=headers)).json()
    return next(c for c in cats if c["name"].startswith(name_startswith))


async def _masters(client, headers, supplier_state_gstin="27ABCDE1234F1Z5"):
    """Create the master rows an asset needs to reach `ready`."""
    supplier = (
        await client.post(
            f"{MASTERS}/suppliers",
            json={"code": "SUP1", "name": "Acme Ltd", "gstin": supplier_state_gstin},
            headers=headers,
        )
    ).json()
    out = {"supplier": supplier}
    for kind, name in [
        ("branch", "Head Office"),
        ("cost_centre", "Admin"),
        ("department", "Finance"),
        ("location", "Floor 3"),
    ]:
        out[kind] = (
            await client.post(
                f"{MASTERS}/lookups", json={"kind": kind, "name": name}, headers=headers
            )
        ).json()
    return out


async def _quick_add(client, headers, category_id, **kw):
    body = {"asset_name": "Laptop", "category_id": category_id, "quantity": 1}
    body.update(kw)
    resp = await client.post(f"{ASSETS}/quick-add", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _upload(client, headers, path, doc_role, filename="f.png"):
    resp = await client.post(
        path,
        files={"file": (filename, PNG, "image/png")},
        data={"doc_role": doc_role},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _make_ready(client, headers, created, masters, **asset_overrides):
    """Fill everything needed to submit, then submit. Returns the detail payload."""
    acq_id = created["acquisition_id"]
    asset_id = created["first_asset_id"]

    acq_body = {
        "supplier_id": masters["supplier"]["id"],
        "invoice_number": "INV-001",
        "invoice_date": "2026-04-01",
        "po_number": "PO-001",
        "purchase_date": "2026-04-03",
        "gst_rate": 18,
        "itc_treatment": "eligible",
        "branch_id": masters["branch"]["id"],
    }
    r = await client.patch(f"{ACQ}/{acq_id}", json=acq_body, headers=headers)
    assert r.status_code == 200, r.text

    asset_body = {
        "description": "Developer laptop",
        "manufacturer": "Dell",
        "brand_model": "Latitude 5450",
        "branch_id": masters["branch"]["id"],
        "cost_centre_id": masters["cost_centre"]["id"],
        "department_id": masters["department"]["id"],
        "location_id": masters["location"]["id"],
        "custodian_name": "S. Kulkarni",
        "operational_status": "in_use",
        "condition": "new",
    }
    asset_body.update(asset_overrides)
    r = await client.patch(f"{ASSETS}/{asset_id}", json=asset_body, headers=headers)
    assert r.status_code == 200, r.text

    await _upload(client, headers, f"{ACQ}/{acq_id}/documents/upload", "invoice", "inv.pdf")
    await _upload(client, headers, f"{ASSETS}/{asset_id}/documents/upload", "asset_photo")
    return asset_id, acq_id


# =====================================================================
# Quick add + explode
# =====================================================================

@pytest.mark.asyncio
async def test_quick_add_creates_a_draft_from_six_fields(client: AsyncClient):
    AH = await admin_headers(client, "as_qa@a.com")
    cat = await _leaf_category(client, AH)

    created = await _quick_add(client, AH, cat["id"], unit_basic_price=60000)
    assert created["quantity"] == 1

    detail = (await client.get(f"{ASSETS}/{created['first_asset_id']}", headers=AH)).json()
    asset = detail["asset"]
    assert asset["lifecycle_status"] == "draft"
    assert asset["asset_code"].startswith("COMP-")
    # The category's statutory defaults are applied silently — this is what keeps
    # the create form to six fields.
    assert asset["useful_life_months"] == 36
    assert asset["dep_method"] == "slm"
    assert float(asset["residual_pct"]) == 5.0
    assert float(asset["it_dep_rate"]) == 40.0
    assert asset["it_block_id"] is not None
    # And the field groups the category declares relevant.
    assert "network_ids" in detail["applicable_field_groups"]


@pytest.mark.asyncio
async def test_quantity_fifty_explodes_into_fifty_tagged_units(client: AsyncClient):
    AH = await admin_headers(client, "as_explode@a.com")
    cat = await _leaf_category(client, AH, "General furniture")

    created = await _quick_add(
        client, AH, cat["id"], asset_name="Office chair", quantity=50, unit_basic_price=1000
    )
    assert created["quantity"] == 50
    assert len(created["asset_ids"]) == 50

    units = (await client.get(f"{ACQ}/{created['acquisition_id']}/units", headers=AH)).json()
    assert len(units) == 50
    codes = [u["asset_code"] for u in units]
    assert len(set(codes)) == 50, "tags must be unique"
    assert codes[0].endswith("000001") and codes[49].endswith("000050")
    assert [u["unit_index"] for u in units] == list(range(1, 51))

    # Every unit carries its own allocated cost, and they tie back exactly.
    acquisition = (await client.get(f"{ACQ}/{created['acquisition_id']}", headers=AH)).json()
    total = sum(Decimal(u["original_cost"]) for u in units)
    assert total == Decimal(acquisition["landed_cost"]) == Decimal("50000.00")


@pytest.mark.asyncio
async def test_allocation_has_no_rounding_leak_on_an_awkward_total(client: AsyncClient):
    AH = await admin_headers(client, "as_leak@a.com")
    cat = await _leaf_category(client, AH, "General furniture")
    created = await _quick_add(client, AH, cat["id"], quantity=3, unit_basic_price="333.34")

    units = (await client.get(f"{ACQ}/{created['acquisition_id']}/units", headers=AH)).json()
    acquisition = (await client.get(f"{ACQ}/{created['acquisition_id']}", headers=AH)).json()
    assert sum(Decimal(u["original_cost"]) for u in units) == Decimal(acquisition["landed_cost"])


@pytest.mark.asyncio
async def test_tag_prefixes_come_from_the_category(client: AsyncClient):
    AH = await admin_headers(client, "as_prefix@a.com")
    comp = await _leaf_category(client, AH)
    car = await _leaf_category(client, AH, "Motor cars")

    a = await _quick_add(client, AH, comp["id"])
    b = await _quick_add(client, AH, car["id"], asset_name="Company car")

    da = (await client.get(f"{ASSETS}/{a['first_asset_id']}", headers=AH)).json()["asset"]
    db_ = (await client.get(f"{ASSETS}/{b['first_asset_id']}", headers=AH)).json()["asset"]
    assert da["asset_code"].startswith("COMP-")
    assert db_["asset_code"].startswith("MV-")
    # Counters are per prefix, so both start at 1.
    assert da["asset_code"].endswith("000001")
    assert db_["asset_code"].endswith("000001")


# =====================================================================
# GST and ITC
# =====================================================================

@pytest.mark.asyncio
async def test_gst_splits_by_state_and_flips_to_igst(client: AsyncClient):
    AH = await admin_headers(client, "as_gst@a.com")
    # The company's own GSTIN is the default place of supply (state 27).
    await set_company_gstin("as_gst@a.com", "27AAAAA1111A1Z5")
    cat = await _leaf_category(client, AH)

    # With no supplier at all the state is genuinely unknown, and the split says so
    # rather than pretending — the form uses this to prompt for the missing state.
    unknown = (
        await client.post(
            f"{ASSETS}/cost-preview",
            json={"quantity": 1, "unit_basic_price": 1000, "gst_rate": 18},
            headers=AH,
        )
    ).json()
    assert unknown["gst_split_basis"] == "assumed_intra_state"

    local = (
        await client.post(
            f"{MASTERS}/suppliers",
            json={"code": "MH1", "name": "Mumbai Traders", "gstin": "27ABCDE1234F1Z5"},
            headers=AH,
        )
    ).json()
    same_state = await client.post(
        f"{ASSETS}/cost-preview",
        json={
            "quantity": 1,
            "unit_basic_price": 1000,
            "gst_rate": 18,
            "supplier_id": local["id"],
        },
        headers=AH,
    )
    assert same_state.status_code == 200, same_state.text
    body = same_state.json()
    assert body["gst_split_basis"] == "intra_state"
    assert Decimal(body["cgst_amount"]) == Decimal("90.00")
    assert Decimal(body["sgst_amount"]) == Decimal("90.00")
    assert Decimal(body["igst_amount"]) == Decimal("0.00")

    # A supplier registered in another state makes it inter-state.
    other = (
        await client.post(
            f"{MASTERS}/suppliers",
            json={"code": "KA1", "name": "Bengaluru Traders", "gstin": "29ABCDE1234F1Z5"},
            headers=AH,
        )
    ).json()
    inter = (
        await client.post(
            f"{ASSETS}/cost-preview",
            json={
                "quantity": 1,
                "unit_basic_price": 1000,
                "gst_rate": 18,
                "supplier_id": other["id"],
            },
            headers=AH,
        )
    ).json()
    assert inter["gst_split_basis"] == "inter_state"
    assert Decimal(inter["igst_amount"]) == Decimal("180.00")
    assert Decimal(inter["cgst_amount"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_blocked_itc_lands_in_the_capitalized_value_eligible_does_not(client: AsyncClient):
    AH = await admin_headers(client, "as_itc@a.com")
    car = await _leaf_category(client, AH, "Motor cars")
    laptop = await _leaf_category(client, AH)

    # The Motor cars category defaults ITC to blocked (Sec 17(5)).
    assert car["default_itc_treatment"] == "blocked"

    car_created = await _quick_add(
        client, AH, car["id"], asset_name="Sedan", unit_basic_price=1000000
    )
    r = await client.patch(
        f"{ACQ}/{car_created['acquisition_id']}", json={"gst_rate": 28}, headers=AH
    )
    assert r.status_code == 200, r.text
    car_acq = r.json()
    assert Decimal(car_acq["total_gst"]) == Decimal("280000.00")
    assert Decimal(car_acq["recoverable_gst"]) == Decimal("0.00")
    assert Decimal(car_acq["capitalizable_gst"]) == Decimal("280000.00")
    # GST is part of the depreciation base.
    assert Decimal(car_acq["landed_cost"]) == Decimal("1280000.00")

    laptop_created = await _quick_add(client, AH, laptop["id"], unit_basic_price=1000000)
    laptop_acq = (
        await client.patch(
            f"{ACQ}/{laptop_created['acquisition_id']}",
            json={"gst_rate": 28, "itc_treatment": "eligible"},
            headers=AH,
        )
    ).json()
    assert Decimal(laptop_acq["recoverable_gst"]) == Decimal("280000.00")
    assert Decimal(laptop_acq["capitalizable_gst"]) == Decimal("0.00")
    # ...and here it is not.
    assert Decimal(laptop_acq["landed_cost"]) == Decimal("1000000.00")


@pytest.mark.asyncio
async def test_manually_entered_gst_survives_a_later_recompute(client: AsyncClient):
    AH = await admin_headers(client, "as_ovr@a.com")
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"], unit_basic_price=1000)

    overridden = (
        await client.patch(
            f"{ACQ}/{created['acquisition_id']}",
            json={"gst_rate": 18, "cgst_amount": "89.99", "sgst_amount": "90.01"},
            headers=AH,
        )
    ).json()
    assert overridden["gst_amounts_overridden"] is True
    assert Decimal(overridden["total_gst"]) == Decimal("180.00")

    # An unrelated edit must not silently recompute the amounts back.
    after = (
        await client.patch(
            f"{ACQ}/{created['acquisition_id']}", json={"po_number": "PO-9"}, headers=AH
        )
    ).json()
    assert Decimal(after["cgst_amount"]) == Decimal("89.99")
    assert Decimal(after["sgst_amount"]) == Decimal("90.01")


@pytest.mark.asyncio
async def test_freight_and_installation_are_capitalized(client: AsyncClient):
    AH = await admin_headers(client, "as_freight@a.com")
    cat = await _leaf_category(client, AH, "General plant")
    created = await _quick_add(client, AH, cat["id"], asset_name="Lathe", unit_basic_price=100000)
    acq = (
        await client.patch(
            f"{ACQ}/{created['acquisition_id']}",
            json={
                "gst_rate": 18,
                "itc_treatment": "eligible",
                "freight_cost": 5000,
                "installation_cost": 12000,
                "other_capitalizable_cost": 1000,
            },
            headers=AH,
        )
    ).json()
    assert Decimal(acq["landed_cost"]) == Decimal("118000.00")
    assert Decimal(acq["total_acquisition_outlay"]) == Decimal("136000.00")


# =====================================================================
# Lifecycle
# =====================================================================

@pytest.mark.asyncio
async def test_submit_is_blocked_with_a_full_checklist(client: AsyncClient):
    AH = await admin_headers(client, "as_sub@a.com")
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"])

    resp = await client.post(
        f"{ASSETS}/{created['first_asset_id']}/submit", json={}, headers=AH
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    fields = {i["field"] for i in detail["issues"]}
    assert {"invoice_number", "location_id", "custodian", "doc:invoice", "doc:asset_photo"} <= fields
    # Every issue names the tab that owns it so the UI can deep-link.
    assert all(i["tab"] for i in detail["issues"])


@pytest.mark.asyncio
async def test_a_completed_draft_submits_and_capitalizes(client: AsyncClient):
    AH = await admin_headers(client, "as_flow@a.com")
    masters = await _masters(client, AH)
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"], unit_basic_price=60000)
    asset_id, acq_id = await _make_ready(client, AH, created, masters)

    resp = await client.post(f"{ASSETS}/{asset_id}/submit", json={}, headers=AH)
    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle_status"] == "ready"

    detail = (await client.get(f"{ASSETS}/{asset_id}", headers=AH)).json()
    assert detail["asset"]["submitted_by"] is not None

    # Capitalization needs the dates that start depreciation.
    resp = await client.post(f"{ASSETS}/{asset_id}/approve", json={}, headers=AH)
    assert resp.status_code == 422
    missing = {i["field"] for i in resp.json()["detail"]["issues"]}
    assert {"available_for_use_date", "capitalization_date", "it_put_to_use_date"} <= missing

    await client.patch(
        f"{ASSETS}/{asset_id}",
        json={
            "available_for_use_date": "2026-04-10",
            "capitalization_date": "2026-04-10",
            "it_put_to_use_date": "2026-04-10",
        },
        headers=AH,
    )
    resp = await client.post(f"{ASSETS}/{asset_id}/approve", json={}, headers=AH)
    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle_status"] == "capitalized"

    final = (await client.get(f"{ASSETS}/{asset_id}", headers=AH)).json()["asset"]
    assert final["approved_by"] is not None
    assert Decimal(final["original_cost"]) == Decimal("60000.00")
    # Residual amount is derived from the percentage, not typed.
    assert Decimal(final["residual_value"]) == Decimal("3000.00")


@pytest.mark.asyncio
async def test_a_manager_cannot_approve_their_own_asset(client: AsyncClient):
    AH = await admin_headers(client, "as_sod@a.com")
    await make_user(client, AH, "as_mgr@a.com", role="manager")
    MH = await user_headers(client, "as_mgr@a.com")
    masters = await _masters(client, AH)
    cat = await _leaf_category(client, AH)

    # The manager creates it themselves.
    created = await _quick_add(client, MH, cat["id"], unit_basic_price=60000)
    asset_id, _ = await _make_ready(client, MH, created, masters)
    await client.patch(
        f"{ASSETS}/{asset_id}",
        json={
            "available_for_use_date": "2026-04-10",
            "capitalization_date": "2026-04-10",
            "it_put_to_use_date": "2026-04-10",
        },
        headers=MH,
    )
    await client.post(f"{ASSETS}/{asset_id}/submit", json={}, headers=MH)

    denied = await client.post(f"{ASSETS}/{asset_id}/approve", json={}, headers=MH)
    assert denied.status_code == 403
    assert "cannot approve an asset you created" in denied.json()["detail"]

    # An admin can.
    assert (await client.post(f"{ASSETS}/{asset_id}/approve", json={}, headers=AH)).status_code == 200


@pytest.mark.asyncio
async def test_employees_cannot_approve(client: AsyncClient):
    AH = await admin_headers(client, "as_emp@a.com")
    await make_user(client, AH, "as_e1@a.com")
    EH = await user_headers(client, "as_e1@a.com")
    cat = await _leaf_category(client, AH)
    # An employee with module access CAN create a draft.
    created = await _quick_add(client, EH, cat["id"])
    resp = await client.post(f"{ASSETS}/{created['first_asset_id']}/approve", json={}, headers=EH)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reject_sends_it_back_to_draft(client: AsyncClient):
    AH = await admin_headers(client, "as_rej@a.com")
    masters = await _masters(client, AH)
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"], unit_basic_price=1000)
    asset_id, _ = await _make_ready(client, AH, created, masters)
    await client.post(f"{ASSETS}/{asset_id}/submit", json={}, headers=AH)

    resp = await client.post(f"{ASSETS}/{asset_id}/reject", json={"note": "wrong PO"}, headers=AH)
    assert resp.status_code == 200
    detail = (await client.get(f"{ASSETS}/{asset_id}", headers=AH)).json()["asset"]
    assert detail["lifecycle_status"] == "draft"
    assert detail["submitted_by"] is None


@pytest.mark.asyncio
async def test_a_whole_batch_can_transition_at_once(client: AsyncClient):
    AH = await admin_headers(client, "as_batch@a.com")
    masters = await _masters(client, AH)
    cat = await _leaf_category(client, AH, "General furniture")
    created = await _quick_add(
        client, AH, cat["id"], asset_name="Chair", quantity=3, unit_basic_price=1000
    )
    acq_id = created["acquisition_id"]

    await client.patch(
        f"{ACQ}/{acq_id}",
        json={
            "supplier_id": masters["supplier"]["id"],
            "invoice_number": "INV-9",
            "invoice_date": "2026-04-01",
            "po_number": "PO-9",
            "purchase_date": "2026-04-03",
            "gst_rate": 18,
            "itc_treatment": "eligible",
        },
        headers=AH,
    )
    await _upload(client, AH, f"{ACQ}/{acq_id}/documents/upload", "invoice", "inv.pdf")

    for aid in created["asset_ids"]:
        await client.patch(
            f"{ASSETS}/{aid}",
            json={
                "description": "Stackable chair",
                "manufacturer": "Godrej",
                "brand_model": "GC-1",
                "branch_id": masters["branch"]["id"],
                "cost_centre_id": masters["cost_centre"]["id"],
                "department_id": masters["department"]["id"],
                "location_id": masters["location"]["id"],
                "custodian_name": "Facilities",
                "operational_status": "in_use",
                "condition": "new",
                "available_for_use_date": "2026-04-10",
                "capitalization_date": "2026-04-10",
                "it_put_to_use_date": "2026-04-10",
            },
            headers=AH,
        )
        await _upload(client, AH, f"{ASSETS}/{aid}/documents/upload", "asset_photo")

    resp = await client.post(
        f"{ASSETS}/{created['first_asset_id']}/submit",
        json={"apply_to_siblings": True},
        headers=AH,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["updated"]) == 3

    resp = await client.post(
        f"{ASSETS}/{created['first_asset_id']}/approve",
        json={"apply_to_siblings": True},
        headers=AH,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["updated"]) == 3


# =====================================================================
# Locks after capitalization
# =====================================================================

async def _capitalized(client, headers, email_suffix="x"):
    masters = await _masters(client, headers)
    cat = await _leaf_category(client, headers)
    created = await _quick_add(client, headers, cat["id"], unit_basic_price=60000)
    asset_id, acq_id = await _make_ready(client, headers, created, masters)
    await client.patch(
        f"{ASSETS}/{asset_id}",
        json={
            "available_for_use_date": "2026-04-10",
            "capitalization_date": "2026-04-10",
            "it_put_to_use_date": "2026-04-10",
        },
        headers=headers,
    )
    await client.post(f"{ASSETS}/{asset_id}/submit", json={}, headers=headers)
    r = await client.post(f"{ASSETS}/{asset_id}/approve", json={}, headers=headers)
    assert r.status_code == 200, r.text
    return asset_id, acq_id


@pytest.mark.asyncio
async def test_the_tag_is_immutable_once_capitalized(client: AsyncClient):
    AH = await admin_headers(client, "as_lock1@a.com")
    asset_id, _ = await _capitalized(client, AH)

    resp = await client.patch(f"{ASSETS}/{asset_id}", json={"asset_code": "NEW-1"}, headers=AH)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cost_and_depreciation_inputs_are_locked_once_capitalized(client: AsyncClient):
    AH = await admin_headers(client, "as_lock2@a.com")
    asset_id, acq_id = await _capitalized(client, AH)

    # Unit-level depreciation inputs.
    resp = await client.patch(f"{ASSETS}/{asset_id}", json={"useful_life_months": 60}, headers=AH)
    assert resp.status_code == 409
    assert "useful_life_months" in resp.json()["detail"]["locked_fields"]

    # Acquisition-level cost.
    resp = await client.patch(f"{ACQ}/{acq_id}", json={"unit_basic_price": 99999}, headers=AH)
    assert resp.status_code == 409
    assert "unit_basic_price" in resp.json()["detail"]["locked_fields"]

    # But operational facts still move freely.
    resp = await client.patch(
        f"{ASSETS}/{asset_id}", json={"condition": "fair", "remarks": "scratched"}, headers=AH
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_a_capitalized_asset_cannot_be_deleted(client: AsyncClient):
    AH = await admin_headers(client, "as_del@a.com")
    asset_id, _ = await _capitalized(client, AH)
    resp = await client.delete(f"{ASSETS}/{asset_id}", headers=AH)
    assert resp.status_code == 409
    assert "disposed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_a_draft_can_be_deleted(client: AsyncClient):
    AH = await admin_headers(client, "as_del2@a.com")
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"])
    assert (await client.delete(f"{ASSETS}/{created['first_asset_id']}", headers=AH)).status_code == 204
    assert (await client.get(f"{ASSETS}/{created['first_asset_id']}", headers=AH)).status_code == 404


# =====================================================================
# Batch editing
# =====================================================================

@pytest.mark.asyncio
async def test_serials_can_be_filled_for_a_batch_in_one_call(client: AsyncClient):
    AH = await admin_headers(client, "as_ser@a.com")
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"], quantity=3, unit_basic_price=1000)

    resp = await client.post(
        f"{ASSETS}/{created['first_asset_id']}/serials",
        json={
            "assignments": [
                {"asset_id": created["asset_ids"][0], "manufacturer_serial_number": "SN-A"},
                {"asset_id": created["asset_ids"][1], "manufacturer_serial_number": "SN-B"},
                {"asset_id": created["asset_ids"][2], "manufacturer_serial_number": "SN-C"},
            ]
        },
        headers=AH,
    )
    assert resp.status_code == 200, resp.text
    units = (await client.get(f"{ACQ}/{created['acquisition_id']}/units", headers=AH)).json()
    assert {u["manufacturer_serial_number"] for u in units} == {"SN-A", "SN-B", "SN-C"}


@pytest.mark.asyncio
async def test_duplicate_asset_codes_are_rejected(client: AsyncClient):
    AH = await admin_headers(client, "as_dupcode@a.com")
    cat = await _leaf_category(client, AH)
    a = await _quick_add(client, AH, cat["id"])
    b = await _quick_add(client, AH, cat["id"])

    a_code = (await client.get(f"{ASSETS}/{a['first_asset_id']}", headers=AH)).json()["asset"][
        "asset_code"
    ]
    resp = await client.patch(
        f"{ASSETS}/{b['first_asset_id']}", json={"asset_code": a_code.lower()}, headers=AH
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_growing_the_quantity_mints_new_units(client: AsyncClient):
    AH = await admin_headers(client, "as_grow@a.com")
    cat = await _leaf_category(client, AH, "General furniture")
    created = await _quick_add(client, AH, cat["id"], quantity=2, unit_basic_price=1000)

    resp = await client.patch(f"{ACQ}/{created['acquisition_id']}", json={"quantity": 5}, headers=AH)
    assert resp.status_code == 200, resp.text
    units = (await client.get(f"{ACQ}/{created['acquisition_id']}/units", headers=AH)).json()
    assert len(units) == 5
    assert [u["unit_index"] for u in units] == [1, 2, 3, 4, 5]
    assert len({u["asset_code"] for u in units}) == 5
    acq = (await client.get(f"{ACQ}/{created['acquisition_id']}", headers=AH)).json()
    assert sum(Decimal(u["original_cost"]) for u in units) == Decimal(acq["landed_cost"])


@pytest.mark.asyncio
async def test_shrinking_the_quantity_drops_trailing_drafts(client: AsyncClient):
    AH = await admin_headers(client, "as_shrink@a.com")
    cat = await _leaf_category(client, AH, "General furniture")
    created = await _quick_add(client, AH, cat["id"], quantity=5, unit_basic_price=1000)

    resp = await client.patch(f"{ACQ}/{created['acquisition_id']}", json={"quantity": 2}, headers=AH)
    assert resp.status_code == 200, resp.text
    units = (await client.get(f"{ACQ}/{created['acquisition_id']}/units", headers=AH)).json()
    assert len(units) == 2
    assert [u["unit_index"] for u in units] == [1, 2]


# =====================================================================
# Documents
# =====================================================================

@pytest.mark.asyncio
async def test_the_invoice_attaches_once_and_covers_every_unit(client: AsyncClient):
    AH = await admin_headers(client, "as_doc1@a.com")
    cat = await _leaf_category(client, AH, "General furniture")
    created = await _quick_add(client, AH, cat["id"], quantity=3, unit_basic_price=1000)

    await _upload(
        client, AH, f"{ACQ}/{created['acquisition_id']}/documents/upload", "invoice", "inv.pdf"
    )
    # All three units see it without three copies being stored.
    for aid in created["asset_ids"]:
        docs = (await client.get(f"{ASSETS}/{aid}/documents", headers=AH)).json()
        assert [d["doc_role"] for d in docs] == ["invoice"]


@pytest.mark.asyncio
async def test_document_roles_are_kept_at_the_right_level(client: AsyncClient):
    AH = await admin_headers(client, "as_doc2@a.com")
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"])
    asset_id = created["first_asset_id"]
    acq_id = created["acquisition_id"]

    # An invoice on a single unit is a modelling error — it belongs to the batch.
    bad = await client.post(
        f"{ASSETS}/{asset_id}/documents/upload",
        files={"file": ("inv.pdf", PNG, "application/pdf")},
        data={"doc_role": "invoice"},
        headers=AH,
    )
    assert bad.status_code == 400
    assert "shared paperwork" in bad.json()["detail"]

    # A photograph on the batch is equally wrong — photos are per unit.
    bad = await client.post(
        f"{ACQ}/{acq_id}/documents/upload",
        files={"file": ("p.png", PNG, "image/png")},
        data={"doc_role": "asset_photo"},
        headers=AH,
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_an_uploaded_photo_can_be_streamed_back_decrypted(client: AsyncClient):
    AH = await admin_headers(client, "as_doc3@a.com")
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"])
    link = await _upload(
        client, AH, f"{ASSETS}/{created['first_asset_id']}/documents/upload", "asset_photo"
    )

    resp = await client.get(f"/api/v1/asset-documents/{link['id']}/thumbnail", headers=AH)
    assert resp.status_code == 200, resp.text
    # Round-trips through AES-256-GCM byte for byte.
    assert resp.content == PNG
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.headers["content-disposition"].startswith("inline")


@pytest.mark.asyncio
async def test_an_attachment_can_be_detached(client: AsyncClient):
    AH = await admin_headers(client, "as_doc4@a.com")
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"])
    link = await _upload(
        client, AH, f"{ASSETS}/{created['first_asset_id']}/documents/upload", "asset_photo"
    )
    assert (
        await client.delete(f"/api/v1/asset-documents/{link['id']}", headers=AH)
    ).status_code == 204
    docs = (await client.get(f"{ASSETS}/{created['first_asset_id']}/documents", headers=AH)).json()
    assert docs == []


# =====================================================================
# Scoping and permissions
# =====================================================================

@pytest.mark.asyncio
async def test_the_register_is_visible_to_every_module_holder(client: AsyncClient):
    """A finance artifact: totals must tie, so reads are not narrowed by custodian."""
    AH = await admin_headers(client, "as_scope@a.com")
    await make_user(client, AH, "as_s1@a.com")
    EH = await user_headers(client, "as_s1@a.com")
    cat = await _leaf_category(client, AH)

    await _quick_add(client, AH, cat["id"], asset_name="Admin laptop")
    await _quick_add(client, AH, cat["id"], asset_name="Someone else's laptop")

    listed = (await client.get(ASSETS, headers=EH)).json()
    assert len(listed) == 2


@pytest.mark.asyncio
async def test_assets_are_tenant_isolated(client: AsyncClient):
    A = await admin_headers(client, "as_t1@a.com")
    B = await admin_headers(client, "as_t2@b.com")
    cat = await _leaf_category(client, A)
    created = await _quick_add(client, A, cat["id"], asset_name="A-only")

    assert (await client.get(ASSETS, headers=B)).json() == []
    assert (await client.get(f"{ASSETS}/{created['first_asset_id']}", headers=B)).status_code == 404
    assert (
        await client.get(f"{ACQ}/{created['acquisition_id']}", headers=B)
    ).status_code == 404


@pytest.mark.asyncio
async def test_module_access_is_required_server_side(client: AsyncClient):
    AH = await admin_headers(client, "as_mod@a.com")
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": "as_nomod@a.com",
            "password": "pass1234",
            "full_name": "No Module",
            "role": "employee",
            "accessible_modules": [],
        },
        headers=AH,
    )
    assert resp.status_code == 201
    NH = await user_headers(client, "as_nomod@a.com")
    assert (await client.get(ASSETS, headers=NH)).status_code == 403


# =====================================================================
# Misc
# =====================================================================

@pytest.mark.asyncio
async def test_custom_fields_still_validate(client: AsyncClient):
    AH = await admin_headers(client, "as_cf@a.com")
    await client.post(
        "/api/v1/custom-fields/asset_management",
        json={
            "field_name": "Region",
            "field_key": "region",
            "field_type": "dropdown",
            "dropdown_options": ["North", "South"],
            "is_required": True,
        },
        headers=AH,
    )
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"])

    bad = await client.patch(
        f"{ASSETS}/{created['first_asset_id']}",
        json={"custom_fields": {"region": "West"}},
        headers=AH,
    )
    assert bad.status_code == 400
    assert "custom_field_errors" in bad.json()["detail"]

    ok = await client.patch(
        f"{ASSETS}/{created['first_asset_id']}",
        json={"custom_fields": {"region": "North"}},
        headers=AH,
    )
    assert ok.status_code == 200
    assert ok.json()["custom_fields"]["region"] == "North"


@pytest.mark.asyncio
async def test_lifecycle_transitions_are_written_to_the_activity_log(client: AsyncClient):
    """The old assets router logged nothing at all."""
    AH = await admin_headers(client, "as_log@a.com")
    asset_id, _ = await _capitalized(client, AH)

    resp = await client.get("/api/v1/activity-log", headers=AH)
    assert resp.status_code == 200, resp.text
    actions = {entry["action"] for entry in resp.json()}
    assert {"asset.created", "asset.submitted", "asset.capitalized"} <= actions

    # The capitalization entry records the figure that entered the books.
    entry = next(e for e in resp.json() if e["action"] == "asset.capitalized")
    assert entry["entity_id"] == str(asset_id)

    # Each unit's own trail starts at its creation, so filtering to one asset does
    # not begin mid-story at the first edit.
    scoped = await client.get(f"/api/v1/activity-log?entity_id={asset_id}", headers=AH)
    assert {e["action"] for e in scoped.json()} >= {
        "asset.created",
        "asset.submitted",
        "asset.capitalized",
    }


@pytest.mark.asyncio
async def test_warranty_expiry_is_derived(client: AsyncClient):
    AH = await admin_headers(client, "as_warr@a.com")
    cat = await _leaf_category(client, AH)
    created = await _quick_add(client, AH, cat["id"])
    resp = await client.patch(
        f"{ASSETS}/{created['first_asset_id']}",
        json={"warranty_start_date": "2026-01-15", "warranty_months": 24},
        headers=AH,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["warranty_expiry_date"] == "2028-01-14"


@pytest.mark.asyncio
async def test_filters_and_search(client: AsyncClient):
    AH = await admin_headers(client, "as_filter@a.com")
    comp = await _leaf_category(client, AH)
    furn = await _leaf_category(client, AH, "General furniture")
    await _quick_add(client, AH, comp["id"], asset_name="Thinkpad X1")
    await _quick_add(client, AH, furn["id"], asset_name="Desk")

    assert len((await client.get(f"{ASSETS}?category_id={comp['id']}", headers=AH)).json()) == 1
    assert len((await client.get(f"{ASSETS}?search=thinkpad", headers=AH)).json()) == 1
    assert len((await client.get(f"{ASSETS}?lifecycle_status=draft", headers=AH)).json()) == 2
    assert len((await client.get(f"{ASSETS}?lifecycle_status=capitalized", headers=AH)).json()) == 0


@pytest.mark.asyncio
async def test_export_produces_a_spreadsheet(client: AsyncClient):
    AH = await admin_headers(client, "as_exp@a.com")
    cat = await _leaf_category(client, AH)
    await _quick_add(client, AH, cat["id"])
    resp = await client.get(f"{ASSETS}/export/excel", headers=AH)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]
    assert len(resp.content) > 0
