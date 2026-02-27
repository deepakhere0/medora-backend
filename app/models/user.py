import enum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

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
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
