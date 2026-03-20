import random
import string
from datetime import date, time
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentStatus as SchemaStatus,
    AppointmentStatusUpdate,
    AppointmentStatsResponse,
    AppointmentUpdate,
    WalkInAppointmentRequest,
    WalkInAppointmentResponse,
)


async def _check_doctor_conflict(
    db: AsyncSession,
    org_id: UUID,
    doctor_id: UUID,
    appointment_date: date,
    start_time: time,
    end_time: time,
    exclude_id: UUID | None = None,
) -> None:
    filters = [
        Appointment.organization_id == org_id,
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appointment_date,
        Appointment.status != AppointmentStatus.cancelled,
        Appointment.is_active.is_(True),
        Appointment.start_time < end_time,
        Appointment.end_time > start_time,
    ]
    if exclude_id is not None:
        filters.append(Appointment.id != exclude_id)

    result = await db.execute(select(Appointment.id).where(and_(*filters)).limit(1))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor already has an appointment during this time slot",
        )


async def create_appointment(
    db: AsyncSession,
    org_id: UUID,
    data: AppointmentCreate,
) -> Appointment:
    # Verify doctor exists and belongs to org
    doctor_result = await db.execute(
        select(Doctor).where(
            and_(
                Doctor.id == data.doctor_id,
                Doctor.organization_id == org_id,
                Doctor.is_active.is_(True),
            )
        )
    )
    if doctor_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    # Verify patient exists and belongs to org
    patient_result = await db.execute(
        select(Patient).where(
            and_(
                Patient.id == data.patient_id,
                Patient.organization_id == org_id,
                Patient.is_active.is_(True),
            )
        )
    )
    if patient_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    # Check for double booking
    await _check_doctor_conflict(
        db=db,
        org_id=org_id,
        doctor_id=data.doctor_id,
        appointment_date=data.appointment_date,
        start_time=data.start_time,
        end_time=data.end_time,
    )

    # Calculate token number for walk-in appointments
    token_number: int | None = None
    if data.appointment_type.value == "walk_in":
        count_result = await db.execute(
            select(func.count(Appointment.id)).where(
                and_(
                    Appointment.organization_id == org_id,
                    Appointment.appointment_date == data.appointment_date,
                    Appointment.appointment_type == "walk_in",
                    Appointment.status != AppointmentStatus.cancelled,
                )
            )
        )
        token_number = (count_result.scalar_one() or 0) + 1

    appointment = Appointment(
        **data.model_dump(),
        organization_id=org_id,
        status=AppointmentStatus.scheduled,
        token_number=token_number,
    )
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    return appointment


async def get_appointment(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
) -> Appointment:
    result = await db.execute(
        select(Appointment).where(
            and_(
                Appointment.organization_id == org_id,
                Appointment.id == appointment_id,
                Appointment.is_active.is_(True),
            )
        )
    )
    appointment = result.scalar_one_or_none()
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    return appointment


async def list_appointments(
    db: AsyncSession,
    org_id: UUID,
    doctor_id: UUID | None,
    patient_id: UUID | None,
    appointment_date: date | None,
    appt_status: SchemaStatus | None,
    page: int,
    limit: int,
) -> tuple[list[Appointment], int]:
    filters = [
        Appointment.organization_id == org_id,
        Appointment.is_active.is_(True),
    ]
    if doctor_id is not None:
        filters.append(Appointment.doctor_id == doctor_id)
    if patient_id is not None:
        filters.append(Appointment.patient_id == patient_id)
    if appointment_date is not None:
        filters.append(Appointment.appointment_date == appointment_date)
    if appt_status is not None:
        filters.append(Appointment.status == appt_status.value)

    where_clause = and_(*filters)

    count_result = await db.execute(
        select(func.count(Appointment.id)).where(where_clause)
    )
    total: int = count_result.scalar_one()

    rows_result = await db.execute(
        select(Appointment)
        .where(where_clause)
        .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    appointments: list[Appointment] = list(rows_result.scalars().all())

    return appointments, total


async def update_appointment(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
    data: AppointmentUpdate,
) -> Appointment:
    appointment = await get_appointment(db, appointment_id, org_id)

    _locked = {
        AppointmentStatus.in_progress,
        AppointmentStatus.completed,
        AppointmentStatus.cancelled,
    }
    if appointment.status in _locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update appointment with status: {appointment.status}",
        )

    updates: dict = data.model_dump(exclude_unset=True)

    time_fields = {"appointment_date", "start_time", "end_time"}
    if time_fields & updates.keys():
        await _check_doctor_conflict(
            db=db,
            org_id=org_id,
            doctor_id=appointment.doctor_id,
            appointment_date=updates.get("appointment_date", appointment.appointment_date),
            start_time=updates.get("start_time", appointment.start_time),
            end_time=updates.get("end_time", appointment.end_time),
            exclude_id=appointment_id,
        )

    for field, value in updates.items():
        setattr(appointment, field, value)

    await db.commit()
    await db.refresh(appointment)
    return appointment


_TRANSITIONS: dict[str, list[str]] = {
    "scheduled":   ["confirmed", "cancelled"],
    "confirmed":   ["in_progress", "cancelled"],
    "in_progress": ["completed", "cancelled"],
    "completed":   [],
    "cancelled":   [],
}


async def update_appointment_status(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
    data: AppointmentStatusUpdate,
) -> Appointment:
    appointment = await get_appointment(db, appointment_id, org_id)
    current_status: str = appointment.status

    if data.status.value not in _TRANSITIONS[current_status]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {current_status} to {data.status.value}",
        )

    appointment.status = data.status.value
    if data.status.value == "cancelled":
        appointment.cancellation_reason = data.cancellation_reason

    await db.commit()
    await db.refresh(appointment)
    return appointment


async def cancel_appointment(
    db: AsyncSession,
    appointment_id: UUID,
    org_id: UUID,
    reason: str,
) -> None:
    appointment = await get_appointment(db, appointment_id, org_id)

    if appointment.status in ("completed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a {appointment.status} appointment",
        )

    appointment.status = "cancelled"
    appointment.cancellation_reason = reason
    appointment.is_active = False

    await db.commit()


def _generate_booking_id() -> str:
    """Return a booking ID in MED-XXXX-XXXX format (uppercase alphanum)."""
    chars = string.ascii_uppercase + string.digits
    part1 = "".join(random.choices(chars, k=4))
    part2 = "".join(random.choices(chars, k=4))
    return f"MED-{part1}-{part2}"


async def create_walkin_appointment(
    db: AsyncSession,
    org_id: UUID,
    data: WalkInAppointmentRequest,
) -> WalkInAppointmentResponse:
    # 1. Look up patient by phone within this org
    patient_row = await db.execute(
        select(Patient).where(
            Patient.organization_id == org_id,
            Patient.phone == data.patient_phone,
            Patient.is_active.is_(True),
        )
    )
    patient = patient_row.scalar_one_or_none()
    is_new_patient = patient is None

    if is_new_patient:
        if data.patient_date_of_birth is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="patient_date_of_birth is required when registering a new patient",
            )
        # Generate next patient_code for this org (counts all, including soft-deleted)
        code_count = await db.scalar(
            select(func.count()).select_from(Patient).where(Patient.organization_id == org_id)
        ) or 0
        patient_code = f"PID-{code_count + 1:04d}"

        patient = Patient(
            organization_id=org_id,
            patient_code=patient_code,
            name=data.patient_name,
            gender=data.patient_gender.value,
            phone=data.patient_phone,
            email=data.patient_email,
            date_of_birth=data.patient_date_of_birth,
            address=data.patient_address,
            blood_type=data.patient_blood_type.value if data.patient_blood_type else None,
        )
        db.add(patient)
        # UUID is Python-generated; patient.id is ready to use immediately

    # 2. Validate doctor exists and belongs to org
    doctor_row = await db.execute(
        select(Doctor).where(
            Doctor.id == data.doctor_id,
            Doctor.organization_id == org_id,
            Doctor.is_active.is_(True),
        )
    )
    doctor = doctor_row.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    # 3. Check for doctor time conflicts
    await _check_doctor_conflict(
        db=db,
        org_id=org_id,
        doctor_id=data.doctor_id,
        appointment_date=data.appointment_date,
        start_time=data.start_time,
        end_time=data.end_time,
    )

    # 4. Calculate walk-in token number for this date
    token_count = await db.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.organization_id == org_id,
            Appointment.appointment_date == data.appointment_date,
            Appointment.appointment_type == "walk_in",
            Appointment.status != AppointmentStatus.cancelled,
        )
    ) or 0
    token_number = token_count + 1

    # 5. Create appointment (same session — single commit covers both)
    appointment = Appointment(
        organization_id=org_id,
        doctor_id=data.doctor_id,
        patient_id=patient.id,
        appointment_date=data.appointment_date,
        start_time=data.start_time,
        end_time=data.end_time,
        appointment_type="walk_in",
        status=AppointmentStatus.scheduled,
        token_number=token_number,
        booking_id=_generate_booking_id(),
        notes=data.notes,
    )
    db.add(appointment)

    # Single commit: atomically persists patient (if new) + appointment
    await db.commit()
    await db.refresh(appointment)
    await db.refresh(patient)

    return WalkInAppointmentResponse(
        appointment_id=appointment.id,
        booking_id=appointment.booking_id,
        patient_id=patient.id,
        patient_code=patient.patient_code,
        patient_name=patient.name,
        doctor_name=doctor.name,
        appointment_date=appointment.appointment_date,
        start_time=appointment.start_time.strftime("%H:%M"),
        end_time=appointment.end_time.strftime("%H:%M"),
        status=appointment.status,
        message=(
            "Walk-in appointment created for new patient"
            if is_new_patient
            else "Walk-in appointment created for existing patient"
        ),
    )


async def get_appointment_stats(
    db: AsyncSession,
    org_id: UUID,
    target_date: date,
) -> AppointmentStatsResponse:
    base = and_(
        Appointment.organization_id == org_id,
        Appointment.appointment_date == target_date,
        Appointment.is_active.is_(True),
    )

    def _count(extra_filter=None):
        q = select(func.count(Appointment.id)).where(base)
        if extra_filter is not None:
            q = q.where(extra_filter)
        return q

    total_today      = await db.scalar(_count()) or 0
    scheduled_count  = await db.scalar(_count(Appointment.status == "scheduled")) or 0
    confirmed_count  = await db.scalar(_count(Appointment.status == "confirmed")) or 0
    in_progress_count = await db.scalar(_count(Appointment.status == "in_progress")) or 0
    completed_count  = await db.scalar(_count(Appointment.status == "completed")) or 0
    cancelled_count  = await db.scalar(_count(Appointment.status == "cancelled")) or 0

    return AppointmentStatsResponse(
        total_today=total_today,
        scheduled_count=scheduled_count,
        confirmed_count=confirmed_count,
        in_progress_count=in_progress_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count,
    )
