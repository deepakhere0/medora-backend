"""reconcile_patient_blood_type_and_add_vitals

Replaces the initial patient_blood_type ENUM values (A_positive … O_negative)
with the canonical short-form values used by the API (A_pos … O_neg), and
adds the height_cm, weight_kg, and blood_pressure vital-signs columns.

Safe to run on an empty patients table — no data migration required.

Revision ID: a372fea3c1a4
Revises: 03640bbb436b
Create Date: 2026-03-02 01:52:02.677750

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a372fea3c1a4"
down_revision: Union[str, None] = "03640bbb436b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_BLOOD_VALUES = (
    "A_positive", "A_negative",
    "B_positive", "B_negative",
    "AB_positive", "AB_negative",
    "O_positive", "O_negative",
)
_NEW_BLOOD_VALUES = (
    "A_pos", "A_neg",
    "B_pos", "B_neg",
    "O_pos", "O_neg",
    "AB_pos", "AB_neg",
)


def upgrade() -> None:
    # ── 1. Release the column from the old enum type ──────────────────────
    op.execute("ALTER TABLE patients ALTER COLUMN blood_type TYPE text USING blood_type::text")

    # ── 2. Drop the old enum (no existing rows, so no residual dependencies) ──
    op.execute("DROP TYPE patient_blood_type")

    # ── 3. Create the new enum with canonical short-form values ───────────
    new_values = ", ".join(f"'{v}'" for v in _NEW_BLOOD_VALUES)
    op.execute(f"CREATE TYPE patient_blood_type AS ENUM ({new_values})")

    # ── 4. Cast the column back to the new enum type ──────────────────────
    op.execute(
        "ALTER TABLE patients "
        "ALTER COLUMN blood_type TYPE patient_blood_type "
        "USING blood_type::patient_blood_type"
    )

    # ── 5. Add vital-signs columns ────────────────────────────────────────
    op.add_column("patients", sa.Column("height_cm", sa.Float(), nullable=True))
    op.add_column("patients", sa.Column("weight_kg", sa.Float(), nullable=True))
    op.add_column("patients", sa.Column("blood_pressure", sa.String(length=20), nullable=True))


def downgrade() -> None:
    # ── 1. Drop vital-signs columns ───────────────────────────────────────
    op.drop_column("patients", "blood_pressure")
    op.drop_column("patients", "weight_kg")
    op.drop_column("patients", "height_cm")

    # ── 2. Release column from new enum ───────────────────────────────────
    op.execute("ALTER TABLE patients ALTER COLUMN blood_type TYPE text USING blood_type::text")

    # ── 3. Drop new enum ──────────────────────────────────────────────────
    op.execute("DROP TYPE patient_blood_type")

    # ── 4. Restore original enum ──────────────────────────────────────────
    old_values = ", ".join(f"'{v}'" for v in _OLD_BLOOD_VALUES)
    op.execute(f"CREATE TYPE patient_blood_type AS ENUM ({old_values})")

    # ── 5. Cast column back to original enum ──────────────────────────────
    op.execute(
        "ALTER TABLE patients "
        "ALTER COLUMN blood_type TYPE patient_blood_type "
        "USING blood_type::patient_blood_type"
    )
