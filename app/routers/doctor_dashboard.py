"""
doctor_dashboard.py

Authenticated endpoints for the doctor's own dashboard.
All routes are under /api/v1/doctor (prefix set in main.py).

Every endpoint requires role="doctor" — enforced via require_role(UserRole.doctor).
The service layer resolves the Doctor record from current_user.id via Doctor.user_id.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.doctor import DoctorProfileResponse
from app.schemas.doctor_dashboard import (
    DoctorAppointmentsResponse,
    DoctorDashboardResponse,
    DoctorPatientsResponse,
    DoctorReviewsResponse,
    EarningsResponse,
    ScheduleResponse,
    UpdateScheduleRequest,
    DoctorProfileUpdateRequest,
    DoctorPatientDetailResponse,
    UpsertConsultationNoteRequest,
    ConsultationNoteResponse,
    AuditLogResponse,
)
from app.services.doctor_dashboard_service import (
    get_doctor_appointments,
    get_doctor_dashboard,
    get_doctor_earnings,
    get_doctor_patients,
    get_doctor_reviews,
    get_doctor_schedule,
    update_doctor_profile,
    update_doctor_schedule,
    get_doctor_patient_detail,
    upsert_consultation_note,
    get_consultation_note,
)
from app.services.doctor_auth_service import get_doctor_profile

router = APIRouter(tags=["Doctor Dashboard"])


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard",
    response_model=DoctorDashboardResponse,
    summary="Doctor dashboard summary",
    description=(
        "Returns all key metrics for the doctor's home screen: "
        "today's appointments, earnings, rating, upcoming schedule, and recent reviews."
    ),
)
async def doctor_dashboard(
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> DoctorDashboardResponse:
    data = await get_doctor_dashboard(db, current_user)
    return DoctorDashboardResponse(**data)


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

@router.get(
    "/appointments",
    response_model=DoctorAppointmentsResponse,
    summary="Doctor's appointment list",
)
async def doctor_appointments(
    status: str = Query(
        default="upcoming",
        description="upcoming | completed | cancelled | all",
    ),
    date_from: date | None = Query(default=None, description="Filter from date (YYYY-MM-DD)"),
    date_to: date | None = Query(default=None, description="Filter to date (YYYY-MM-DD)"),
    type: str = Query(
        default="all",
        description="in_clinic | video | all",
    ),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> DoctorAppointmentsResponse:
    data = await get_doctor_appointments(
        db,
        user=current_user,
        appt_status=status,
        date_from=date_from,
        date_to=date_to,
        appt_type=type,
        page=page,
        per_page=per_page,
    )
    return DoctorAppointmentsResponse(**data)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@router.put(
    "/profile",
    response_model=DoctorProfileResponse,
    summary="Update doctor profile",
    description=(
        "Updates editable profile fields. "
        "nmc_registration_number and is_verified are immutable — they are silently ignored "
        "if included in the request body."
    ),
)
async def update_profile(
    body: DoctorProfileUpdateRequest,
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> DoctorProfileResponse:
    updates = body.model_dump(exclude_none=True)
    await update_doctor_profile(db, current_user, updates)
    # Return full profile using the same builder as GET /me
    return await get_doctor_profile(db, current_user)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@router.get(
    "/schedule",
    response_model=ScheduleResponse,
    summary="Get doctor's weekly schedule",
)
async def get_schedule(
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    schedules = await get_doctor_schedule(db, current_user)
    return ScheduleResponse(schedules=schedules)


@router.put(
    "/schedule",
    response_model=ScheduleResponse,
    summary="Replace doctor's weekly schedule",
    description=(
        "Full replace — the existing schedule is deleted and replaced with the submitted entries. "
        "Duplicate day_of_week values are rejected. "
        "start_time must be before end_time; break window must fall within working hours."
    ),
)
async def update_schedule(
    body: UpdateScheduleRequest,
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    schedules = await update_doctor_schedule(db, current_user, body.schedules)
    return ScheduleResponse(schedules=schedules)


# ---------------------------------------------------------------------------
# Earnings
# ---------------------------------------------------------------------------

@router.get(
    "/earnings",
    response_model=EarningsResponse,
    summary="Doctor's earnings report",
    description=(
        "Earnings = in-clinic (doctor.consultation_fee × completed appointments) "
        "+ online (sum of online_consultations.consultation_fee where status='completed', payment_status='paid'). "
        "comparison_percentage is relative to the previous equivalent period."
    ),
)
async def doctor_earnings(
    period: str = Query(
        default="this_month",
        description="this_month | last_month | this_year | custom",
    ),
    date_from: date | None = Query(default=None, description="Required for period='custom'"),
    date_to: date | None = Query(default=None, description="Required for period='custom'"),
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> EarningsResponse:
    data = await get_doctor_earnings(
        db,
        user=current_user,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    return EarningsResponse(**data)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

@router.get(
    "/reviews",
    response_model=DoctorReviewsResponse,
    summary="Reviews received by this doctor",
)
async def doctor_reviews(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> DoctorReviewsResponse:
    data = await get_doctor_reviews(db, current_user, page=page, per_page=per_page)
    return DoctorReviewsResponse(**data)


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

@router.get(
    "/patients",
    response_model=DoctorPatientsResponse,
    summary="Unique patients who have visited this doctor",
    description=(
        "Returns patients with at least one completed appointment with this doctor, "
        "ordered by most recent visit. Includes phone number for follow-up calls."
    ),
)
async def doctor_patients(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> DoctorPatientsResponse:
    data = await get_doctor_patients(db, current_user, page=page, per_page=per_page)
    return DoctorPatientsResponse(**data)


@router.get(
    "/patients/{patient_id}",
    response_model=DoctorPatientDetailResponse,
    summary="Get patient details for doctor",
    description="Returns patient details, their appointments with this doctor, and their uploaded reports."
)
async def doctor_patient_detail(
    patient_id: UUID,
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> DoctorPatientDetailResponse:
    data = await get_doctor_patient_detail(db, current_user, patient_id)
    return DoctorPatientDetailResponse(**data)


from typing import Optional

# ---------------------------------------------------------------------------
# Consultation Notes & Audit
# ---------------------------------------------------------------------------

@router.get(
    "/audit",
    response_model=list[AuditLogResponse],
    summary="Get recent audit logs for the doctor",
)
async def get_doctor_audit_logs(
    patient_id: Optional[UUID] = None,
    limit: int = 50,
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    from app.services.doctor_dashboard_service import get_audit_logs
    data = await get_audit_logs(db, current_user, patient_id, limit)
    return [AuditLogResponse(**item) for item in data]

@router.post(
    "/notes",
    response_model=ConsultationNoteResponse,
    summary="Create or update doctor note for a patient",
    description="Upserts a consultation note for the (doctor, patient) pair. Safe to call repeatedly.",
)
async def upsert_note(
    body: UpsertConsultationNoteRequest,
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> ConsultationNoteResponse:
    data = await upsert_consultation_note(
        db, current_user, body.patient_id, body.content, body.client_updated_at, body.version
    )
    return ConsultationNoteResponse(**data)


@router.get(
    "/notes/{patient_id}",
    response_model=ConsultationNoteResponse | None,
    summary="Get doctor note for a specific patient",
)
async def get_note(
    patient_id: UUID,
    current_user: User = Depends(require_role(UserRole.doctor)),
    db: AsyncSession = Depends(get_db),
) -> ConsultationNoteResponse | None:
    data = await get_consultation_note(db, current_user, patient_id)
    if data is None:
        return None
    return ConsultationNoteResponse(**data)
