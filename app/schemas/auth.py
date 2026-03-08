from uuid import UUID

from pydantic import BaseModel

from app.models.user import UserRole


class LoginResponse(BaseModel):
    access_token:    str
    token_type:      str
    user_id:         UUID
    email:           str
    role:            str
    organization_id: UUID | None
