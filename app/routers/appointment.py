from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.appointment import (
    AppointmentCancelRequest,
    AppointmentCreate,
    AppointmentListResponse,
    AppointmentRead,
    AppointmentListItem,
    AppointmentRejectRequest,
    AppointmentStatus as SchemaStatus,
    AppointmentStatusUpdate,
    AppointmentStatsResponse,
    AppointmentUpdate,
    DoctorAppointmentItem,
    DoctorPendingCountResponse,
    WalkInAppointmentRequest,
    WalkInAppointmentResponse,
)
from app.services.appointment_service import (
    AppointmentRow,
    cancel_appointment,
    cancel_appointment_by_request,
    complete_appointment,
    confirm_appointment,
    create_appointment,
    create_walkin_appointment,
    get_appointment,
    get_appointment_stats,
    get_doctor_pending_appointments,
    get_doctor_pending_count,
    get_doctor_today_appointments,
    list_appointments,
    reject_appointment,
    start_appointment,
    update_appointment,
    update_appointment_status,
)

router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"],
)


def _get_org_id(current_user: User) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization is not set up yet",
        )
    return current_user.organization_id


@router.get(
    "/doctor/pending/count",
    response_model=DoctorPendingCountResponse,
    status_code=status.HTTP_200_OK,
)
async def doctor_pending_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> DoctorPendingCountResponse:
    count = await get_doctor_pending_count(db, current_user)
    return DoctorPendingCountResponse(count=count)


@router.get(
    "/doctor/pending",
    response_model=list[DoctorAppointmentItem],
    status_code=status.HTTP_200_OK,
)
async def doctor_pending_appointments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> list[DoctorAppointmentItem]:
    return await get_doctor_pending_appointments(db, current_user)


@router.get(
    "/doctor/today",
    response_model=list[DoctorAppointmentItem],
    status_code=status.HTTP_200_OK,
)
async def doctor_today_appointments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> list[DoctorAppointmentItem]:
    return await get_doctor_today_appointments(db, current_user)


@router.get(
    "/stats",
    response_model=AppointmentStatsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_stats(
    target_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> AppointmentStatsResponse:
    org_id = _get_org_id(current_user)
    return await get_appointment_stats(db, org_id, target_date or date.today())


@router.get(
    "",
    response_model=AppointmentListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_appointments_endpoint(
    doctor_id: UUID | None = None,
    patient_id: UUID | None = None,
    appointment_date: date | None = None,
    appt_status: SchemaStatus | None = None,
    page: int = 1,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> AppointmentListResponse:
    org_id = _get_org_id(current_user)
    appointments, total = await list_appointments(
        db, org_id, doctor_id, patient_id,
        appointment_date, appt_status, page, limit,
    )

    items: list[AppointmentListItem] = []
    for row in appointments:
        appt = row.appointment

        # For guest bookings ("someone_else"), prefer guest fields over the
        # registered patient's details so the table shows who is actually seen.
        if appt.booking_for == "someone_else" and appt.guest_name:
            display_patient_name = appt.guest_name
            display_patient_phone = appt.guest_phone
        else:
            display_patient_name = row.patient_name
            display_patient_phone = row.patient_phone

        items.append(AppointmentListItem(
            id=appt.id,
            doctor_id=appt.doctor_id,
            patient_id=appt.patient_id,
            appointment_date=appt.appointment_date,
            start_time=appt.start_time,
            end_time=appt.end_time,
            appointment_type=appt.appointment_type,
            status=appt.status,
            token_number=appt.token_number,
            booking_for=appt.booking_for,
            guest_name=appt.guest_name,
            patient_name=display_patient_name,
            patient_phone=display_patient_phone,
            patient_code=row.patient_code,
            doctor_name=row.doctor_name,
            doctor_specialization=row.doctor_specialization,
            created_at=appt.created_at,
        ))

    return AppointmentListResponse(
        appointments=items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/{appointment_id}",
    response_model=AppointmentRead,
    status_code=status.HTTP_200_OK,
)
async def get_appointment_endpoint(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> AppointmentRead:
    org_id = _get_org_id(current_user)
    return await get_appointment(db, appointment_id, org_id)


@router.post(
    "/walk-in",
    response_model=WalkInAppointmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_walkin_appointment_endpoint(
    data: WalkInAppointmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> WalkInAppointmentResponse:
    org_id = _get_org_id(current_user)
    return await create_walkin_appointment(db, org_id, data)


@router.post(
    "",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_appointment_endpoint(
    data: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> AppointmentRead:
    org_id = _get_org_id(current_user)
    return await create_appointment(db, org_id, data)


@router.patch(
    "/{appointment_id}/status",
    response_model=AppointmentRead,
    status_code=status.HTTP_200_OK,
)
async def update_status_endpoint(
    appointment_id: UUID,
    data: AppointmentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> AppointmentRead:
    org_id = _get_org_id(current_user)
    return await update_appointment_status(db, appointment_id, org_id, data)


@router.patch(
    "/{appointment_id}/cancel",
    response_model=AppointmentRead,
    status_code=status.HTTP_200_OK,
)
async def cancel_appointment_endpoint(
    appointment_id: UUID,
    payload: AppointmentCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> AppointmentRead:
    org_id = _get_org_id(current_user)
    return await cancel_appointment_by_request(db, appointment_id, org_id, payload)


@router.patch(
    "/{appointment_id}/confirm",
    response_model=AppointmentRead,
    status_code=status.HTTP_200_OK,
)
async def confirm_appointment_endpoint(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> AppointmentRead:
    return await confirm_appointment(db, appointment_id, current_user)


@router.patch(
    "/{appointment_id}/reject",
    response_model=AppointmentRead,
    status_code=status.HTTP_200_OK,
)
async def reject_appointment_endpoint(
    appointment_id: UUID,
    payload: AppointmentRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> AppointmentRead:
    return await reject_appointment(db, appointment_id, current_user, payload)


@router.patch(
    "/{appointment_id}/start",
    response_model=AppointmentRead,
    status_code=status.HTTP_200_OK,
)
async def start_appointment_endpoint(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> AppointmentRead:
    return await start_appointment(db, appointment_id, current_user)


@router.patch(
    "/{appointment_id}/complete",
    response_model=AppointmentRead,
    status_code=status.HTTP_200_OK,
)
async def complete_appointment_endpoint(
    appointment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> AppointmentRead:
    return await complete_appointment(db, appointment_id, current_user)


@router.delete(
    "/{appointment_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def cancel_appointment_endpoint(
    appointment_id: UUID,
    reason: str = "Cancelled by admin",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.org_admin)),
) -> dict:
    org_id = _get_org_id(current_user)
    await cancel_appointment(db, appointment_id, org_id, reason)
    return {"message": "Appointment cancelled successfully"}
