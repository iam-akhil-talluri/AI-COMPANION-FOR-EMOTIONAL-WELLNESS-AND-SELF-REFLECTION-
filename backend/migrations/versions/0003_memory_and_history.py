"""Cross-session memory: per-user setting, per-session summary, and the purpose of each AI call.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.types

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('memory_enabled', sa.Boolean(), server_default='1', nullable=False))

    with op.batch_alter_table('sessions') as batch_op:
        batch_op.add_column(sa.Column('summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('summary_updated_at', app.db.types.UTCDateTime(), nullable=True))
        batch_op.add_column(sa.Column('summarized_count', sa.Integer(), server_default='0', nullable=False))

    with op.batch_alter_table('interactions') as batch_op:
        batch_op.add_column(sa.Column('purpose', sa.String(length=20), server_default='chat', nullable=False))
        batch_op.create_check_constraint('ck_interactions_purpose', "purpose IN ('chat', 'summary')")


def downgrade() -> None:
    with op.batch_alter_table('interactions') as batch_op:
        batch_op.drop_constraint('ck_interactions_purpose', type_='check')
        batch_op.drop_column('purpose')

    with op.batch_alter_table('sessions') as batch_op:
        batch_op.drop_column('summarized_count')
        batch_op.drop_column('summary_updated_at')
        batch_op.drop_column('summary')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('memory_enabled')
