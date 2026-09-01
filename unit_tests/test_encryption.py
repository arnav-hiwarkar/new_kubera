"""Root KEK mismatch used to surface as a bare `cryptography.exceptions.InvalidTag`
and an opaque 500 — reproduced live when an earlier hardening pass generated a new
ROOT_MASTER_KEK without running ops/kubera-rotate-root-kek.py against the existing
database. Every document, SMTP credential and DEK for the affected companies was
unreachable, and the error gave no indication why.
"""

from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

os.environ.setdefault("KUBERA_ALLOW_INSECURE_DEFAULTS", "1")

from app.encryption import (
    CompanyKeyDecryptionError,
    decrypt_company_kek,
    generate_company_kek,
)


def test_decrypting_with_the_correct_root_kek_round_trips(monkeypatch):
    monkeypatch.setenv("ROOT_MASTER_KEK", "a" * 64)
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        raw_kek, encrypted, nonce = generate_company_kek()
        assert decrypt_company_kek(encrypted, nonce) == raw_kek
    finally:
        get_settings.cache_clear()


def test_a_kek_wrapped_under_a_different_root_key_raises_a_clear_error(monkeypatch):
    """This is exactly what happens when ROOT_MASTER_KEK is rotated in .env
    without re-wrapping existing company_keys rows first."""
    monkeypatch.setenv("ROOT_MASTER_KEK", "a" * 64)
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        _, encrypted, nonce = generate_company_kek()
    finally:
        get_settings.cache_clear()

    monkeypatch.setenv("ROOT_MASTER_KEK", "b" * 64)
    get_settings.cache_clear()
    try:
        with pytest.raises(CompanyKeyDecryptionError, match="does not match"):
            decrypt_company_kek(encrypted, nonce)
    finally:
        get_settings.cache_clear()


def test_corrupted_ciphertext_also_raises_the_clear_error(monkeypatch):
    """Not just a wrong key — any authentication failure (bit flip, truncation)
    must fail the same informative way rather than an unhandled InvalidTag."""
    monkeypatch.setenv("ROOT_MASTER_KEK", "c" * 64)
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        _, encrypted, nonce = generate_company_kek()
        tampered = bytes([encrypted[0] ^ 0xFF]) + encrypted[1:]
        with pytest.raises(CompanyKeyDecryptionError):
            decrypt_company_kek(tampered, nonce)
    finally:
        get_settings.cache_clear()
