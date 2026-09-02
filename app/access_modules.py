"""Canonical company-user module access identifiers."""

DASHBOARD_MODULE = "dashboard"
DOCVAULT_MODULE = "docvault"
SALES_MODULE = "sales"
ASSETS_MODULE = "assets"
KRA_MODULE = "kra"
AUDITEASE_MODULE = "auditease"
ROC_MODULE = "roc"
SECRETARIAL_MODULE = "secretarial"
NOTIFICATIONS_MODULE = "notifications"
ACTIVITY_MODULE = "activity"

LEGACY_COMPLIANCE_MODULE = "compliance"

ALL_MODULES = frozenset({
    DASHBOARD_MODULE, DOCVAULT_MODULE, SALES_MODULE, ASSETS_MODULE, KRA_MODULE,
    AUDITEASE_MODULE, ROC_MODULE, SECRETARIAL_MODULE, NOTIFICATIONS_MODULE,
    ACTIVITY_MODULE,
})

def normalize_accessible_modules(modules: list[str]) -> list[str]:
    """Return de-duplicated canonical module IDs, preserving input order.

    The former combined ``compliance`` grant remains accepted during rollout and
    expands to both compliance domains. Persisted and returned values are always
    canonical.
    """
    normalized: list[str] = []
    seen: set[str] = set()

    for module in modules:
        replacements = (
            (ROC_MODULE, SECRETARIAL_MODULE)
            if module == LEGACY_COMPLIANCE_MODULE
            else (module,)
        )
        for replacement in replacements:
            if replacement not in seen:
                normalized.append(replacement)
                seen.add(replacement)

    return normalized


def validate_accessible_modules(modules: list[str]) -> list[str]:
    normalized = normalize_accessible_modules(modules)
    unknown = sorted(set(normalized) - ALL_MODULES)
    if unknown:
        raise ValueError(f"Unknown module ids: {', '.join(unknown)}")
    return normalized
