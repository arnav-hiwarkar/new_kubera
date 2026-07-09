import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings


def get_root_kek() -> bytes:
    """Return the root master KEK from env (hex-decoded)."""
    settings = get_settings()
    return bytes.fromhex(settings.ROOT_MASTER_KEK)


def generate_company_kek() -> tuple[bytes, bytes, bytes]:
    """Generate a new per-company KEK, encrypt it under root KEK.
    Returns (raw_kek, encrypted_kek, nonce).
    """
    raw_kek = os.urandom(32)  # AES-256
    root_kek = get_root_kek()
    aesgcm = AESGCM(root_kek)
    nonce = os.urandom(12)
    encrypted_kek = aesgcm.encrypt(nonce, raw_kek, None)
    return raw_kek, encrypted_kek, nonce


def decrypt_company_kek(encrypted_kek: bytes, nonce: bytes) -> bytes:
    """Decrypt a company's KEK using the root master KEK."""
    root_kek = get_root_kek()
    aesgcm = AESGCM(root_kek)
    return aesgcm.decrypt(nonce, encrypted_kek, None)


def generate_dek() -> tuple[bytes, bytes]:
    """Generate a document-level DEK. Returns (raw_dek, nonce_for_dek_encryption)."""
    return os.urandom(32), os.urandom(12)


def encrypt_dek(dek: bytes, company_kek: bytes) -> tuple[bytes, bytes]:
    """Encrypt a DEK under the company KEK. Returns (encrypted_dek, nonce)."""
    aesgcm = AESGCM(company_kek)
    nonce = os.urandom(12)
    encrypted = aesgcm.encrypt(nonce, dek, None)
    return encrypted, nonce


def decrypt_dek(encrypted_dek: bytes, nonce: bytes, company_kek: bytes) -> bytes:
    """Decrypt a DEK using the company KEK."""
    aesgcm = AESGCM(company_kek)
    return aesgcm.decrypt(nonce, encrypted_dek, None)


def encrypt_file_data(data: bytes, dek: bytes) -> tuple[bytes, bytes]:
    """Encrypt file content with the DEK. Returns (ciphertext, nonce)."""
    aesgcm = AESGCM(dek)
    nonce = os.urandom(12)
    return aesgcm.encrypt(nonce, data, None), nonce


def decrypt_file_data(ciphertext: bytes, nonce: bytes, dek: bytes) -> bytes:
    """Decrypt file content with the DEK."""
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ciphertext, None)
