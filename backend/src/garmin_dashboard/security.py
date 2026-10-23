"""Passwords, login sessions and encryption of stored Garmin API keys."""

from __future__ import annotations

import contextlib
import hashlib
import os
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def new_session_token() -> tuple[str, str]:
    """Return (token for the cookie, hash stored in the database)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@lru_cache
def _fernet() -> Fernet:
    """Fernet key from GD_SECRET_KEY, else a key file generated on first run."""
    settings = get_settings()
    env_key = os.environ.get("GD_SECRET_KEY")
    if env_key:
        return Fernet(env_key.encode())
    settings.ensure_dirs()
    key_file = settings.secrets_dir / "master.key"
    if not key_file.exists():
        key_file.write_bytes(Fernet.generate_key())
        with contextlib.suppress(OSError):
            key_file.chmod(0o600)
    return Fernet(key_file.read_bytes().strip())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError(
            "Stored Garmin key can't be decrypted - was data/secrets/master.key replaced?"
        ) from exc


def key_hint(api_key: str) -> str:
    return f"…{api_key[-4:]}" if len(api_key) >= 8 else "…"
