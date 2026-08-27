"""Security utilities for user passwords, complexity checks, and image magic bytes."""
import re
from typing import Literal

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# Special character set allowed and checked
SPECIAL_CHARS_RE = re.compile(r'[-!@#$%^&*(),.?":{}|<>_=+`~/\\\[\];]')


def validate_password_complexity(password: str) -> None:
    """Validate password against Kubera enterprise complexity policy.

    Rules:
    - Minimum 8 characters
    - At least 1 uppercase ASCII letter (A-Z)
    - At least 1 lowercase ASCII letter (a-z)
    - At least 1 numeric digit (0-9)
    - At least 1 special character
    """
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long.")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be no more than {PASSWORD_MAX_LENGTH} characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter (A-Z).")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter (a-z).")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one number (0-9).")
    if not SPECIAL_CHARS_RE.search(password):
        raise ValueError("Password must contain at least one special character.")


def detect_image_format(data: bytes) -> Literal["jpg", "png", "webp"] | None:
    """Detect image format by inspecting binary magic bytes.

    Supports:
    - JPEG (starts with FF D8 FF)
    - PNG (starts with 89 50 4E 47 0D 0A 1A 0A)
    - WEBP (starts with 'RIFF' and bytes 8..12 are 'WEBP')

    Returns 'jpg', 'png', 'webp', or None if unrecognized/invalid.
    """
    if not data or len(data) < 12:
        return None

    # JPEG: \xff\xd8\xff
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"

    # PNG: \x89PNG\r\n\x1a\n
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    # WEBP: RIFF....WEBP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"

    return None
