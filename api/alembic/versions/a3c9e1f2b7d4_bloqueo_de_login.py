"""bloqueo de login por intentos fallidos

Revision ID: a3c9e1f2b7d4
Revises: 6f7ea6220e69
Create Date: 2026-09-16 12:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c9e1f2b7d4'
down_revision: str | None = '6f7ea6220e69'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('login_attempt',
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('failures', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('email')
    )


def downgrade() -> None:
    op.drop_table('login_attempt')
