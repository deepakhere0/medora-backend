from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentListResponse,
    AppointmentRead,
    AppointmentListItem,
    AppointmentStatus as SchemaStatus,
    AppointmentStatusUpdate,
    AppointmentStatsResponse,
    AppointmentUpdate,
)
from app.services.appointment_service import (
    cancel_appointment,
    create_appointment,
    get_appointment,
    get_appointment_stats,
    list_appointments,
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
    return AppointmentListResponse(
        appointments=appointments,
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
