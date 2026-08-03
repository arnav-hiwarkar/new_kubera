"""Canonical company-user module access identifiers."""

LEGACY_COMPLIANCE_MODULE = "compliance"
ROC_MODULE = "roc"
SECRETARIAL_MODULE = "secretarial"


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
