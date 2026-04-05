"""change_blood_type_enum_to_varchar

Revision ID: 2a7f3e9b1c05
Revises: 1814c1f0fe94
Create Date: 2026-03-27 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2a7f3e9b1c05'
down_revision: Union[str, None] = '1814c1f0fe94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'patients',
        'blood_type',
        type_=sa.String(10),
        postgresql_using='blood_type::text',
        existing_nullable=True,
    )
    op.execute('DROP TYPE IF EXISTS patient_blood_type')


def downgrade() -> None:
    # Recreating the ENUM and casting back is intentionally left as a no-op
    # because restoring data that was saved in free-form (e.g. "B+") into a
    # strict ENUM would require a manual data-clean step.
    pass
