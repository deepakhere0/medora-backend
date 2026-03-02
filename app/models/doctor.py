"""
Doctor represents a licensed medical professional within a tenant organization.
All doctor records are scoped to an organization, ensuring strict multi-tenant
isolation. Doctors are linked to appointments and drive scheduling, availability,
and clinical workflows across the MEDORA platform.
"""

import enum
from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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

    organization_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
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
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    organization = relationship("Organization", back_populates="doctors")
    appointments = relationship("Appointment", back_populates="doctor", lazy="noload")
