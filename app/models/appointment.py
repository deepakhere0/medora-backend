import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import ENUM as PgENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class AppointmentStatus(str, enum.Enum):
    pending = "pending"
    scheduled = "scheduled"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    rejected = "rejected"


class AppointmentType(str, enum.Enum):
    walk_in = "walk_in"
    scheduled = "scheduled"


appointment_status_enum = PgENUM(
    "pending",
    "scheduled",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled",
    "rejected",
    name="appointment_status",
    create_type=False,
)

appointment_type_enum = PgENUM(
    "walk_in",
    "scheduled",
    name="appointment_type",
    create_type=False,
)


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Central scheduling entity in MEDORA.
    Connects a patient to a doctor at a specific date and time,
    scoped to a tenant organization.
    """

    __tablename__ = "appointments"

    __table_args__ = (
        Index("ix_appt_org_date", "organization_id", "appointment_date"),
        Index("ix_appt_org_doctor_date", "organization_id", "doctor_id", "appointment_date"),
        Index("ix_appt_org_patient", "organization_id", "patient_id"),
        Index("ix_appt_org_status", "organization_id", "status"),
        {},
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    appointment_type: Mapped[str] = mapped_column(
        appointment_type_enum,
        nullable=False,
        server_default="scheduled",
    )
    status: Mapped[str] = mapped_column(
        appointment_status_enum,
        nullable=False,
        server_default="scheduled",
    )
    booking_id: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancel_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    consultation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consultation_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    booking_for: Mapped[str] = mapped_column(String, nullable=False, default="self", server_default="self")
    guest_name: Mapped[str | None] = mapped_column(String, nullable=True)
    guest_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    guest_sex: Mapped[str | None] = mapped_column(String, nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    guest_email: Mapped[str | None] = mapped_column(String, nullable=True)
    video_channel: Mapped[str | None] = mapped_column(String, nullable=True)

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="appointments", lazy="noload"
    )
    doctor: Mapped["Doctor"] = relationship(
        "Doctor", back_populates="appointments", lazy="noload"
    )
    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="appointments", lazy="noload"
    )
    reports: Mapped[list["Report"]] = relationship(
        "Report", back_populates="appointment", lazy="noload"
    )
    medical_histories: Mapped[list["MedicalHistory"]] = relationship(
        "MedicalHistory", back_populates="appointment", lazy="noload"
    )
    reviews: Mapped[list["Review"]] = relationship(
        "Review", back_populates="appointment", lazy="noload"
    )
    online_consultations: Mapped[list["OnlineConsultation"]] = relationship(
        "OnlineConsultation", back_populates="appointment", lazy="noload"
    )
