import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

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
    pincode: str | None = None
    is_approved: bool
    created_by: uuid.UUID | None = None
    registration_number: str | None = None
    registration_certificate_url: str | None = None
    admin_email: str | None = None
    created_at: datetime


class OrganizationUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    description: str | None = None
    operating_hours: dict | None = None
    departments: list | None = None


class OrganizationDetailResponse(BaseSchema):
    id: uuid.UUID
    name: str
    city: str
    state: str
    pincode: str | None
    address: str | None
    phone: str | None
    email: str | None
    website: str | None
    description: str | None
    logo_url: str | None
    operating_hours: dict | None
    departments: list | None
    is_approved: bool
    registration_number: str | None = None
    registration_certificate_url: str | None = None
    created_at: datetime


class HospitalRegistrationRequest(BaseModel):
    # Organization details
    org_name: str
    org_city: str
    org_state: str
    org_address: str | None = None
    org_phone: str | None = None
    org_email: str | None = None
    registration_number: str
    pincode: str = Field(pattern=r'^[1-9][0-9]{5}$')

    # Admin user details
    admin_email: EmailStr
    admin_password: str
    admin_name: str | None = None
    admin_phone: str | None = None


class HospitalRegistrationResponse(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    user_id: uuid.UUID
    user_email: str
    is_approved: bool
    registration_number: str | None = None
    registration_certificate_url: str | None = None
    pincode: str | None = None
    message: str
