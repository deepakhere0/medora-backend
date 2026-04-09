from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AdminUserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str | None
    phone: str | None
    role: str
    is_active: bool
    organization_id: UUID | None
    organization_name: str | None
    created_at: datetime


class AdminUsersResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    users: list[AdminUserBrief]
    total: int


class ToggleActiveRequest(BaseModel):
    is_active: bool


class UpdateRoleRequest(BaseModel):
    role: str


class AdminOrgBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    city: str
    state: str
    address: str | None
    pincode: str | None
    phone: str | None
    is_approved: bool
    admin_email: str | None
    doctor_count: int
    patient_count: int
    registration_number: str | None = None
    registration_certificate_url: str | None = None
    created_at: datetime


class AdminOrgsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organizations: list[AdminOrgBrief]
    total: int


class AdminStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_users: int
    total_organizations: int
    total_patients: int
    total_doctors: int
    total_appointments: int
    pending_approvals: int
