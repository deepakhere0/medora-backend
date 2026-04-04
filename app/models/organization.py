import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel


class Organization(BaseModel):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    operating_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    departments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    users = relationship("User", back_populates="organization", foreign_keys="User.organization_id")
    doctors = relationship("Doctor", back_populates="organization")
    appointments = relationship("Appointment", back_populates="organization", lazy="noload")
    reports = relationship("Report", back_populates="organization", lazy="noload")
    medical_histories = relationship("MedicalHistory", back_populates="organization", lazy="noload")
    doctor_schedules = relationship("DoctorSchedule", back_populates="organization", lazy="noload")
