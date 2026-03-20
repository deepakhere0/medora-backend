import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    org_admin = "org_admin"
    patient = "patient"


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )

    organization = relationship("Organization", back_populates="users", foreign_keys="User.organization_id")
    reports = relationship("Report", back_populates="uploader", lazy="noload", foreign_keys="[Report.uploaded_by]")
    medical_histories = relationship("MedicalHistory", back_populates="recorder", lazy="noload", foreign_keys="[MedicalHistory.recorded_by]")
