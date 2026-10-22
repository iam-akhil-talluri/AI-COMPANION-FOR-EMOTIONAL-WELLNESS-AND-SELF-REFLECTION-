"""User account management. Accounts are pseudonymous: username and password only."""

import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.types import utc_now
from app.services.security import hash_password, password_needs_rehash, verify_password

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class UsernameTakenError(Exception):
    pass


def username_key(username: str) -> str:
    return username.strip().lower()


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def find_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username_key == username_key(username)))


def create_user(db: Session, username: str, password: str, role: str = "user") -> User:
    """Create and commit a user. Raise UsernameTakenError if the name is taken (case-insensitive)."""
    user = User(username=username.strip(), username_key=username_key(username),
                password_hash=hash_password(password), role=role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise UsernameTakenError(username) from exc
    db.refresh(user)
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Return the active user for these credentials, or None."""
    user = find_user(db, username)
    if not verify_password(user.password_hash if user else None, password):
        return None
    if user is None or not user.is_active:
        return None
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utc_now()
    return user


def set_password(user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    user.token_version += 1  # Revokes existing tokens


def revoke_tokens(user: User) -> None:
    user.token_version += 1
