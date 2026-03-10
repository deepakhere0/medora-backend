import uuid
from datetime import datetime

from app.schemas.base import BaseSchema


class OrganizationCreate(BaseSchema):
    name: str
    city: str
    state: str


class OrganizationResponse(BaseSchema):
    id: uuid.UUID
    name: str
    city: str
    state: str
    is_approved: bool
    created_by: uuid.UUID | None = None
    created_at: datetime
