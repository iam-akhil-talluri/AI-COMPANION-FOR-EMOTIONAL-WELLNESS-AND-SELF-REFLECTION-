"""Tests for registration, sign-in and tokens."""

from datetime import timedelta

import jwt
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.models import EventLog, User
from app.db.types import utc_now
from app.services.security import ALGORITHM, ISSUER
from app.services.user_service import create_user
from tests.helpers import PASSWORD, login, register


def test_register_returns_token_and_user(client, db_session):
    response = client.post("/api/auth/register", json={"username": "Quiet.Harbor", "password": PASSWORD})
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer" and body["token"] and body["expires_in"] == 480 * 60
    assert body["user"] == {"username": "Quiet.Harbor", "role": "user"}
    user = db_session.scalar(select(User))
    assert user.username_key == "quiet.harbor"
    assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash


def test_usernames_are_unique_case_insensitively(client):
    register(client, "calm-river")
    response = client.post("/api/auth/register", json={"username": "CALM-RIVER", "password": PASSWORD})
    assert response.status_code == 409
    assert response.json()["code"] == "username_taken"


@pytest.mark.parametrize("username", ["ab", "has space", "x" * 33, "-leading-dash", "name@example.com"])
def test_invalid_usernames_are_rejected(client, username):
    response = client.post("/api/auth/register", json={"username": username, "password": PASSWORD})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_short_password_rejected(client):
    response = client.post("/api/auth/register", json={"username": "calm-river", "password": "short"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Your password must be 8-128 characters."


def test_invalid_username_gets_a_plain_message(client):
    """The validation message is plain text, not a regex."""
    response = client.post("/api/auth/register", json={"username": "has space", "password": PASSWORD})
    detail = response.json()["detail"]
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert detail.startswith("Usernames are 3-32 characters") and "pattern" not in detail and "^" not in detail


def test_registration_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_registration", False)
    response = client.post("/api/auth/register", json={"username": "calm-river", "password": PASSWORD})
    assert response.status_code == 403 and response.json()["code"] == "registration_disabled"


def test_registration_is_rate_limited_per_network(client):
    codes = [client.post("/api/auth/register", json={"username": f"user-{n:02d}", "password": PASSWORD}).status_code
             for n in range(11)]
    assert codes[:10] == [201] * 10 and codes[10] == 429


def test_login_success(client):
    register(client, "calm-river")
    response = login(client, "Calm-River")
    assert response.status_code == 200
    assert response.json()["user"] == {"username": "calm-river", "role": "user"}


@pytest.mark.parametrize("username,password", [("calm-river", "wrong-password"), ("nobody-here", PASSWORD)])
def test_wrong_credentials_get_the_same_401(client, username, password):
    register(client, "calm-river")
    response = login(client, username, password)
    assert response.status_code == 401
    assert response.json() == {"code": "invalid_credentials",
                               "detail": "Sign-in was not successful. Check your username and password."}


def test_admin_checkbox_refuses_non_admin_accounts(client):
    register(client, "calm-river")
    response = login(client, "calm-river", admin=True)
    assert response.status_code == 403
    assert response.json()["detail"] == "Administrator sign-in was not successful"


def test_admin_checkbox_with_admin_account(client, db_session):
    create_user(db_session, "site-admin", PASSWORD, role="admin")
    response = login(client, "site-admin", admin=True)
    assert response.status_code == 200 and response.json()["user"]["role"] == "admin"
    assert db_session.scalar(select(EventLog.event_type).order_by(EventLog.id.desc())) == "admin_login"


def test_only_failed_sign_ins_count_toward_the_limit(client):
    register(client, "calm-river")
    for _ in range(10):
        assert login(client, "calm-river").status_code == 200
    codes = [login(client, "calm-river", "wrong-password").status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    assert login(client, "calm-river").status_code == 429  # Locked out for the window, even with the correct password.


def test_inactive_account_cannot_sign_in(client, db_session):
    register(client, "calm-river")
    db_session.scalar(select(User)).is_active = False
    db_session.commit()
    assert login(client, "calm-river").status_code == 401


def test_failed_sign_in_is_logged_without_the_username(client, db_session):
    login(client, "secret-name", "wrong-password")
    row = db_session.scalar(select(EventLog).where(EventLog.event_type == "login_failed"))
    assert row is not None and "secret-name" not in (row.detail or "")


def test_me_returns_the_signed_in_user(client, auth):
    assert client.get("/api/auth/me", headers=auth).json() == {"username": "calm-river", "role": "user"}


def test_protected_routes_require_a_token(client):
    response = client.get("/api/sessions")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["www-authenticate"] == "Bearer"


def test_garbage_token_is_rejected(client):
    response = client.get("/api/sessions", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401 and response.json()["code"] == "session_expired"


def _token(user_id: int, **overrides) -> str:
    now = utc_now()
    payload = {"sub": str(user_id), "role": "user", "ver": 0, "iss": ISSUER, "iat": now,
               "exp": now + timedelta(minutes=5), **overrides}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGORITHM)


def test_expired_token_is_rejected(client, auth, db_session):
    user = db_session.scalar(select(User))
    token = _token(user.id, exp=utc_now() - timedelta(seconds=1))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_signed_with_another_key_is_rejected(client, auth, db_session):
    user = db_session.scalar(select(User))
    forged = jwt.encode({"sub": str(user.id), "role": "admin", "ver": 0, "iss": ISSUER, "iat": utc_now(),
                         "exp": utc_now() + timedelta(minutes=5)}, "x" * 40, algorithm=ALGORITHM)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_role_claim_cannot_grant_admin(client, auth, db_session):
    # The role is always read from the database, never trusted from the token.
    user = db_session.scalar(select(User))
    token = _token(user.id, role="admin")
    response = client.get("/api/admin/logs", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_logout_revokes_existing_tokens(client, auth):
    assert client.post("/api/auth/logout", headers=auth).status_code == 204
    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_deleted_user_token_is_rejected(client, auth, db_session):
    db_session.delete(db_session.scalar(select(User)))
    db_session.commit()
    assert client.get("/api/auth/me", headers=auth).status_code == 401
