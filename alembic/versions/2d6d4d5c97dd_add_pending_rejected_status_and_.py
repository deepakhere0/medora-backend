"""add pending rejected status and confirmation fields to appointment

Revision ID: 2d6d4d5c97dd
Revises: 3568b6513c95
Create Date: 2026-04-18 17:02:31.862288

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2d6d4d5c97dd'
down_revision: Union[str, None] = '3568b6513c95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend the PostgreSQL enum — ADD VALUE is non-transactional in Postgres,
    # so we use IF NOT EXISTS for idempotency.
    op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'pending'")
    op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'rejected'")

    op.add_column('appointments', sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('appointments', sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('appointments', sa.Column('rejection_reason', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('appointments', 'rejection_reason')
    op.drop_column('appointments', 'rejected_at')
    op.drop_column('appointments', 'confirmed_at')
    # Postgres does not support DROP VALUE on enums; remove 'pending'/'rejected'
    # manually if a full rollback is needed.
