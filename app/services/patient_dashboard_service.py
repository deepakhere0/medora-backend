from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.patient_organization import PatientOrganization
from app.models.report import Report


def _build_appointment_brief(appt: Appointment, doctor: Doctor, org: Organization) -> dict:
    return {
        "id": appt.id,
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

    # 3. Upcoming appointments (next 5)
    today = date.today()
    appt_result = await db.execute(
        select(Appointment, Doctor, Organization)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(Organization, Organization.id == Appointment.organization_id)
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.appointment_date >= today)
        .where(Appointment.status.in_(["scheduled", "confirmed"]))
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


async def get_patient_appointments(
    db: AsyncSession,
    patient_id: UUID,
    status: str | None = None,
    upcoming_only: bool = False,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list, int]:
    today = date.today()

    # Build count query
    count_query = (
        select(func.count(Appointment.id))
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.is_active == True)
    )
    if status:
        count_query = count_query.where(Appointment.status == status)
    if upcoming_only:
        count_query = count_query.where(Appointment.appointment_date >= today)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Build list query
    list_query = (
        select(Appointment, Doctor, Organization)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(Organization, Organization.id == Appointment.organization_id)
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.is_active == True)
    )
    if status:
        list_query = list_query.where(Appointment.status == status)
    if upcoming_only:
        list_query = list_query.where(Appointment.appointment_date >= today)

    list_query = (
        list_query
        .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(list_query)
    appointments = [
        _build_appointment_brief(appt, doctor, org)
        for appt, doctor, org in result.all()
    ]

    return appointments, total


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
