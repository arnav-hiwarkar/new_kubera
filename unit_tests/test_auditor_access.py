import pytest

from app.services.auditor_access import area_enabled, normalize_area_permissions


def test_none_means_full_access():
    assert normalize_area_permissions(None) == {
        "trial_balance": True,
        "entries": True,
        "requirements": True,
        "queries": True,
        "documents": True,
    }


def test_explicit_payload_fills_missing_with_false():
    perms = normalize_area_permissions({"entries": True})
    assert perms["entries"] is True
    assert perms["trial_balance"] is False
    assert perms["documents"] is False


def test_unknown_area_raises():
    with pytest.raises(ValueError):
        normalize_area_permissions({"nope": True})


def test_area_enabled_missing_key_is_denied():
    assert area_enabled({}, "entries") is False
    assert area_enabled(None, "entries") is False
    assert area_enabled({"entries": True}, "entries") is True
