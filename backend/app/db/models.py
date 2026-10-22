"""SQLAlchemy models.

Accounts are pseudonymous, and the event log never stores message text.
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text
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


RISK_LEVELS = ("low", "moderate", "elevated", "high")
SAFETY_STAGES = ("input", "output")
INTERACTION_STATUSES = ("ok", "support", "crisis", "blocked", "safety_error", "ai_error")


class SafetyEvent(Base):
    """A safety decision: a risky user message (input) or a blocked AI reply (output).

    Anonymized metrics only: no message text and no user ID. Kept after the session or its
    transcript is deleted, so the admin dashboard keeps accurate totals.
    """

    __tablename__ = "safety_events"
    __table_args__ = (
        CheckConstraint(_in("stage", SAFETY_STAGES), name="ck_safety_events_stage"),
        CheckConstraint(_in("risk_level", RISK_LEVELS), name="ck_safety_events_risk_level"),
        Index("ix_safety_events_session_created", "session_id", "created_at"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    stage: Mapped[str] = mapped_column(String(10))
    risk_level: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(40))
    # crisis_template | support_template | ai_with_support_note | ai_with_boundary_note | reply_blocked
    action: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(20), default="rules")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, index=True)


class Interaction(Base):
    """One chat request's outcome and AI usage. Anonymized: no message text and no user ID."""

    __tablename__ = "interactions"
    __table_args__ = (
        CheckConstraint(_in("status", INTERACTION_STATUSES), name="ck_interactions_status"),
        MYSQL_TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # False only for replies that did not go through the safety layer (e.g. a demo provider).
    safety_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    used_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, index=True)


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
