"""SQLAlchemy models.

Accounts are pseudonymous, and the event log never stores message text.
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db.types import UTCDateTime, utc_now

ROLES = ("user", "admin")
SESSION_TYPES = ("conversation", "reflection")
MESSAGE_ROLES = ("user", "assistant")

MYSQL_TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    """Declarative base for all models."""


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="ck_users_role"), MYSQL_TABLE_OPTIONS)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Display name as entered; uniqueness is enforced on username_key.
    username: Mapped[str] = mapped_column(String(32))
    username_key: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="user", server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Incremented to revoke previously issued tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    sessions: Mapped[list["ConversationSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class ConversationSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(_in("type", SESSION_TYPES), name="ck_sessions_type"),
        Index("ix_sessions_user_last_active", "user_id", "last_active"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID4
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20), default="conversation")
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, index=True)
    last_active: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    # Set when the retention job deletes the transcript.
    transcript_purged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True, order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (CheckConstraint(_in("role", MESSAGE_ROLES), name="ck_messages_role"), MYSQL_TABLE_OPTIONS)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    session: Mapped[ConversationSession] = relationship(back_populates="messages")


class EventLog(Base):
    """Operational event log. Never contains message text."""

    __tablename__ = "event_logs"
    __table_args__ = (MYSQL_TABLE_OPTIONS,)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    level: Mapped[str] = mapped_column(String(10), default="info")  # info | warning | error
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    environment: Mapped[str] = mapped_column(String(20), default="development")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, index=True)
