"""Tests for encryption module."""
import pytest
from app.encryption import (
    generate_company_kek,
    decrypt_company_kek,
    generate_dek,
    encrypt_dek,
    decrypt_dek,
    encrypt_file_data,
    decrypt_file_data,
)


def test_company_kek_roundtrip():
    """Generate a company KEK, encrypt it, decrypt it — should match."""
    raw_kek, encrypted_kek, nonce = generate_company_kek()
    decrypted = decrypt_company_kek(encrypted_kek, nonce)
    assert raw_kek == decrypted


def test_dek_roundtrip():
    """Encrypt a DEK under company KEK and decrypt it back."""
    raw_kek, _, _ = generate_company_kek()
    dek, _ = generate_dek()
    encrypted_dek, nonce = encrypt_dek(dek, raw_kek)
    decrypted = decrypt_dek(encrypted_dek, nonce, raw_kek)
    assert dek == decrypted


def test_file_encryption_roundtrip():
    """Encrypt file data and decrypt it back."""
    raw_kek, _, _ = generate_company_kek()
    dek, _ = generate_dek()
    data = b"Hello, this is a secret document!"
    ciphertext, nonce = encrypt_file_data(data, dek)
    plaintext = decrypt_file_data(ciphertext, nonce, dek)
    assert data == plaintext
