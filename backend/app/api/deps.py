"""Request dependencies for authentication and session ownership."""

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.models import ConversationSession, User
from app.db.session import get_db
from app.errors import AppError
from app.services.conversation_service import get_owned_session
from app.services.security import TokenError, decode_access_token

_bearer = HTTPBearer(auto_error=False, description="Access token from /api/auth/login")
_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError("not_authenticated", 401, "Please sign in to continue.", _UNAUTHORIZED)
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError:
        raise AppError("session_expired", 401, "Your sign-in has expired. Please sign in again.",
                       _UNAUTHORIZED) from None
    user = db.get(User, int(payload["sub"]))
    # Reject inactive accounts and tokens issued before the last revocation.
    if user is None or not user.is_active or user.token_version != payload.get("ver"):
        raise AppError("session_expired", 401, "Your sign-in has expired. Please sign in again.", _UNAUTHORIZED)
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise AppError("forbidden", 403, "Administrator access is required.")
    return user


def owned_session(session_id: str, user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> ConversationSession:
    """Return the session if it belongs to the current user.

    Unknown and foreign sessions both return 404 so session IDs cannot be probed.
    """
    conversation = get_owned_session(db, session_id, user.id) if len(session_id) <= 36 else None
    if conversation is None:
        raise AppError("not_found", 404, "Session not found.")
    return conversation


def client_ip(request: Request) -> str:
    # request.client reflects X-Forwarded-For only for proxies trusted via FORWARDED_ALLOW_IPS.
    return request.client.host if request.client else "unknown"
