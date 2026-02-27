import uuid
from datetime import datetime

from pydantic import EmailStr

from app.models.user import UserRole
from app.schemas.base import BaseSchema


class UserCreate(BaseSchema):
    email: EmailStr
    password: str
    role: UserRole = UserRole.patient


class UserResponse(BaseSchema):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime
