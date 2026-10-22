"""Database URL handling, the UTC column type, migrations and the admin script."""

import os
from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select

from app.db.models import Base, User
from app.db.session import normalize_database_url
from app.db.types import UTCDateTime
from tests.helpers import PASSWORD, login

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))


@pytest.mark.parametrize("url,expected", [
    ("mysql://u:p@db.example:3306/app", "mysql+pymysql://u:p@db.example:3306/app?charset=utf8mb4"),
    ("mysql+pymysql://u:p@h/app?charset=utf8mb4", "mysql+pymysql://u:p@h/app?charset=utf8mb4"),
    ("sqlite:///./data/app.db", "sqlite:///./data/app.db"),
])
def test_database_url_is_normalized(url, expected):
    assert normalize_database_url(url) == expected


def test_utc_datetime_round_trip(db_session):
    eastern = timezone(timedelta(hours=-4))
    user = User(username="tz-user", username_key="tz-user", password_hash="x",
                created_at=datetime(2026, 10, 20, 8, 0, tzinfo=eastern))
    db_session.add(user)
    db_session.commit()
    db_session.expire_all()
    stored = db_session.scalar(select(User))
    assert stored.created_at == datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    assert stored.created_at.tzinfo is UTC


def test_naive_datetimes_are_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1), None)


def test_migrations_match_the_models(tmp_path):
    """Migrations must match the models and downgrade cleanly."""
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    config.attributes["database_url"] = url
    config.attributes["configure_logging"] = False
    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata)
    assert diff == []

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()


def test_create_admin_script(session_factory, client, monkeypatch, db_session):
    from scripts import create_admin

    monkeypatch.setenv("NEW_ADMIN_PASSWORD", "a-long-admin-password")
    assert create_admin.main(["--username", "site-admin", "--password-env", "NEW_ADMIN_PASSWORD"]) == 0
    assert login(client, "site-admin", "a-long-admin-password", admin=True).status_code == 200


def test_create_admin_promotes_existing_user(session_factory, client, monkeypatch):
    from scripts import create_admin
    from tests.helpers import register

    register(client, "promote-me")
    assert login(client, "promote-me", PASSWORD, admin=True).status_code == 403
    create_admin.main(["--username", "promote-me", "--keep-password"])
    assert login(client, "promote-me", PASSWORD, admin=True).status_code == 200


def test_create_admin_rejects_short_passwords(session_factory, monkeypatch):
    from scripts import create_admin

    monkeypatch.setenv("NEW_ADMIN_PASSWORD", "short-pass")
    with pytest.raises(SystemExit, match="12-128"):
        create_admin.main(["--username", "site-admin", "--password-env", "NEW_ADMIN_PASSWORD"])

