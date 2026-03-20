import re
import uuid
from datetime import datetime

from pydantic import EmailStr, BaseModel, ConfigDict, field_validator

from app.models.user import UserRole
from app.schemas.base import BaseSchema


# Add this new class — login only needs email and password
class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # reject any unexpected fields
    email: EmailStr
    password: str


class UserCreate(BaseSchema):
    email: EmailStr
    password: str
    role: UserRole = UserRole.patient


class UserResponse(BaseSchema):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    organization_id: uuid.UUID | None
    name: str | None = None
    phone: str | None = None
    created_at: datetime


class UserProfileUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class UserProfileResponse(BaseSchema):
    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    organization_id: uuid.UUID | None
    name: str | None
    phone: str | None
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v
