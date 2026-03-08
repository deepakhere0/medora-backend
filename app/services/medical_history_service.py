from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.medical_history import MedicalHistory
from app.models.patient import Patient
from app.schemas.medical_history import (
    MedicalHistoryCreate,
    MedicalHistoryListResponse,
    MedicalHistoryRead,
    MedicalHistoryUpdate,
)


async def create_medical_history(
    db: AsyncSession,
    org_id: UUID,
    recorded_by: UUID,
    data: MedicalHistoryCreate,
) -> MedicalHistoryRead:
    # Validation 1 — Patient exists in this org
    patient_result = await db.execute(
        select(Patient).where(
            Patient.organization_id == org_id,
            Patient.id == data.patient_id,
            Patient.is_active == True,
        )
    )
    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    # Validation 2 — Appointment (if provided)
    if data.appointment_id is not None:
        appt_result = await db.execute(
            select(Appointment).where(
                Appointment.organization_id == org_id,
                Appointment.id == data.appointment_id,
                Appointment.is_active == True,
            )
        )
        appointment = appt_result.scalar_one_or_none()
        if appointment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )
        if appointment.patient_id != data.patient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Appointment does not belong to this patient",
            )

    # Create and save record
    history = MedicalHistory(
        organization_id=org_id,
        patient_id=data.patient_id,
        appointment_id=data.appointment_id,
        recorded_by=recorded_by,
        event_date=data.event_date,
        event_name=data.event_name,
        description=data.description,
    )
    db.add(history)
    await db.commit()
    await db.refresh(history)
    return MedicalHistoryRead.model_validate(history)


async def get_patient_history(
    db: AsyncSession,
    org_id: UUID,
    patient_id: UUID,
) -> MedicalHistoryListResponse:
    # Validate patient exists in this org
    patient_result = await db.execute(
        select(Patient).where(
            Patient.organization_id == org_id,
            Patient.id == patient_id,
            Patient.is_active == True,
        )
    )
    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    # Fetch all active history records ordered by event_date DESC
    records_result = await db.execute(
        select(MedicalHistory).where(
            MedicalHistory.organization_id == org_id,
            MedicalHistory.patient_id == patient_id,
            MedicalHistory.is_active == True,
        ).order_by(MedicalHistory.event_date.desc())
    )
    records = records_result.scalars().all()

    return MedicalHistoryListResponse(
        histories=[MedicalHistoryRead.model_validate(h) for h in records],
        total=len(records),
    )


async def update_medical_history(
    db: AsyncSession,
    org_id: UUID,
    history_id: UUID,
    data: MedicalHistoryUpdate,
) -> MedicalHistoryRead:
    # Fetch record scoped to org
    result = await db.execute(
        select(MedicalHistory).where(
            MedicalHistory.organization_id == org_id,
            MedicalHistory.id == history_id,
            MedicalHistory.is_active == True,
        )
    )
    history = result.scalar_one_or_none()
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical history record not found",
        )

    # Apply only the fields the caller explicitly provided
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(history, field, value)

    await db.commit()
    await db.refresh(history)
    return MedicalHistoryRead.model_validate(history)


async def delete_medical_history(
    db: AsyncSession,
    org_id: UUID,
    history_id: UUID,
) -> None:
    # Fetch record scoped to org
    result = await db.execute(
        select(MedicalHistory).where(
            MedicalHistory.organization_id == org_id,
            MedicalHistory.id == history_id,
            MedicalHistory.is_active == True,
        )
    )
    history = result.scalar_one_or_none()
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical history record not found",
        )

    # Soft delete — preserve audit trail
    history.is_active = False
    await db.commit()
