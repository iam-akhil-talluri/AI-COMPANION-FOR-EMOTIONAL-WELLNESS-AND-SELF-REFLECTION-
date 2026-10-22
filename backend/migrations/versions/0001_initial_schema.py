"""Initial schema: users, sessions, messages and the operational event log.

Revision ID: 0001
Revises:
Create Date: 2026-10-21 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.types

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('event_logs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('event_type', sa.String(length=40), nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=True),
    sa.Column('level', sa.String(length=10), nullable=False),
    sa.Column('detail', sa.String(length=200), nullable=True),
    sa.Column('environment', sa.String(length=20), nullable=False),
    sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_event_logs_created_at'), 'event_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_event_logs_event_type'), 'event_logs', ['event_type'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=32), nullable=False),
    sa.Column('username_key', sa.String(length=32), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=10), server_default='user', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('token_version', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
    sa.Column('last_login_at', app.db.types.UTCDateTime(), nullable=True),
    sa.CheckConstraint("role IN ('user', 'admin')", name='ck_users_role'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username_key'),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )

    op.create_table('sessions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=True),
    sa.Column('prompt', sa.String(length=300), nullable=True),
    sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
    sa.Column('last_active', app.db.types.UTCDateTime(), nullable=False),
    sa.Column('message_count', sa.Integer(), nullable=False),
    sa.Column('transcript_purged_at', app.db.types.UTCDateTime(), nullable=True),
    sa.CheckConstraint("type IN ('conversation', 'reflection')", name='ck_sessions_type'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_sessions_created_at'), 'sessions', ['created_at'], unique=False)
    op.create_index('ix_sessions_user_last_active', 'sessions', ['user_id', 'last_active'], unique=False)

    op.create_table('messages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
    sa.CheckConstraint("role IN ('user', 'assistant')", name='ck_messages_role'),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_messages_session_id'), 'messages', ['session_id'], unique=False)


def downgrade() -> None:
    # Dropping a table also drops its indexes.
    op.drop_table('messages')
    op.drop_table('sessions')
    op.drop_table('users')
    op.drop_table('event_logs')
