"""
Patient represents an individual receiving medical care within a tenant
organization. All patient records are scoped to an organization, ensuring
strict multi-tenant isolation. Patients are linked to appointments and
drive clinical workflows across the MEDORA platform.
"""

import enum
import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PatientGender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class PatientBloodType(str, enum.Enum):
    A_pos = "A_pos"
    A_neg = "A_neg"
    B_pos = "B_pos"
    B_neg = "B_neg"
    O_pos = "O_pos"
    O_neg = "O_neg"
    AB_pos = "AB_pos"
    AB_neg = "AB_neg"


patient_gender_enum = ENUM(
    "male", "female", "other",
    name="patient_gender",
    create_type=False,
)

patient_blood_type_enum = ENUM(
    "A_pos", "A_neg",
    "B_pos", "B_neg",
    "O_pos", "O_neg",
    "AB_pos", "AB_neg",
    name="patient_blood_type",
    create_type=False,
)


class Patient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patients"

    __table_args__ = (
        UniqueConstraint("organization_id", "patient_code", name="uq_patients_org_code"),
        UniqueConstraint("organization_id", "phone", name="uq_patients_org_phone"),
        Index("ix_patients_org_name", "organization_id", "name"),
        Index("ix_patients_org_is_active", "organization_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gender: Mapped[str] = mapped_column(patient_gender_enum, nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    blood_type: Mapped[str | None] = mapped_column(patient_blood_type_enum, nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    blood_pressure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    appointments = relationship("Appointment", back_populates="patient", lazy="noload")
    reports = relationship("Report", back_populates="patient", lazy="noload")
    medical_histories = relationship("MedicalHistory", back_populates="patient", lazy="noload")
