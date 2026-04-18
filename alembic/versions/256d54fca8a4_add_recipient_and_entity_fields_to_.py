"""add recipient and entity fields to notifications

Revision ID: 256d54fca8a4
Revises: 2d6d4d5c97dd
Create Date: 2026-04-18 17:11:20.800943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID


revision: str = '256d54fca8a4'
down_revision: Union[str, None] = '2d6d4d5c97dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('notifications', sa.Column(
        'recipient_user_id',
        PgUUID(as_uuid=True),
        sa.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=True,
    ))
    op.create_index('ix_notifications_recipient_user_id', 'notifications', ['recipient_user_id'])

    op.add_column('notifications', sa.Column(
        'recipient_patient_id',
        PgUUID(as_uuid=True),
        sa.ForeignKey('patients.id', ondelete='CASCADE'),
        nullable=True,
    ))
    op.create_index('ix_notifications_recipient_patient_id', 'notifications', ['recipient_patient_id'])

    op.add_column('notifications', sa.Column('related_entity_type', sa.String(), nullable=True))
    op.add_column('notifications', sa.Column(
        'related_entity_id',
        PgUUID(as_uuid=True),
        nullable=True,
    ))


def downgrade() -> None:
    op.drop_column('notifications', 'related_entity_id')
    op.drop_column('notifications', 'related_entity_type')
    op.drop_index('ix_notifications_recipient_patient_id', table_name='notifications')
    op.drop_column('notifications', 'recipient_patient_id')
    op.drop_index('ix_notifications_recipient_user_id', table_name='notifications')
    op.drop_column('notifications', 'recipient_user_id')
