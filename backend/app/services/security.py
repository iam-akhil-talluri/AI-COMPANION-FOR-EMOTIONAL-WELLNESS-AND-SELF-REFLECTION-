"""Password hashing (Argon2id) and access tokens (HS256 JWT)."""

from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Settings, get_settings
from app.db.types import utc_now

ALGORITHM = "HS256"
ISSUER = "wellness-companion"

_hasher = PasswordHasher()
# Used for unknown usernames so failed sign-ins take the same time.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


class TokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: int, role: str, token_version: int,
                        settings: Settings | None = None) -> tuple[str, int]:
    settings = settings or get_settings()
    expires_in = settings.jwt_expire_minutes * 60
    now = utc_now()
    payload = {
        "sub": str(user_id),
        "role": role,
        "ver": token_version,
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), expires_in


def decode_access_token(token: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], issuer=ISSUER,
                             options={"require": ["sub", "exp", "iat", "iss"]})
    except jwt.PyJWTError as exc:
        raise TokenError("invalid or expired token") from exc
    if not str(payload.get("sub", "")).isdigit():
        raise TokenError("invalid subject")
    return payload
