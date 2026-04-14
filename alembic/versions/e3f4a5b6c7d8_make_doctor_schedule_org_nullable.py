"""make doctor_schedules.organization_id nullable for independent doctors

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-04-15 00:00:00.000000

Independent / self-registered doctors have no organization_id.
The DoctorSchedule.organization_id column must be nullable so they can
manage their own weekly schedule without belonging to a hospital.

Existing hospital-affiliated schedules are unaffected (they keep their
non-null organization_id values).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "doctor_schedules",
        "organization_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # This will fail if any rows have NULL organization_id.
    # Clean those up manually before running downgrade.
    op.alter_column(
        "doctor_schedules",
        "organization_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )
