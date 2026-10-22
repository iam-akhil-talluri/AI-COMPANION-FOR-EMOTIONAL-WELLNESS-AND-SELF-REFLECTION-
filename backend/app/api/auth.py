"""Account registration, sign-in and sign-out.

A sign-in request with `admin: true` is refused unless the account has the admin role.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.errors import AppError
from app.schemas import ErrorResponse
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.services.event_log import log_event
from app.services.rate_limiter import limiter
from app.services.security import create_access_token
from app.services.user_service import UsernameTakenError, authenticate, create_user, revoke_tokens, username_key

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Failed sign-in limits per 15-minute window.
LOGIN_FAILURES_PER_ACCOUNT = 5
LOGIN_FAILURES_PER_IP = 20
LOGIN_WINDOW_SECONDS = 15 * 60
REGISTRATIONS_PER_IP_PER_HOUR = 10

_TOO_MANY = "Too many sign-in attempts. Please wait a few minutes and try again."
_INVALID = "Sign-in was not successful. Check your username and password."
_NOT_ADMIN = "Administrator sign-in was not successful"


def _auth_response(user: User) -> AuthResponse:
    token, expires_in = create_access_token(user.id, user.role, user.token_version)
    return AuthResponse(token=token, expires_in=expires_in, user=UserOut(username=user.username, role=user.role))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED,
             responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    if not get_settings().allow_registration:
        raise AppError("registration_disabled", 403, "New accounts can't be created right now.")
    if not limiter.allow(f"register:{client_ip(request)}", REGISTRATIONS_PER_IP_PER_HOUR, 3600):
        raise AppError("rate_limited", 429, "Too many new accounts from this network. Please try again later.")
    try:
        user = create_user(db, body.username, body.password)
    except UsernameTakenError:
        raise AppError("username_taken", 409, "That username is taken. Please choose another.") from None
    log_event(db, "user_registered")
    db.commit()
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse,
             responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    ip = client_ip(request)
    keys = [f"login-fail:{ip}:{username_key(body.username)}", f"login-fail:{ip}"]
    rules = [(keys[0], LOGIN_FAILURES_PER_ACCOUNT, LOGIN_WINDOW_SECONDS),
             (keys[1], LOGIN_FAILURES_PER_IP, LOGIN_WINDOW_SECONDS)]
    if not limiter.peek_all(rules):
        raise AppError("rate_limited", 429, _TOO_MANY, headers={"Retry-After": str(LOGIN_WINDOW_SECONDS)})

    user = authenticate(db, body.username, body.password)
    if user is None or (body.admin and user.role != "admin"):
        # Only failed attempts count toward the limit.
        limiter.record(keys)
        db.rollback()  # Discard the last_login_at update for a refused sign-in.
        log_event(db, "login_failed", level="warning", detail="admin=true" if body.admin else None)
        db.commit()
        if user is None:
            raise AppError("invalid_credentials", 401, _INVALID)
        raise AppError("admin_required", 403, _NOT_ADMIN)

    log_event(db, "admin_login" if user.role == "admin" else "user_login")
    db.commit()
    return _auth_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut(username=user.username, role=user.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """Revoke all tokens issued to the current user."""
    revoke_tokens(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
