"""Password hashing, token issuing and other security primitives.

Argon2id is used for passwords (memory-hard, current OWASP recommendation). JWTs are short-lived
access tokens; refresh tokens are opaque random strings stored hashed so they can be revoked.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from pakjobs_core.config import settings

# Tuned for a web request budget (~50-80ms on typical server hardware).
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2, hash_len=32, salt_len=16)

TokenType = Literal["access", "refresh"]
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 200


class PasswordPolicyError(ValueError):
    pass


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError("Password is too long.")
    if password.lower() in _COMMON_PASSWORDS:
        raise PasswordPolicyError("This password is too common. Choose something less predictable.")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise PasswordPolicyError("Password must contain both letters and numbers.")


_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "qwerty123",
    "abc12345", "welcome1", "iloveyou", "admin123", "letmein1", "pakistan1",
}


def hash_password(password: str) -> str:
    validate_password_strength(password)
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time verification; never raises for a bad hash."""
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# --- JWT --------------------------------------------------------------------

def create_access_token(
    *, user_id: uuid.UUID | str, role: str, token_version: int = 0, extra: dict[str, Any] | None = None
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
        "jti": secrets.token_urlsafe(12),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError subclasses on any problem — callers convert to 401."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# --- opaque tokens (refresh, email verification, password reset) -------------

def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """HMAC with the app secret so a database leak alone cannot forge tokens."""
    return hmac.new(settings.jwt_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days)


def hash_ip(ip: str | None) -> str | None:
    """Store a salted hash instead of the raw IP (data-minimisation)."""
    if not ip:
        return None
    return hashlib.sha256(f"{settings.jwt_secret}:{ip}".encode()).hexdigest()[:64]


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
