import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings


class CompanyKeyDecryptionError(RuntimeError):
    """A company's KEK would not decrypt under the configured ROOT_MASTER_KEK.

    In practice this means ROOT_MASTER_KEK in .env does not match the key this
    company's KEK was wrapped under — usually because it was regenerated without
    running ops/kubera-rotate-root-kek.py first. Every document, SMTP credential
    and DEK for the company is unreachable until the correct key is restored or
    the rotation script is run. See docs/SECURITY_HARDENING.md §6."""


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
    try:
        return aesgcm.decrypt(nonce, encrypted_kek, None)
    except InvalidTag as exc:
        raise CompanyKeyDecryptionError(
            "Could not decrypt a company KEK with the configured ROOT_MASTER_KEK. "
            "This root key does not match the one this company's KEK was wrapped "
            "under. If ROOT_MASTER_KEK was recently changed, run "
            "ops/kubera-rotate-root-kek.py to re-wrap existing company keys before "
            "changing it, or restore the previous value. See "
            "docs/SECURITY_HARDENING.md §6."
        ) from exc


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


def encrypt_smtp_password(password: str, company_kek: bytes) -> tuple[bytes, bytes]:
    """Encrypt an SMTP password string with AES-GCM under the company KEK.
    Returns (ciphertext, nonce).
    """
    aesgcm = AESGCM(company_kek)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, password.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_smtp_password(ciphertext: bytes, nonce: bytes, company_kek: bytes) -> str:
    """Decrypt an AES-GCM encrypted SMTP password using the company KEK."""
    aesgcm = AESGCM(company_kek)
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_bytes.decode("utf-8")
