"""Per-area permission helpers for auditor engagement grants.

Pure functions — no DB. The router layer owns queries and HTTP errors.
"""
from app.models.auditease import AUDITOR_AREAS


def normalize_area_permissions(payload: dict | None) -> dict[str, bool]:
    """None => every area enabled (invite default). An explicit payload sets the
    listed areas and DENIES everything omitted, so {"entries": true} means
    entries-only."""
    if payload is None:
        return {a: True for a in AUDITOR_AREAS}
    unknown = set(payload) - set(AUDITOR_AREAS)
    if unknown:
        raise ValueError(f"Unknown areas: {sorted(unknown)}")
    return {a: bool(payload.get(a, False)) for a in AUDITOR_AREAS}


def area_enabled(perms: dict | None, area: str) -> bool:
    return bool((perms or {}).get(area, False))
