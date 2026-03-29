from datetime import date, datetime, time
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.patient_organization import PatientOrganization
from app.models.report import Report


def _build_appointment_brief(appt: Appointment, doctor: Doctor, org: Organization) -> dict:
    return {
        "id": appt.id,
        "doctor_id": appt.doctor_id,
        "doctor_name": doctor.name,
        "doctor_specialty": doctor.specialization,
        "doctor_photo_url": doctor.photo_url,
        "organization_name": org.name,
        "hospital_address": org.address,
        "hospital_city": org.city,
        "hospital_state": org.state,
        "appointment_date": appt.appointment_date,
        "start_time": appt.start_time,
        "end_time": appt.end_time,
        "status": appt.status,
        "consultation_type": None,  # not a model field, default to None
        "notes": appt.notes,
    }


async def _fetch_linked_orgs(db: AsyncSession, patient_id: UUID) -> list:
    result = await db.execute(
        select(Organization)
        .join(PatientOrganization, PatientOrganization.organization_id == Organization.id)
        .where(PatientOrganization.patient_id == patient_id)
        .where(PatientOrganization.is_active == True)
    )
    return result.scalars().all()


async def get_patient_dashboard(db: AsyncSession, patient_id: UUID) -> dict:
    # 1. Fetch patient record
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    # 2. Linked organizations
    orgs = await _fetch_linked_orgs(db, patient_id)

    # 3. Upcoming appointments (next 5) — auto-complete stale ones first
    today = date.today()
    await _auto_complete_past_appointments(db, patient_id)
    appt_result = await db.execute(
        select(Appointment, Doctor, Organization)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(Organization, Organization.id == Appointment.organization_id)
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.appointment_date >= today)
        .where(Appointment.status.not_in(["cancelled", "completed"]))
        .where(Appointment.is_active == True)
        .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
        .limit(5)
    )
    upcoming_appointments = [
        _build_appointment_brief(appt, doctor, org)
        for appt, doctor, org in appt_result.all()
    ]

    # 4. Total appointments (all time)
    total_appt_result = await db.execute(
        select(func.count(Appointment.id))
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.is_active == True)
    )
    total_appointments = total_appt_result.scalar() or 0

    # 5. Total reports
    total_reports_result = await db.execute(
        select(func.count(Report.id))
        .where(Report.patient_id == patient_id)
        .where(Report.is_active == True)
    )
    total_reports = total_reports_result.scalar() or 0

    return {
        "profile": {
            "id": patient.id,
            "name": patient.name,
            "email": patient.email,
            "phone": patient.phone,
            "patient_code": patient.patient_code,
            "date_of_birth": patient.date_of_birth,
            "gender": patient.gender,
            "blood_type": patient.blood_type,
            "height_cm": patient.height_cm,
            "weight_kg": patient.weight_kg,
            "blood_pressure": patient.blood_pressure,
            "heart_rate": patient.heart_rate,
            "photo_url": patient.photo_url,
            "organizations": [{"id": o.id, "name": o.name} for o in orgs],
        },
        "upcoming_appointments": upcoming_appointments,
        "total_appointments": total_appointments,
        "total_reports": total_reports,
    }


async def get_patient_profile(db: AsyncSession, patient_id: UUID) -> dict:
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    orgs = await _fetch_linked_orgs(db, patient_id)

    return {
        "id": patient.id,
        "name": patient.name,
        "email": patient.email,
        "phone": patient.phone,
        "patient_code": patient.patient_code,
        "date_of_birth": patient.date_of_birth,
        "gender": patient.gender,
        "blood_type": patient.blood_type,
        "height_cm": patient.height_cm,
        "weight_kg": patient.weight_kg,
        "blood_pressure": patient.blood_pressure,
        "heart_rate": patient.heart_rate,
        "photo_url": patient.photo_url,
        "organizations": [{"id": o.id, "name": o.name} for o in orgs],
    }


async def update_patient_profile(db: AsyncSession, patient_id: UUID, updates: dict) -> dict:
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    for field, value in updates.items():
        if value is not None:
            setattr(patient, field, value)

    await db.commit()
    await db.refresh(patient)

    orgs = await _fetch_linked_orgs(db, patient_id)

    return {
        "id": patient.id,
        "name": patient.name,
        "email": patient.email,
        "phone": patient.phone,
        "patient_code": patient.patient_code,
        "date_of_birth": patient.date_of_birth,
        "gender": patient.gender,
        "blood_type": patient.blood_type,
        "height_cm": patient.height_cm,
        "weight_kg": patient.weight_kg,
        "blood_pressure": patient.blood_pressure,
        "heart_rate": patient.heart_rate,
        "photo_url": patient.photo_url,
        "organizations": [{"id": o.id, "name": o.name} for o in orgs],
    }


async def _auto_complete_past_appointments(db: AsyncSession, patient_id: UUID) -> None:
    """Mark scheduled/confirmed appointments whose end_time has passed as completed."""
    now = datetime.now()
    stale_result = await db.execute(
        select(Appointment)
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.is_active == True)
        .where(Appointment.status.in_(["scheduled", "confirmed"]))
        .where(Appointment.appointment_date <= now.date())
    )
    stale = stale_result.scalars().all()
    changed = False
    for appt in stale:
        appt_end_dt = datetime.combine(appt.appointment_date, appt.end_time)
        if appt_end_dt < now:
            appt.status = "completed"
            changed = True
    if changed:
        await db.commit()


async def get_patient_appointments(
    db: AsyncSession,
    patient_id: UUID,
    filter: str = "upcoming",
    skip: int = 0,
    limit: int = 20,
) -> tuple[list, int]:
    today = date.today()

    await _auto_complete_past_appointments(db, patient_id)

    base = (
        select(Appointment, Doctor, Organization)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(Organization, Organization.id == Appointment.organization_id)
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.is_active == True)
    )

    if filter == "upcoming":
        base = base.where(Appointment.appointment_date >= today).where(
            Appointment.status.not_in(["cancelled", "completed"])
        )
        order = (Appointment.appointment_date.asc(), Appointment.start_time.asc())
    elif filter == "past":
        base = base.where(
            (Appointment.appointment_date < today) | (Appointment.status == "completed")
        )
        order = (Appointment.appointment_date.desc(), Appointment.start_time.desc())
    elif filter == "cancelled":
        base = base.where(Appointment.status == "cancelled")
        order = (Appointment.appointment_date.desc(), Appointment.start_time.desc())
    else:  # "all"
        order = (Appointment.appointment_date.desc(), Appointment.start_time.desc())

    count_query = (
        select(func.count())
        .select_from(base.subquery())
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    list_query = base.order_by(*order).offset(skip).limit(limit)
    result = await db.execute(list_query)
    appointments = [
        _build_appointment_brief(appt, doctor, org)
        for appt, doctor, org in result.all()
    ]

    return appointments, total


async def reschedule_patient_appointment(
    db: AsyncSession,
    patient_id: UUID,
    appointment_id: UUID,
    new_date: str,
    new_start_time: str,
    new_end_time: str,
) -> dict:
    # 1. Fetch appointment and verify ownership
    result = await db.execute(
        select(Appointment, Doctor, Organization)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(Organization, Organization.id == Appointment.organization_id)
        .where(Appointment.id == appointment_id)
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.is_active == True)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    appointment, doctor, org = row

    # 2. Verify the appointment can be rescheduled
    if appointment.status not in ("scheduled", "confirmed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reschedule an appointment with status '{appointment.status}'",
        )

    # 3. Parse new date and times
    try:
        parsed_date = date.fromisoformat(new_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )
    try:
        h, m = new_start_time.strip().split(":")
        parsed_start = time(int(h), int(m))
        h, m = new_end_time.strip().split(":")
        parsed_end = time(int(h), int(m))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid time format. Use HH:MM",
        )

    # 4. Verify doctor has a schedule on the new weekday
    day_of_week = parsed_date.weekday()
    sched_result = await db.execute(
        select(DoctorSchedule)
        .where(DoctorSchedule.doctor_id == appointment.doctor_id)
        .where(DoctorSchedule.day_of_week == day_of_week)
        .where(DoctorSchedule.is_active == True)
    )
    schedule = sched_result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor is not available on this day",
        )

    # 5. Verify slot falls within working hours and not in break
    if parsed_start < schedule.start_time or parsed_end > schedule.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slot is outside the doctor's working hours",
        )
    if schedule.break_start and schedule.break_end:
        if schedule.break_start <= parsed_start < schedule.break_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slot falls within the doctor's break time",
            )

    # 6. Check for conflict (exclude the current appointment)
    conflict_result = await db.execute(
        select(Appointment)
        .where(Appointment.doctor_id == appointment.doctor_id)
        .where(Appointment.appointment_date == parsed_date)
        .where(Appointment.start_time == parsed_start)
        .where(Appointment.id != appointment_id)
        .where(Appointment.status.not_in(["cancelled"]))
        .where(Appointment.is_active == True)
    )
    if conflict_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This slot is already booked. Please choose another time.",
        )

    # 7. Apply the update
    appointment.appointment_date = parsed_date
    appointment.start_time = parsed_start
    appointment.end_time = parsed_end

    await db.commit()
    await db.refresh(appointment)

    return {
        "id": appointment.id,
        "booking_id": appointment.booking_id,
        "doctor_name": doctor.name,
        "doctor_specialty": doctor.specialization,
        "organization_name": org.name,
        "hospital_city": org.city,
        "hospital_state": org.state,
        "appointment_date": appointment.appointment_date,
        "start_time": appointment.start_time,
        "end_time": appointment.end_time,
        "status": appointment.status,
        "notes": appointment.notes,
    }


async def cancel_patient_appointment(
    db: AsyncSession,
    patient_id: UUID,
    appointment_id: UUID,
) -> Appointment:
    result = await db.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.is_active == True)
    )
    appointment = result.scalar_one_or_none()

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.status not in ("scheduled", "confirmed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel an appointment with status '{appointment.status}'",
        )

    appointment.status = "cancelled"
    await db.commit()
    await db.refresh(appointment)
    return appointment
