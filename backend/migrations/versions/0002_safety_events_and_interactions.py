"""Safety events and interactions: anonymized safety decisions and AI usage metrics.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22 17:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.types

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('interactions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=True),
    sa.Column('safety_checked', sa.Boolean(), nullable=False),
    sa.Column('risk_level', sa.String(length=10), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('used_ai', sa.Boolean(), nullable=False),
    sa.Column('model', sa.String(length=80), nullable=True),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('estimated_cost_usd', sa.Float(), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
    sa.CheckConstraint("status IN ('ok', 'support', 'crisis', 'blocked', 'safety_error', 'ai_error')", name='ck_interactions_status'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_interactions_created_at'), 'interactions', ['created_at'], unique=False)

    op.create_table('safety_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.String(length=36), nullable=True),
    sa.Column('stage', sa.String(length=10), nullable=False),
    sa.Column('risk_level', sa.String(length=10), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
    sa.CheckConstraint("risk_level IN ('low', 'moderate', 'elevated', 'high')", name='ck_safety_events_risk_level'),
    sa.CheckConstraint("stage IN ('input', 'output')", name='ck_safety_events_stage'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_safety_events_created_at'), 'safety_events', ['created_at'], unique=False)
    op.create_index('ix_safety_events_session_created', 'safety_events', ['session_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_safety_events_session_created', table_name='safety_events')
    op.drop_index(op.f('ix_safety_events_created_at'), table_name='safety_events')
    op.drop_table('safety_events')
    op.drop_index(op.f('ix_interactions_created_at'), table_name='interactions')
    op.drop_table('interactions')
