"""Required-field validation for the fixed-asset register, tiered by lifecycle.

This is the mechanism that makes a 37-field "mandatory" list compatible with a
six-field create form. Nothing is required by the database; requirements attach to
*transitions*:

  -> draft        asset name + category. Save and walk away.
  -> ready        every commercial and statutory field, plus the invoice and a
                  photograph. This is the completeness gate.
  -> capitalized  the dates that start depreciation, and a non-zero cost.

Returns a list of issues rather than raising on the first one, so the UI can show
a checklist that deep-links to the tab owning each field.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional

from app.models.asset_masters import ItcTreatment
from app.models.assets import (
    Asset,
    AssetAcquisition,
    AssetDisposalType,
    AssetDocRole,
    AssetLifecycleStatus,
)
from app.models.financial_year import FinancialYear

# Tabs on the asset detail page, used to deep-link each issue.
TAB_IDENTITY = "identity"
TAB_ACQUISITION = "acquisition"
TAB_TAX = "tax"
TAB_DEPRECIATION = "depreciation"
TAB_ASSIGNMENT = "assignment"
TAB_DOCUMENTS = "documents"


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    label: str
    tab: str
    kind: str = "missing"  # missing | invalid
    message: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "field": self.field,
            "label": self.label,
            "tab": self.tab,
            "kind": self.kind,
            "message": self.message,
        }


# (attribute, human label, tab) — required to reach `ready`.
_ACQUISITION_READY_FIELDS = [
    ("supplier_id", "Supplier", TAB_ACQUISITION),
    ("invoice_number", "Invoice number", TAB_ACQUISITION),
    ("invoice_date", "Invoice date", TAB_ACQUISITION),
    ("po_number", "Purchase order number", TAB_ACQUISITION),
    ("purchase_date", "Purchase / receipt date", TAB_ACQUISITION),
    ("unit_basic_price", "Basic price", TAB_ACQUISITION),
    ("gst_rate", "GST rate", TAB_TAX),
    ("itc_treatment", "GST ITC eligibility", TAB_TAX),
]

_ASSET_READY_FIELDS = [
    ("description", "Asset description", TAB_IDENTITY),
    ("manufacturer", "Manufacturer", TAB_IDENTITY),
    ("brand_model", "Brand / model", TAB_IDENTITY),
    ("branch_id", "Branch", TAB_ASSIGNMENT),
    ("cost_centre_id", "Cost centre", TAB_ASSIGNMENT),
    ("department_id", "Department", TAB_ASSIGNMENT),
    ("location_id", "Location", TAB_ASSIGNMENT),
    ("operational_status", "Asset status", TAB_ASSIGNMENT),
    ("condition", "Condition", TAB_ASSIGNMENT),
    ("useful_life_months", "Companies Act useful life", TAB_DEPRECIATION),
    ("dep_method", "Depreciation method (SLM/WDV)", TAB_DEPRECIATION),
    ("residual_pct", "Residual value %", TAB_DEPRECIATION),
    ("it_block_id", "Income-tax asset block", TAB_DEPRECIATION),
    ("it_dep_rate", "Income-tax depreciation rate", TAB_DEPRECIATION),
]

_ASSET_CAPITALIZED_FIELDS = [
    ("available_for_use_date", "Available-for-use date", TAB_DEPRECIATION),
    ("capitalization_date", "Capitalization date", TAB_DEPRECIATION),
    ("it_put_to_use_date", "Income-tax put-to-use date", TAB_DEPRECIATION),
]

# Documents that must be attached before an asset can be submitted.
_REQUIRED_DOC_ROLES = [
    (AssetDocRole.invoice, "Supplier invoice"),
    (AssetDocRole.asset_photo, "Asset photograph"),
]


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def validate_transition(
    asset: Asset,
    acquisition: Optional[AssetAcquisition],
    target: AssetLifecycleStatus,
    present_doc_roles: Optional[Iterable[AssetDocRole]] = None,
    category=None,
) -> list[ValidationIssue]:
    """Return every reason `asset` cannot reach `target`. Empty list means OK.

    `category` is optional; when supplied, a useful life that diverges from the
    category default requires a stated reason (Schedule II disclosure).
    """
    issues: list[ValidationIssue] = []
    roles = set(present_doc_roles or ())

    # --- Tier 1: always ---
    if _is_blank(asset.asset_name):
        issues.append(ValidationIssue("asset_name", "Asset name", TAB_IDENTITY))
    if asset.category_id is None:
        issues.append(ValidationIssue("category_id", "Asset category", TAB_IDENTITY))

    if target == AssetLifecycleStatus.draft:
        return issues

    # --- Tier 2: ready (also required for capitalized) ---
    for attr, label, tab in _ASSET_READY_FIELDS:
        if _is_blank(getattr(asset, attr, None)):
            issues.append(ValidationIssue(attr, label, tab))

    # Custodian is satisfied by either a real user or a free-text name.
    if asset.custodian_id is None and _is_blank(asset.custodian_name):
        issues.append(
            ValidationIssue(
                "custodian",
                "Custodian",
                TAB_ASSIGNMENT,
                message="Select a user or enter a custodian name",
            )
        )

    if acquisition is None:
        issues.append(
            ValidationIssue("acquisition_id", "Acquisition details", TAB_ACQUISITION)
        )
    else:
        for attr, label, tab in _ACQUISITION_READY_FIELDS:
            if _is_blank(getattr(acquisition, attr, None)):
                issues.append(ValidationIssue(attr, label, tab))

        if (
            acquisition.itc_treatment == ItcTreatment.partial
            and acquisition.itc_eligible_pct is None
        ):
            issues.append(
                ValidationIssue(
                    "itc_eligible_pct",
                    "Eligible ITC %",
                    TAB_TAX,
                    message="Required when ITC eligibility is partial",
                )
            )

        if (
            acquisition.invoice_date is not None
            and acquisition.purchase_date is not None
            and acquisition.invoice_date > acquisition.purchase_date
        ):
            issues.append(
                ValidationIssue(
                    "invoice_date",
                    "Invoice date",
                    TAB_ACQUISITION,
                    kind="invalid",
                    message="Invoice date cannot be after the purchase / receipt date",
                )
            )

    for role, label in _REQUIRED_DOC_ROLES:
        if role not in roles:
            issues.append(
                ValidationIssue(f"doc:{role.value}", label, TAB_DOCUMENTS)
            )

    if (
        category is not None
        and category.default_useful_life_months is not None
        and asset.useful_life_months is not None
        and int(asset.useful_life_months) != int(category.default_useful_life_months)
        and _is_blank(asset.useful_life_override_reason)
    ):
        issues.append(
            ValidationIssue(
                "useful_life_override_reason",
                "Reason for differing useful life",
                TAB_DEPRECIATION,
                message=(
                    "Schedule II requires the reason to be disclosed when the useful life "
                    f"differs from the category default of {category.default_useful_life_months} months"
                ),
            )
        )

    if target == AssetLifecycleStatus.ready:
        return issues

    # --- Tier 3: capitalized ---
    for attr, label, tab in _ASSET_CAPITALIZED_FIELDS:
        if _is_blank(getattr(asset, attr, None)):
            issues.append(ValidationIssue(attr, label, tab))

    if asset.original_cost is None or Decimal(asset.original_cost) <= 0:
        issues.append(
            ValidationIssue(
                "original_cost",
                "Total capitalized value",
                TAB_ACQUISITION,
                kind="invalid" if asset.original_cost is not None else "missing",
                message="Capitalized cost must be greater than zero",
            )
        )

    # Assets already owned at cutover carry their history in rather than having it
    # recomputed; without these the engine would restate depreciation from scratch.
    if asset.is_pre_cutover:
        if asset.opening_accumulated_depreciation is None:
            issues.append(
                ValidationIssue(
                    "opening_accumulated_depreciation",
                    "Opening accumulated depreciation",
                    TAB_DEPRECIATION,
                    message="Required for assets acquired before the register cutover date",
                )
            )
        if asset.opening_wdv is None:
            issues.append(
                ValidationIssue(
                    "opening_wdv",
                    "Opening written-down value",
                    TAB_DEPRECIATION,
                    message="Required for assets acquired before the register cutover date",
                )
            )
        # The Income Tax block refuses to open without this, and the book WDV is not a
        # valid stand-in. Ask for it here rather than failing the depreciation run.
        if asset.opening_it_wdv is None:
            issues.append(
                ValidationIssue(
                    "opening_it_wdv",
                    "Opening written-down value (tax)",
                    TAB_DEPRECIATION,
                    message=(
                        "Required for assets acquired before the register cutover date. "
                        "The Income Tax written-down value differs from the book value and "
                        "cannot be derived from it."
                    ),
                )
            )

    purchase_date = getattr(acquisition, "purchase_date", None) if acquisition else None
    if (
        purchase_date is not None
        and asset.available_for_use_date is not None
        and asset.available_for_use_date < purchase_date
    ):
        issues.append(
            ValidationIssue(
                "available_for_use_date",
                "Available-for-use date",
                TAB_DEPRECIATION,
                kind="invalid",
                message="Cannot be earlier than the purchase / receipt date",
            )
        )
    if (
        asset.capitalization_date is not None
        and asset.available_for_use_date is not None
        and asset.capitalization_date < asset.available_for_use_date
    ):
        issues.append(
            ValidationIssue(
                "capitalization_date",
                "Capitalization date",
                TAB_DEPRECIATION,
                kind="invalid",
                message="Cannot be earlier than the available-for-use date",
            )
        )

    return issues


def validate_disposal(
    asset: Asset,
    disposal_date: date,
    disposal_type: str | AssetDisposalType,
    sale_proceeds: Optional[Decimal],
    has_company_fys: bool = False,
    covering_fy: Optional[FinancialYear] = None,
    has_finalized_run: bool = False,
) -> list[ValidationIssue]:
    """Validate asset disposal rules."""
    issues: list[ValidationIssue] = []

    if asset.lifecycle_status != AssetLifecycleStatus.capitalized:
        issues.append(
            ValidationIssue(
                "lifecycle_status",
                "Asset Status",
                TAB_IDENTITY,
                kind="invalid",
                message=f"Only a capitalized asset can be disposed of (this asset is {asset.lifecycle_status.value})",
            )
        )

    earliest_date = asset.capitalization_date or asset.available_for_use_date
    if earliest_date and disposal_date < earliest_date:
        issues.append(
            ValidationIssue(
                "disposal_date",
                "Disposal Date",
                TAB_DEPRECIATION,
                kind="invalid",
                message=f"Disposal date ({disposal_date}) cannot be earlier than capitalization date ({earliest_date})",
            )
        )

    if has_company_fys:
        if not covering_fy:
            issues.append(
                ValidationIssue(
                    "disposal_date",
                    "Disposal Date",
                    TAB_DEPRECIATION,
                    kind="invalid",
                    message=f"Disposal date {disposal_date} does not fall within an open financial year",
                )
            )
        elif covering_fy.status != "open":
            issues.append(
                ValidationIssue(
                    "disposal_date",
                    "Disposal Date",
                    TAB_DEPRECIATION,
                    kind="invalid",
                    message=f"Financial year {covering_fy.label} is closed",
                )
            )
        elif has_finalized_run:
            issues.append(
                ValidationIssue(
                    "disposal_date",
                    "Disposal Date",
                    TAB_DEPRECIATION,
                    kind="invalid",
                    message=f"Cannot dispose asset in financial year {covering_fy.label} because depreciation has already been finalized",
                )
            )

    disp_type_val = disposal_type.value if hasattr(disposal_type, "value") else str(disposal_type)
    if disp_type_val in ("sale", "insurance_claim") and sale_proceeds is None:
        issues.append(
            ValidationIssue(
                "sale_proceeds",
                "Sale Proceeds",
                TAB_DEPRECIATION,
                kind="missing",
                message=f"Sale proceeds is required for disposal type '{disp_type_val}'",
            )
        )

    return issues


def can_dispose_asset(user, asset: Asset) -> tuple[bool, Optional[str]]:
    """Pure authorization + lifecycle predicate for asset disposal.

    Returns (allowed, reason_if_denied). This is the single source of truth for
    "may this user dispose of this asset" — `dispose_asset` calls it, so the unit
    tests over this function constrain the real endpoint rather than a copy of it.
    The role branch is also enforced declaratively by `require_admin` on the route;
    keeping it here means the rule survives someone dropping the dependency.
    """
    from app.models.company import UserRole

    if user.role != UserRole.admin:
        return False, "Insufficient permissions"
    if asset.lifecycle_status != AssetLifecycleStatus.capitalized:
        return (
            False,
            f"Only a capitalized asset can be disposed of (this asset is {asset.lifecycle_status.value})",
        )
    return True, None
