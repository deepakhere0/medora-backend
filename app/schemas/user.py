import uuid
from datetime import datetime

from pydantic import EmailStr, BaseModel, ConfigDict

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
    created_at: datetime
