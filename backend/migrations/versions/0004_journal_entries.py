"""Journal entries: private journal writing from the Coping Tools screen.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-29 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.types

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('journal_entries',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('prompt', sa.String(length=300), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', app.db.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_journal_entries_created_at'), 'journal_entries', ['created_at'], unique=False)
    op.create_index('ix_journal_entries_user_created', 'journal_entries', ['user_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_journal_entries_user_created', table_name='journal_entries')
    op.drop_index(op.f('ix_journal_entries_created_at'), table_name='journal_entries')
    op.drop_table('journal_entries')
