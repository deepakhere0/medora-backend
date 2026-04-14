"""
Doctor represents a licensed medical professional within MEDORA.

Supports two modes:
  - Hospital-affiliated: linked to an Organization (organization_id set,
    is_independent=False). Created by org_admin via the hospital workflow.
  - Independent / self-registered: no Organization (organization_id=None,
    is_independent=True, self_registered=True). Created by the doctor
    themselves and discoverable via the patient-facing search.

All scheduling, availability, and clinical workflows apply to both types.
"""

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Float,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DoctorGender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class DoctorEmploymentType(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
    visiting = "visiting"


class DoctorStatus(str, enum.Enum):
    active = "active"
    on_duty = "on_duty"
    on_call = "on_call"
    on_leave = "on_leave"
    inactive = "inactive"


doctor_gender_enum = ENUM(
    "male", "female", "other",
    name="doctor_gender",
    create_type=True,
)

doctor_employment_type_enum = ENUM(
    "full_time", "part_time", "visiting",
    name="doctor_employment_type",
    create_type=True,
)

doctor_status_enum = ENUM(
    "active", "on_duty", "on_call", "on_leave", "inactive",
    name="doctor_status",
    create_type=True,
)


class Doctor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "doctors"

    __table_args__ = (
        UniqueConstraint("organization_id", "license_number", name="uq_doctors_org_license"),
        Index("ix_doctors_org_specialization", "organization_id", "specialization"),
        Index("ix_doctors_org_status", "organization_id", "status"),
    )

    # Link to the User account — only set for self-registered doctors.
    # NULL for hospital-affiliated doctors created by org_admin.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )

    # Nullable: independent doctors are not affiliated with any organization.
    organization_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gender: Mapped[str] = mapped_column(doctor_gender_enum, nullable=False)
    specialization: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    experience_years: Mapped[int] = mapped_column(Integer, nullable=False)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_number: Mapped[str] = mapped_column(String(100), nullable=False)
    license_expiry: Mapped[date] = mapped_column(Date, nullable=False)
    employment_type: Mapped[str] = mapped_column(doctor_employment_type_enum, nullable=False)
    certifications: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        doctor_status_enum,
        nullable=False,
        default="active",
        index=True,
    )
    staff_record: Mapped[str | None] = mapped_column(String(100), nullable=True)
    medical_council: Mapped[str | None] = mapped_column(String, nullable=True)
    registration_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registration_certificate_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ------------------------------------------------------------------
    # Independent / self-registration fields
    # ------------------------------------------------------------------
    is_independent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    self_registered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="True after NMC registration number is verified"
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Set when super_admin rejects a doctor registration; NULL means pending or verified"
    )
    nmc_registration_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True,
        comment="National Medical Council registration number — globally unique"
    )

    # ------------------------------------------------------------------
    # Discovery / patient-facing profile fields
    # ------------------------------------------------------------------
    specialty: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Patient-facing specialty label, e.g. 'General Physician'"
    )
    degree: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
        comment="Formal qualifications, e.g. 'MBBS, MD (Medicine)'"
    )
    about_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="TEXT (not VARCHAR) — Supabase signed URLs can exceed 700 chars"
    )
    languages_spoken: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Comma-separated list, e.g. 'Hindi,English,Punjabi'"
    )

    # ------------------------------------------------------------------
    # Fees
    # ------------------------------------------------------------------
    consultation_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0",
        comment="In-clinic fee in INR"
    )
    online_consultation_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0"
    )
    is_available_online: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # ------------------------------------------------------------------
    # Location (for proximity search)
    # ------------------------------------------------------------------
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ------------------------------------------------------------------
    # Cached review aggregates (updated by trigger or background job)
    # ------------------------------------------------------------------
    average_rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=0, server_default="0"
    )
    total_reviews: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user = relationship("User", lazy="noload", foreign_keys="Doctor.user_id")
    organization = relationship("Organization", back_populates="doctors")
    appointments = relationship("Appointment", back_populates="doctor", lazy="noload")
    schedules = relationship("DoctorSchedule", back_populates="doctor", lazy="noload")
    reviews = relationship("Review", back_populates="doctor", lazy="noload")
    online_consultations = relationship("OnlineConsultation", back_populates="doctor", lazy="noload")
