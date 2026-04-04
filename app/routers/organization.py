import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import String, cast, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_role
from app.core.storage import upload_logo
from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.patient_organization import PatientOrganization
from app.models.user import User, UserRole
from app.schemas.organization import (
    HospitalRegistrationRequest,
    HospitalRegistrationResponse,
    OrganizationCreate,
    OrganizationDetailResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.organization_service import (
    approve_organization,
    create_organization,
    get_pending_organizations,
    register_hospital,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post(
    "/register",
    response_model=HospitalRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_hospital_endpoint(
    data: HospitalRegistrationRequest,
    db: AsyncSession = Depends(get_db),
):
    return await register_hospital(db, data)


@router.post("/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization_endpoint(
    org_data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
):
    return await create_organization(db, None, org_data)


@router.get("/pending", response_model=list[OrganizationResponse])
async def get_pending_organizations_endpoint(
    _: User = Depends(require_role(UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    return await get_pending_organizations(db)


@router.patch("/{org_id}/approve", response_model=OrganizationResponse)
async def approve_organization_endpoint(
    org_id: uuid.UUID,
    _: User = Depends(require_role(UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    return await approve_organization(db, org_id)


@router.get("/me", response_model=OrganizationDetailResponse)
async def get_my_organization(
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization linked to your account",
        )
    result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org


@router.put("/me", response_model=OrganizationDetailResponse)
async def update_my_organization(
    payload: OrganizationUpdate,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization linked to your account",
        )
    result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    if payload.name is not None and payload.name != org.name:
        existing = await db.execute(
            select(Organization).where(Organization.name == payload.name)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An organization with this name already exists",
            )
        org.name = payload.name

    update_fields = ["address", "city", "state", "pincode", "phone", "email", "website", "description", "operating_hours", "departments"]
    for field in update_fields:
        value = getattr(payload, field)
        if value is not None:
            setattr(org, field, value)

    await db.commit()
    await db.refresh(org)
    return org


@router.post("/upload-logo", response_model=dict, status_code=status.HTTP_200_OK)
async def upload_organization_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization linked to your account",
        )

    allowed_types = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PNG, JPG, JPEG, and WEBP images are allowed",
        )

    result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    file_bytes = await file.read()
    logo_url = upload_logo(
        file_bytes=file_bytes,
        file_name=file.filename or "logo",
        content_type=file.content_type,
        org_id=current_user.organization_id,
    )

    org.logo_url = logo_url
    await db.commit()
    return {"logo_url": logo_url}


@router.post("/departments", response_model=dict, status_code=status.HTTP_200_OK)
async def add_department(
    body: dict,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name is required")

    if current_user.organization_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No organization linked to your account")

    result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    departments: list = list(org.departments or [])
    if name in departments:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department already exists")

    departments.append(name)
    org.departments = departments
    await db.commit()
    return {"departments": departments}


@router.delete("/departments/{department_name}", response_model=dict, status_code=status.HTTP_200_OK)
async def remove_department(
    department_name: str,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.organization_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No organization linked to your account")

    result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    departments: list = list(org.departments or [])
    if department_name not in departments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    departments.remove(department_name)
    org.departments = departments
    await db.commit()
    return {"departments": departments}


# ---------------------------------------------------------------------------
# Global search
# ---------------------------------------------------------------------------

class SearchPatient(BaseModel):
    id: uuid.UUID
    name: str
    phone: str
    patient_code: str


class SearchDoctor(BaseModel):
    id: uuid.UUID
    name: str
    specialization: str
    status: str


class SearchAppointment(BaseModel):
    id: uuid.UUID
    patient_name: str | None
    doctor_name: str | None
    date: date
    status: str


class GlobalSearchResponse(BaseModel):
    patients: list[SearchPatient]
    doctors: list[SearchDoctor]
    appointments: list[SearchAppointment]


@router.get("/search", response_model=GlobalSearchResponse, status_code=status.HTTP_200_OK)
async def global_search(
    query: str = Query(..., min_length=1, max_length=100),
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> GlobalSearchResponse:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization is not set up yet",
        )
    org_id = current_user.organization_id
    pattern = f"%{query}%"

    # Patients linked to this org via patient_organizations junction
    patient_rows = await db.execute(
        select(Patient)
        .join(PatientOrganization, PatientOrganization.patient_id == Patient.id)
        .where(
            PatientOrganization.organization_id == org_id,
            PatientOrganization.is_active.is_(True),
            (Patient.name.ilike(pattern)) | (Patient.phone.ilike(pattern)),
        )
        .limit(5)
    )
    patients = [
        SearchPatient(
            id=p.id,
            name=p.name,
            phone=p.phone,
            patient_code=p.patient_code,
        )
        for p in patient_rows.scalars().all()
    ]

    # Doctors scoped to this org
    doctor_rows = await db.execute(
        select(Doctor)
        .where(
            Doctor.organization_id == org_id,
            Doctor.is_active.is_(True),
            (Doctor.name.ilike(pattern)) | (Doctor.specialization.ilike(pattern)),
        )
        .limit(5)
    )
    doctors = [
        SearchDoctor(
            id=d.id,
            name=d.name,
            specialization=d.specialization,
            status=d.status,
        )
        for d in doctor_rows.scalars().all()
    ]

    # Appointments scoped to this org — search by ID text representation
    appt_rows = await db.execute(
        select(Appointment, Patient.name.label("patient_name"), Doctor.name.label("doctor_name"))
        .outerjoin(Patient, Patient.id == Appointment.patient_id)
        .outerjoin(Doctor, Doctor.id == Appointment.doctor_id)
        .where(
            Appointment.organization_id == org_id,
            Appointment.is_active.is_(True),
            cast(Appointment.id, String).ilike(pattern),
        )
        .limit(5)
    )
    appointments = [
        SearchAppointment(
            id=row.Appointment.id,
            patient_name=row.patient_name,
            doctor_name=row.doctor_name,
            date=row.Appointment.appointment_date,
            status=row.Appointment.status,
        )
        for row in appt_rows.all()
    ]

    return GlobalSearchResponse(patients=patients, doctors=doctors, appointments=appointments)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class NotificationRead(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    notifications: list[NotificationRead]
    unread_count: int


def _require_org(current_user: User) -> uuid.UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization is not set up yet",
        )
    return current_user.organization_id


@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_notifications(
    unread_only: bool = False,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    org_id = _require_org(current_user)

    filters = [Notification.organization_id == org_id]
    if unread_only:
        filters.append(Notification.is_read.is_(False))

    rows = await db.execute(
        select(Notification)
        .where(*filters)
        .order_by(Notification.created_at.desc())
    )
    notifications = rows.scalars().all()

    unread_count_row = await db.execute(
        select(Notification).where(
            Notification.organization_id == org_id,
            Notification.is_read.is_(False),
        )
    )
    unread_count = len(unread_count_row.scalars().all())

    return NotificationListResponse(
        notifications=list(notifications),
        unread_count=unread_count,
    )


@router.put(
    "/notifications/read-all",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def mark_all_read(
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = _require_org(current_user)
    await db.execute(
        update(Notification)
        .where(
            Notification.organization_id == org_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.commit()
    return {"success": True}


@router.put(
    "/notifications/{notification_id}/read",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.org_admin)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = _require_org(current_user)
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.organization_id == org_id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    notification.is_read = True
    await db.commit()
    return {"success": True}
