"""
Review represents a patient's rating and feedback for a doctor.

Key rules:
  - Tied to a real appointment (appointment_id) when is_verified=True,
    ensuring the patient actually visited the doctor.
  - UNIQUE(doctor_id, appointment_id) prevents duplicate reviews for the
    same visit (NULL appointment_id is excluded from this constraint by
    PostgreSQL's standard NULL-safe UNIQUE behaviour).
  - Rating must be 1–5 (enforced by DB CHECK constraint).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class Review(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reviews"

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        UniqueConstraint("doctor_id", "appointment_id", name="uq_reviews_doctor_appointment"),
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
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="True when the review is linked to a completed appointment"
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    doctor = relationship("Doctor", back_populates="reviews", lazy="noload")
    patient = relationship("Patient", back_populates="reviews", lazy="noload")
    appointment = relationship("Appointment", back_populates="reviews", lazy="noload")
