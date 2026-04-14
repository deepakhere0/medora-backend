from datetime import datetime
from decimal import Decimal
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


# ---------------------------------------------------------------------------
# Admin — Doctor management
# ---------------------------------------------------------------------------

class AdminDoctorBrief(BaseModel):
    """Summary row used in the paginated doctor list."""
    id: UUID
    name: str
    email: str | None
    phone: str | None
    specialty: str | None
    nmc_registration_number: str | None
    is_verified: bool
    is_active: bool            # user.is_active
    rejection_reason: str | None
    city: str | None
    state: str | None
    profile_photo_url: str | None
    registration_certificate_url: str | None
    created_at: datetime
    # Derived verification status: "pending" | "verified" | "rejected" | "suspended"
    verification_status: str


class AdminDoctorsResponse(BaseModel):
    doctors: list[AdminDoctorBrief]
    total: int
    page: int
    per_page: int
    total_pages: int


class AdminDoctorDetail(BaseModel):
    """Full doctor record returned by GET /admin/doctors/{doctor_id}."""
    id: UUID
    name: str
    email: str | None
    phone: str | None
    specialty: str | None
    specialization: str | None
    degree: str | None
    nmc_registration_number: str | None
    is_verified: bool
    is_active: bool
    rejection_reason: str | None
    verification_status: str
    city: str | None
    state: str | None
    address: str | None
    pincode: str | None
    latitude: float | None
    longitude: float | None
    profile_photo_url: str | None
    registration_certificate_url: str | None
    consultation_fee: Decimal
    online_consultation_fee: Decimal
    is_available_online: bool
    experience_years: int
    about_text: str | None
    languages_spoken: str | None
    average_rating: Decimal
    total_reviews: int
    is_independent: bool
    self_registered: bool
    user_id: UUID | None
    organization_id: UUID | None
    created_at: datetime


class RejectDoctorRequest(BaseModel):
    reason: str | None = None
