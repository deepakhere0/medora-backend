from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.patient import Patient
from app.schemas.patient_dashboard import (
    PatientAppointmentsResponse,
    PatientDashboardResponse,
    PatientProfile,
    PatientProfileUpdate,
    RescheduleRequest,
    RescheduleResponse,
)
from app.services.patient_dashboard_service import (
    cancel_patient_appointment,
    get_patient_appointments,
    get_patient_dashboard,
    get_patient_profile,
    reschedule_patient_appointment,
    update_patient_profile,
)

router = APIRouter(prefix="/patient", tags=["Patient Dashboard"])


@router.get("/dashboard", response_model=PatientDashboardResponse)
async def patient_dashboard(
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await get_patient_dashboard(db, current_patient.id)


@router.get("/profile", response_model=PatientProfile)
async def patient_profile(
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await get_patient_profile(db, current_patient.id)


@router.put("/profile", response_model=PatientProfile)
async def update_profile(
    body: PatientProfileUpdate,
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    return await update_patient_profile(db, current_patient.id, updates)


@router.get("/appointments", response_model=PatientAppointmentsResponse)
async def patient_appointments(
    filter: str = Query(default="upcoming", description="upcoming | past | cancelled | all"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    appointments, total = await get_patient_appointments(
        db,
        patient_id=current_patient.id,
        filter=filter,
        skip=skip,
        limit=limit,
    )
    return {"appointments": appointments, "total": total}


@router.put("/appointments/{appointment_id}/reschedule", response_model=RescheduleResponse)
async def reschedule_appointment(
    appointment_id: UUID,
    body: RescheduleRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    return await reschedule_patient_appointment(
        db,
        patient_id=current_patient.id,
        appointment_id=appointment_id,
        new_date=body.new_date,
        new_start_time=body.new_start_time,
        new_end_time=body.new_end_time,
    )


@router.patch("/appointments/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: UUID,
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    appointment = await cancel_patient_appointment(db, current_patient.id, appointment_id)
    return {"message": "Appointment cancelled", "id": appointment.id}
