"""P1b — three-tier required-field validation and derived-date rules.

Pure functions over unsaved ORM instances: no session needed, so column defaults
are set explicitly here the way the router does before validating.
"""
from datetime import date
from decimal import Decimal
import uuid

import pytest

from app.models.asset_masters import AssetCategory, DepreciationMethod, ItcTreatment
from app.models.assets import (
    Asset,
    AssetAcquisition,
    AssetCondition,
    AssetDocRole,
    AssetLifecycleStatus,
    AssetOperationalStatus,
)
from app.models.company import CompanyUser, UserRole
from app.services.asset_validation import can_dispose_asset, validate_transition

D = Decimal


def _complete_acquisition(**kw) -> AssetAcquisition:
    a = AssetAcquisition(
        supplier_id="00000000-0000-0000-0000-000000000001",
        invoice_number="INV-1",
        invoice_date=date(2026, 4, 1),
        po_number="PO-1",
        purchase_date=date(2026, 4, 3),
        quantity=1,
        unit_basic_price=D("1000.00"),
        gst_rate=D("18"),
        itc_treatment=ItcTreatment.eligible,
    )
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _complete_asset(**kw) -> Asset:
    a = Asset(
        asset_name="Laptop",
        category_id="00000000-0000-0000-0000-0000000000c1",
        lifecycle_status=AssetLifecycleStatus.draft,
        description="Dev laptop",
        manufacturer="Dell",
        brand_model="Latitude 5450",
        branch_id="00000000-0000-0000-0000-0000000000b1",
        cost_centre_id="00000000-0000-0000-0000-0000000000c2",
        department_id="00000000-0000-0000-0000-0000000000d1",
        location_id="00000000-0000-0000-0000-0000000000e1",
        custodian_id="00000000-0000-0000-0000-0000000000f1",
        operational_status=AssetOperationalStatus.in_use,
        condition=AssetCondition.new,
        useful_life_months=36,
        dep_method=DepreciationMethod.slm,
        residual_pct=D("5"),
        it_block_id="00000000-0000-0000-0000-00000000ab01",
        it_dep_rate=D("40"),
        original_cost=D("1000.00"),
    )
    for k, v in kw.items():
        setattr(a, k, v)
    return a


_ALL_DOCS = {AssetDocRole.invoice, AssetDocRole.asset_photo}


def _fields(issues):
    return {i.field for i in issues}


# === Tier 1: draft ===

def test_draft_needs_only_name_and_category():
    bare = Asset(asset_name="Chair", category_id="00000000-0000-0000-0000-0000000000c1")
    assert validate_transition(bare, AssetAcquisition(quantity=1), AssetLifecycleStatus.draft) == []


def test_draft_still_rejects_a_missing_name():
    issues = validate_transition(
        Asset(asset_name="", category_id="00000000-0000-0000-0000-0000000000c1"),
        AssetAcquisition(quantity=1),
        AssetLifecycleStatus.draft,
    )
    assert "asset_name" in _fields(issues)


def test_draft_rejects_a_missing_category():
    issues = validate_transition(
        Asset(asset_name="Chair"), AssetAcquisition(quantity=1), AssetLifecycleStatus.draft
    )
    assert "category_id" in _fields(issues)


# === Tier 2: ready ===

def test_a_bare_draft_cannot_go_straight_to_ready():
    issues = validate_transition(
        Asset(asset_name="Chair", category_id="00000000-0000-0000-0000-0000000000c1"),
        AssetAcquisition(quantity=1),
        AssetLifecycleStatus.ready,
    )
    missing = _fields(issues)
    # Commercial fields
    assert {"invoice_number", "invoice_date", "purchase_date", "unit_basic_price"} <= missing
    # Statutory fields
    assert {"useful_life_months", "dep_method", "it_block_id", "it_dep_rate"} <= missing
    # Assignment
    assert {"location_id", "custodian", "operational_status", "condition"} <= missing
    # Every issue carries the tab that owns it, so the UI can deep-link.
    assert all(i.tab for i in issues)


def test_a_complete_asset_passes_ready():
    assert (
        validate_transition(
            _complete_asset(),
            _complete_acquisition(),
            AssetLifecycleStatus.ready,
            present_doc_roles=_ALL_DOCS,
        )
        == []
    )


def test_custodian_can_be_satisfied_by_a_free_text_name():
    """A machine operator with no login must still be able to hold an asset."""
    asset = _complete_asset(custodian_id=None, custodian_name="S. Kulkarni")
    issues = validate_transition(
        asset, _complete_acquisition(), AssetLifecycleStatus.ready, present_doc_roles=_ALL_DOCS
    )
    assert "custodian" not in _fields(issues)

    neither = _complete_asset(custodian_id=None, custodian_name=None)
    issues = validate_transition(
        neither, _complete_acquisition(), AssetLifecycleStatus.ready, present_doc_roles=_ALL_DOCS
    )
    assert "custodian" in _fields(issues)


def test_ready_requires_the_invoice_and_a_photograph():
    issues = validate_transition(
        _complete_asset(), _complete_acquisition(), AssetLifecycleStatus.ready, present_doc_roles=set()
    )
    assert {"doc:invoice", "doc:asset_photo"} <= _fields(issues)

    issues = validate_transition(
        _complete_asset(),
        _complete_acquisition(),
        AssetLifecycleStatus.ready,
        present_doc_roles={AssetDocRole.invoice},
    )
    assert _fields(issues) == {"doc:asset_photo"}


def test_partial_itc_requires_its_percentage_at_ready():
    acq = _complete_acquisition(itc_treatment=ItcTreatment.partial)
    issues = validate_transition(
        _complete_asset(), acq, AssetLifecycleStatus.ready, present_doc_roles=_ALL_DOCS
    )
    assert "itc_eligible_pct" in _fields(issues)


def test_overriding_schedule_ii_useful_life_requires_a_reason():
    """Schedule II permits a different life but requires the reason to be disclosed."""
    category = AssetCategory(name="End user devices", default_useful_life_months=36)
    # Matching the default: no reason needed.
    ok = validate_transition(
        _complete_asset(useful_life_months=36),
        _complete_acquisition(),
        AssetLifecycleStatus.ready,
        present_doc_roles=_ALL_DOCS,
        category=category,
    )
    assert ok == []
    # Diverging without a reason: rejected.
    issues = validate_transition(
        _complete_asset(useful_life_months=60),
        _complete_acquisition(),
        AssetLifecycleStatus.ready,
        present_doc_roles=_ALL_DOCS,
        category=category,
    )
    assert "useful_life_override_reason" in _fields(issues)
    # With a reason: accepted.
    ok = validate_transition(
        _complete_asset(useful_life_months=60, useful_life_override_reason="Extended OEM support"),
        _complete_acquisition(),
        AssetLifecycleStatus.ready,
        present_doc_roles=_ALL_DOCS,
        category=category,
    )
    assert ok == []


# === Tier 3: capitalized ===

def test_capitalization_requires_the_dates_that_start_depreciation():
    issues = validate_transition(
        _complete_asset(),
        _complete_acquisition(),
        AssetLifecycleStatus.capitalized,
        present_doc_roles=_ALL_DOCS,
    )
    assert {"available_for_use_date", "capitalization_date", "it_put_to_use_date"} <= _fields(issues)


def test_capitalization_passes_with_dates_and_a_cost():
    asset = _complete_asset(
        available_for_use_date=date(2026, 4, 10),
        capitalization_date=date(2026, 4, 10),
        it_put_to_use_date=date(2026, 4, 10),
    )
    assert (
        validate_transition(
            asset, _complete_acquisition(), AssetLifecycleStatus.capitalized, present_doc_roles=_ALL_DOCS
        )
        == []
    )


def test_capitalization_requires_a_cost_greater_than_zero():
    asset = _complete_asset(
        available_for_use_date=date(2026, 4, 10),
        capitalization_date=date(2026, 4, 10),
        it_put_to_use_date=date(2026, 4, 10),
        original_cost=D("0.00"),
    )
    issues = validate_transition(
        asset, _complete_acquisition(), AssetLifecycleStatus.capitalized, present_doc_roles=_ALL_DOCS
    )
    assert "original_cost" in _fields(issues)


# === Date ordering ===

@pytest.mark.parametrize(
    "kw,bad_field",
    [
        ({"available_for_use_date": date(2026, 3, 1)}, "available_for_use_date"),
        ({"capitalization_date": date(2026, 4, 5)}, "capitalization_date"),
    ],
)
def test_dates_must_be_in_a_sensible_order(kw, bad_field):
    """Available-for-use cannot precede purchase; capitalization cannot precede
    available-for-use."""
    base = dict(
        available_for_use_date=date(2026, 4, 10),
        capitalization_date=date(2026, 4, 10),
        it_put_to_use_date=date(2026, 4, 10),
    )
    base.update(kw)
    issues = validate_transition(
        _complete_asset(**base),
        _complete_acquisition(purchase_date=date(2026, 4, 3)),
        AssetLifecycleStatus.capitalized,
        present_doc_roles=_ALL_DOCS,
    )
    assert bad_field in _fields(issues)
    assert any(i.kind == "invalid" for i in issues)


def test_invoice_date_after_purchase_date_is_rejected():
    issues = validate_transition(
        _complete_asset(),
        _complete_acquisition(invoice_date=date(2026, 5, 1), purchase_date=date(2026, 4, 3)),
        AssetLifecycleStatus.ready,
        present_doc_roles=_ALL_DOCS,
    )
    assert "invoice_date" in _fields(issues)


def test_pre_cutover_assets_must_declare_opening_balances():
    asset = _complete_asset(
        is_pre_cutover=True,
        available_for_use_date=date(2020, 4, 10),
        capitalization_date=date(2020, 4, 10),
        it_put_to_use_date=date(2020, 4, 10),
    )
    issues = validate_transition(
        asset, _complete_acquisition(), AssetLifecycleStatus.capitalized, present_doc_roles=_ALL_DOCS
    )
    # opening_it_wdv is required too: the Income Tax block refuses to open without it,
    # and the book WDV is not a valid substitute for the tax written-down value. Asking
    # here means the user learns at edit time rather than when a run fails.
    assert {
        "opening_accumulated_depreciation",
        "opening_wdv",
        "opening_it_wdv",
    } <= _fields(issues)


def test_can_dispose_asset_matrix():
    """Table-driven unit test verifying can_dispose_asset across roles and lifecycle statuses."""
    admin = CompanyUser(id=uuid.uuid4(), company_id=uuid.uuid4(), role=UserRole.admin)
    emp = CompanyUser(id=uuid.uuid4(), company_id=uuid.uuid4(), role=UserRole.employee)

    # Only admin + capitalized is allowed
    cases = [
        # (user, status, expected_ok, expected_err_substring)
        (admin, AssetLifecycleStatus.capitalized, True, None),
        (admin, AssetLifecycleStatus.draft, False, "Only a capitalized asset can be disposed of"),
        (admin, AssetLifecycleStatus.ready, False, "Only a capitalized asset can be disposed of"),
        (admin, AssetLifecycleStatus.disposed, False, "Only a capitalized asset can be disposed of"),
        (emp, AssetLifecycleStatus.capitalized, False, "Insufficient permissions"),
        (emp, AssetLifecycleStatus.draft, False, "Insufficient permissions"),
        (emp, AssetLifecycleStatus.ready, False, "Insufficient permissions"),
        (emp, AssetLifecycleStatus.disposed, False, "Insufficient permissions"),
    ]

    for user, status, expected_ok, expected_msg in cases:
        asset = Asset(id=uuid.uuid4(), company_id=user.company_id, lifecycle_status=status)
        ok, reason = can_dispose_asset(user, asset)
        assert ok is expected_ok, f"Failed for {user.role} with status {status}: got ok={ok}"
        if expected_msg:
            assert expected_msg in (reason or ""), f"Expected '{expected_msg}' in '{reason}'"


def test_can_dispose_asset_creator_approver_allowed_for_admin():
    """An admin who created and approved the asset can still dispose of it (single-admin SoD rule)."""
    admin_id = uuid.uuid4()
    company_id = uuid.uuid4()
    admin = CompanyUser(id=admin_id, company_id=company_id, role=UserRole.admin)
    asset = Asset(
        id=uuid.uuid4(),
        company_id=company_id,
        lifecycle_status=AssetLifecycleStatus.capitalized,
        created_by=admin_id,
        approved_by=admin_id,
    )
    ok, reason = can_dispose_asset(admin, asset)
    assert ok is True
    assert reason is None

