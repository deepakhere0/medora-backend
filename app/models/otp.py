import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OTPRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "otp_records"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    otp_code: Mapped[str] = mapped_column(String(6), nullable=False)
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, default="password_reset")
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)

    patient = relationship("Patient", lazy="noload")
