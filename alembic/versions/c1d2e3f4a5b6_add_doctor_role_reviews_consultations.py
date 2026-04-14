"""add doctor role, independent doctor columns, reviews, online_consultations

Revision ID: c1d2e3f4a5b6
Revises: a9b8c7d6e5f4
Create Date: 2026-04-14 00:00:00.000000

Changes:
  1. Add 'doctor' value to userrole enum
  2. Make doctors.organization_id nullable (independent doctors have no org)
  3. Add new columns to doctors table for self-registration / discovery
  4. Create reviews table (UUID PK, references doctors+patients+appointments)
  5. Create online_consultations table (UUID PK)
  6. Add performance indexes
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# UPGRADE
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add 'doctor' to the userrole enum.
    #    ALTER TYPE … ADD VALUE cannot run inside a transaction block in
    #    PostgreSQL, so we use Alembic's autocommit_block() context manager
    #    which temporarily commits and re-starts the session.
    # ------------------------------------------------------------------
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'doctor'"))

    # ------------------------------------------------------------------
    # 2. Make doctors.organization_id nullable
    #    Independent doctors are not affiliated with any organization.
    # ------------------------------------------------------------------
    op.alter_column(
        "doctors",
        "organization_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # 3. Add new columns to the doctors table.
    #    All columns are nullable or have defaults so existing rows are
    #    unaffected (hospital-affiliated doctors already in the DB).
    # ------------------------------------------------------------------
    op.add_column("doctors", sa.Column("is_independent", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("doctors", sa.Column("self_registered", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("doctors", sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("doctors", sa.Column("nmc_registration_number", sa.String(100), nullable=True))
    op.add_column("doctors", sa.Column("specialty", sa.String(100), nullable=True))
    op.add_column("doctors", sa.Column("consultation_fee", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")))
    op.add_column("doctors", sa.Column("online_consultation_fee", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")))
    op.add_column("doctors", sa.Column("is_available_online", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("doctors", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("doctors", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("doctors", sa.Column("languages_spoken", sa.Text(), nullable=True))
    op.add_column("doctors", sa.Column("profile_photo_url", sa.Text(), nullable=True))
    op.add_column("doctors", sa.Column("about_text", sa.Text(), nullable=True))
    op.add_column("doctors", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("doctors", sa.Column("pincode", sa.String(10), nullable=True))
    op.add_column("doctors", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("doctors", sa.Column("state", sa.String(100), nullable=True))
    op.add_column("doctors", sa.Column("average_rating", sa.Numeric(3, 2), nullable=False, server_default=sa.text("0")))
    op.add_column("doctors", sa.Column("total_reviews", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("doctors", sa.Column("degree", sa.String(200), nullable=True))

    # Unique constraint for NMC registration number (globally unique)
    op.create_unique_constraint("uq_doctors_nmc_registration", "doctors", ["nmc_registration_number"])

    # ------------------------------------------------------------------
    # 4. Create the reviews table
    #    Uses UUID PKs to match the rest of the MEDORA data model.
    #    One review per appointment (UNIQUE on doctor_id + appointment_id).
    # ------------------------------------------------------------------
    op.create_table(
        "reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("doctor_id", UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appointment_id", UUID(as_uuid=True), sa.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        sa.UniqueConstraint("doctor_id", "appointment_id", name="uq_reviews_doctor_appointment"),
    )

    # ------------------------------------------------------------------
    # 5. Create the online_consultations table
    # ------------------------------------------------------------------
    op.create_table(
        "online_consultations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("doctor_id", UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("appointment_id", UUID(as_uuid=True), sa.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("consultation_type", sa.String(20), nullable=False, server_default=sa.text("'video'")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("meeting_room_id", sa.String(200), nullable=True),
        sa.Column("prescription_text", sa.Text(), nullable=True),
        sa.Column("consultation_fee", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("payment_status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------
    # 6. Performance indexes
    # ------------------------------------------------------------------
    # doctors — location-based search
    op.create_index(
        "idx_doctors_location",
        "doctors",
        ["latitude", "longitude"],
        postgresql_where=sa.text("latitude IS NOT NULL"),
    )
    # doctors — specialty filter
    op.create_index(
        "idx_doctors_specialty",
        "doctors",
        ["specialty"],
        postgresql_where=sa.text("specialty IS NOT NULL"),
    )
    # doctors — independent-only listing
    op.create_index(
        "idx_doctors_independent",
        "doctors",
        ["is_independent"],
        postgresql_where=sa.text("is_independent = true"),
    )
    # doctors — NMC-verified listing
    op.create_index(
        "idx_doctors_verified",
        "doctors",
        ["is_verified"],
        postgresql_where=sa.text("is_verified = true"),
    )
    # reviews
    op.create_index("idx_reviews_doctor", "reviews", ["doctor_id"])
    # online_consultations
    op.create_index("idx_consultations_doctor", "online_consultations", ["doctor_id"])
    op.create_index("idx_consultations_patient", "online_consultations", ["patient_id"])


# ---------------------------------------------------------------------------
# DOWNGRADE
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_consultations_patient", table_name="online_consultations")
    op.drop_index("idx_consultations_doctor", table_name="online_consultations")
    op.drop_index("idx_reviews_doctor", table_name="reviews")
    op.drop_index("idx_doctors_verified", table_name="doctors")
    op.drop_index("idx_doctors_independent", table_name="doctors")
    op.drop_index("idx_doctors_specialty", table_name="doctors")
    op.drop_index("idx_doctors_location", table_name="doctors")

    # Drop new tables
    op.drop_table("online_consultations")
    op.drop_table("reviews")

    # Drop new doctor columns
    for col in [
        "degree", "total_reviews", "average_rating", "state", "city",
        "pincode", "address", "about_text", "profile_photo_url",
        "languages_spoken", "longitude", "latitude", "is_available_online",
        "online_consultation_fee", "consultation_fee", "specialty",
        "nmc_registration_number", "is_verified", "self_registered", "is_independent",
    ]:
        op.drop_column("doctors", col)

    # Restore doctors.organization_id to NOT NULL
    op.alter_column(
        "doctors",
        "organization_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )

    # NOTE: PostgreSQL does not support removing an enum value.
    # The 'doctor' value added to userrole cannot be undone via ALTER TYPE.
    # To fully revert, recreate the enum type without 'doctor' if needed.
