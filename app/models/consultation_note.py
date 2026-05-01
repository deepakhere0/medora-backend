"""
consultation_note.py

Stores doctor notes written during a consultation session.
Each note is scoped to a (doctor, patient) pair so a doctor
can only read/write notes for their own patients.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ConsultationNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Doctor-authored clinical notes for a specific patient."""

    __tablename__ = "consultation_notes"

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
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    doctor: Mapped["Doctor"] = relationship("Doctor", lazy="noload")
    patient: Mapped["Patient"] = relationship("Patient", lazy="noload")
