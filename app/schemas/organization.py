import uuid
from datetime import datetime

from pydantic import BaseModel

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


class OrganizationUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None


class OrganizationDetailResponse(BaseSchema):
    id: uuid.UUID
    name: str
    city: str
    state: str
    address: str | None
    phone: str | None
    email: str | None
    website: str | None
    logo_url: str | None
    is_approved: bool
    created_at: datetime
