import random
import string
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.patient_organization import PatientOrganization
from app.schemas.booking import (
    AvailableSlot,
    BookAppointmentRequest,
    BookAppointmentResponse,
    CityResponse,
    DaySlotsResponse,
    DoctorBrief,
    HospitalBrief,
    SpecializationResponse,
    StateResponse,
    WeekSlotsResponse,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _count_slots(schedule: DoctorSchedule) -> int:
    """Approximate how many appointment slots a schedule produces (for UI badge)."""
    start_m = _time_to_minutes(schedule.start_time)
    end_m = _time_to_minutes(schedule.end_time)
    total_slots = (end_m - start_m) // schedule.slot_duration_minutes

    if schedule.break_start and schedule.break_end:
        break_start_m = _time_to_minutes(schedule.break_start)
        break_end_m = _time_to_minutes(schedule.break_end)
        total_slots -= (break_end_m - break_start_m) // schedule.slot_duration_minutes

    return max(0, total_slots)


def _generate_slots_for_day(
    schedule: DoctorSchedule,
    target_date: date,
    booked_start_times: set[time],
    now: datetime,
) -> list[AvailableSlot]:
    """Generate all appointment slots for a single day according to a schedule."""
    slots: list[AvailableSlot] = []
    duration = timedelta(minutes=schedule.slot_duration_minutes)

    current_dt = datetime.combine(target_date, schedule.start_time)
    end_dt = datetime.combine(target_date, schedule.end_time)

    while current_dt + duration <= end_dt:
        slot_start = current_dt.time()
        slot_end = (current_dt + duration).time()

        # Skip slots that fall inside the break window
        if schedule.break_start and schedule.break_end:
            if schedule.break_start <= slot_start < schedule.break_end:
                current_dt += duration
                continue

        # A slot is unavailable if it is in the past or already booked
        is_past = target_date < now.date() or (
            target_date == now.date() and slot_start <= now.time()
        )
        is_available = not is_past and slot_start not in booked_start_times

        slots.append(
            AvailableSlot(
                start_time=slot_start.strftime("%H:%M"),
                end_time=slot_end.strftime("%H:%M"),
                is_available=is_available,
            )
        )
        current_dt += duration

    return slots


def _split_into_periods(slots: list[AvailableSlot]) -> tuple[list, list, list]:
    """Split a flat slot list into morning / afternoon / evening buckets."""
    morning, afternoon, evening = [], [], []
    for slot in slots:
        hour = int(slot.start_time.split(":")[0])
        if hour < 12:
            morning.append(slot)
        elif hour < 17:
            afternoon.append(slot)
        else:
            evening.append(slot)
    return morning, afternoon, evening


async def _generate_booking_id(db: AsyncSession) -> str:
    """Generate a unique MED-XXXX-XXXX booking reference."""
    chars = string.ascii_uppercase + string.digits
    for _ in range(10):
        part1 = "".join(random.choices(chars, k=4))
        part2 = "".join(random.choices(chars, k=4))
        candidate = f"MED-{part1}-{part2}"
        result = await db.execute(
            select(Appointment).where(Appointment.booking_id == candidate)
        )
        if result.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate a unique booking ID. Please try again.",
    )


# ---------------------------------------------------------------------------
# Step 1-2: Location
# ---------------------------------------------------------------------------

async def get_states(db: AsyncSession) -> list[StateResponse]:
    result = await db.execute(
        select(Organization.state, func.count(Organization.id).label("hospital_count"))
        .where(Organization.is_approved == True)
        .group_by(Organization.state)
        .order_by(Organization.state.asc())
    )
    return [
        StateResponse(state=row.state, hospital_count=row.hospital_count)
        for row in result.all()
    ]


async def get_cities(db: AsyncSession, state: str) -> list[CityResponse]:
    result = await db.execute(
        select(Organization.city, func.count(Organization.id).label("hospital_count"))
        .where(Organization.is_approved == True)
        .where(Organization.state == state)
        .group_by(Organization.city)
        .order_by(Organization.city.asc())
    )
    return [
        CityResponse(city=row.city, hospital_count=row.hospital_count)
        for row in result.all()
    ]


# ---------------------------------------------------------------------------
# Step 3: Hospital listing
# ---------------------------------------------------------------------------

async def get_hospitals(db: AsyncSession, state: str, city: str) -> list[HospitalBrief]:
    today = date.today()
    today_dow = today.weekday()  # 0=Monday … 6=Sunday

    orgs_result = await db.execute(
        select(Organization)
        .where(Organization.is_approved == True)
        .where(Organization.state == state)
        .where(Organization.city == city)
        .order_by(Organization.name.asc())
    )
    orgs = orgs_result.scalars().all()

    hospitals: list[HospitalBrief] = []
    for org in orgs:
        # Active doctor count
        doc_result = await db.execute(
            select(func.count(Doctor.id))
            .where(Doctor.organization_id == org.id)
            .where(Doctor.is_active == True)
        )
        doctor_count: int = doc_result.scalar() or 0

        # Available slots today (approximate)
        sched_result = await db.execute(
            select(DoctorSchedule)
            .where(DoctorSchedule.organization_id == org.id)
            .where(DoctorSchedule.day_of_week == today_dow)
            .where(DoctorSchedule.is_active == True)
        )
        schedules = sched_result.scalars().all()
        total_slots = sum(_count_slots(s) for s in schedules)

        booked_result = await db.execute(
            select(func.count(Appointment.id))
            .where(Appointment.organization_id == org.id)
            .where(Appointment.appointment_date == today)
            .where(Appointment.status.in_(["scheduled", "confirmed", "in_progress"]))
            .where(Appointment.is_active == True)
        )
        booked: int = booked_result.scalar() or 0

        hospitals.append(
            HospitalBrief(
                id=org.id,
                name=org.name,
                city=org.city,
                state=org.state,
                address=org.address,
                logo_url=org.logo_url,
                doctor_count=doctor_count,
                available_slots_today=max(0, total_slots - booked),
            )
        )

    return hospitals


# ---------------------------------------------------------------------------
# Step 4: Doctor listing
# ---------------------------------------------------------------------------

async def get_doctors(
    db: AsyncSession,
    org_id: UUID,
    specialization: str | None = None,
    search: str | None = None,
) -> list[DoctorBrief]:
    query = (
        select(Doctor)
        .where(Doctor.organization_id == org_id)
        .where(Doctor.is_active == True)
        .where(Doctor.status == "active")
    )
    if specialization:
        query = query.where(Doctor.specialization == specialization)
    if search:
        query = query.where(Doctor.name.ilike(f"%{search}%"))
    query = query.order_by(Doctor.name.asc())

    result = await db.execute(query)
    doctors = result.scalars().all()

    return [
        DoctorBrief(
            id=d.id,
            name=d.name,
            specialization=d.specialization,
            experience_years=d.experience_years,
            photo_url=d.photo_url,
            gender=d.gender,
            status=d.status,
        )
        for d in doctors
    ]


async def get_specializations(
    db: AsyncSession, org_id: UUID
) -> list[SpecializationResponse]:
    result = await db.execute(
        select(
            Doctor.specialization,
            func.count(Doctor.id).label("doctor_count"),
        )
        .where(Doctor.organization_id == org_id)
        .where(Doctor.is_active == True)
        .group_by(Doctor.specialization)
        .order_by(Doctor.specialization.asc())
    )
    return [
        SpecializationResponse(
            specialization=row.specialization, doctor_count=row.doctor_count
        )
        for row in result.all()
    ]


# ---------------------------------------------------------------------------
# Step 5: Slot availability
# ---------------------------------------------------------------------------

async def get_available_slots(
    db: AsyncSession,
    doctor_id: UUID,
    week_start: date | None = None,
) -> WeekSlotsResponse:
    # 1. Fetch doctor
    doctor_result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = doctor_result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found"
        )

    # 2. Resolve week window
    if week_start is None:
        week_start = date.today()

    # 3. Load all active schedules for this doctor
    sched_result = await db.execute(
        select(DoctorSchedule)
        .where(DoctorSchedule.doctor_id == doctor_id)
        .where(DoctorSchedule.is_active == True)
    )
    schedules = sched_result.scalars().all()

    if not schedules:
        return WeekSlotsResponse(
            doctor_id=doctor_id,
            doctor_name=doctor.name,
            schedule_exists=False,
            week_start=week_start,
            days=[],
        )

    # Build a lookup: day_of_week → schedule
    schedule_by_dow: dict[int, DoctorSchedule] = {s.day_of_week: s for s in schedules}

    now = datetime.now()
    days: list[DaySlotsResponse] = []

    for offset in range(7):
        target_date = week_start + timedelta(days=offset)
        dow = target_date.weekday()
        schedule = schedule_by_dow.get(dow)
        if schedule is None:
            continue  # Doctor doesn't work on this weekday

        # Fetch already-booked start times for this doctor on this date
        appt_result = await db.execute(
            select(Appointment.start_time)
            .where(Appointment.doctor_id == doctor_id)
            .where(Appointment.appointment_date == target_date)
            .where(Appointment.status.in_(["scheduled", "confirmed", "in_progress"]))
            .where(Appointment.is_active == True)
        )
        booked_start_times: set[time] = {row[0] for row in appt_result.all()}

        all_slots = _generate_slots_for_day(schedule, target_date, booked_start_times, now)
        morning, afternoon, evening = _split_into_periods(all_slots)

        days.append(
            DaySlotsResponse(
                date=target_date,
                day_name=target_date.strftime("%A"),
                morning=morning,
                afternoon=afternoon,
                evening=evening,
            )
        )

    return WeekSlotsResponse(
        doctor_id=doctor_id,
        doctor_name=doctor.name,
        schedule_exists=True,
        week_start=week_start,
        days=days,
    )


# ---------------------------------------------------------------------------
# Step 6: Book appointment
# ---------------------------------------------------------------------------

async def book_appointment(
    db: AsyncSession,
    patient_id: UUID,
    data: BookAppointmentRequest,
) -> BookAppointmentResponse:
    # 1. Resolve organization_id from doctor record if not provided
    org_id = data.organization_id
    if org_id is None:
        doc_lookup = await db.execute(
            select(Doctor).where(Doctor.id == data.doctor_id)
        )
        d = doc_lookup.scalar_one_or_none()
        if d is not None and d.organization_id is not None:
            org_id = d.organization_id

    # 2. Validate organization (only if we have one)
    org: Organization | None = None
    if org_id is not None:
        org_result = await db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = org_result.scalar_one_or_none()
        if org is None or not org.is_approved:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found or not approved",
            )

    # 3. Validate doctor
    doc_query = (
        select(Doctor)
        .where(Doctor.id == data.doctor_id)
        .where(Doctor.is_active == True)
    )
    if org_id is not None:
        doc_query = doc_query.where(Doctor.organization_id == org_id)
    doc_result = await db.execute(doc_query)
    doctor = doc_result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found or not available",
        )

    # 3. Parse start_time string → time object
    try:
        h, m = data.start_time.strip().split(":")
        slot_start = time(int(h), int(m))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid time format. Use HH:MM (e.g. '10:30')",
        )

    # 4. Get doctor's schedule for the requested weekday
    day_of_week = data.appointment_date.weekday()
    sched_result = await db.execute(
        select(DoctorSchedule)
        .where(DoctorSchedule.doctor_id == data.doctor_id)
        .where(DoctorSchedule.day_of_week == day_of_week)
        .where(DoctorSchedule.is_active == True)
    )
    schedule = sched_result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor is not available on this day",
        )

    # 5. Calculate end_time
    slot_end_dt = datetime.combine(data.appointment_date, slot_start) + timedelta(
        minutes=schedule.slot_duration_minutes
    )
    slot_end = slot_end_dt.time()

    # 6. Verify slot falls within working hours
    if slot_start < schedule.start_time or slot_end > schedule.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slot is outside the doctor's working hours",
        )

    # Verify slot does not fall in the break window
    if schedule.break_start and schedule.break_end:
        if schedule.break_start <= slot_start < schedule.break_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slot falls within the doctor's break time",
            )

    # 7. Check for booking conflict
    conflict_result = await db.execute(
        select(Appointment)
        .where(Appointment.doctor_id == data.doctor_id)
        .where(Appointment.appointment_date == data.appointment_date)
        .where(Appointment.start_time == slot_start)
        .where(Appointment.status.not_in(["cancelled", "rejected"]))
        .where(Appointment.is_active == True)
    )
    if conflict_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This slot is already booked. Please choose another time.",
        )

    # 8. Generate unique booking_id
    booking_id = await _generate_booking_id(db)

    # 9. Create appointment record
    appointment = Appointment(
        patient_id=patient_id,
        doctor_id=data.doctor_id,
        organization_id=org_id,
        appointment_date=data.appointment_date,
        start_time=slot_start,
        end_time=slot_end,
        status="pending",
        appointment_type="scheduled",
        booking_id=booking_id,
        notes=data.notes,
        booking_for=data.booking_for,
        guest_name=data.guest_name if data.booking_for == "someone_else" else None,
        guest_age=data.guest_age if data.booking_for == "someone_else" else None,
        guest_sex=data.guest_sex if data.booking_for == "someone_else" else None,
        guest_phone=data.guest_phone if data.booking_for == "someone_else" else None,
        guest_email=data.guest_email if data.booking_for == "someone_else" else None,
    )
    db.add(appointment)

    # 10. Link patient ↔ organization (only when org exists)
    if org_id is not None:
        link_result = await db.execute(
            select(PatientOrganization)
            .where(PatientOrganization.patient_id == patient_id)
            .where(PatientOrganization.organization_id == org_id)
        )
        existing_link = link_result.scalar_one_or_none()
        if existing_link is None:
            db.add(
                PatientOrganization(
                    patient_id=patient_id,
                    organization_id=org_id,
                    is_active=True,
                )
            )
        elif not existing_link.is_active:
            existing_link.is_active = True

    # Clear booking draft on successful booking
    patient_result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = patient_result.scalar_one_or_none()
    if patient is not None and patient.booking_draft is not None:
        patient.booking_draft = None

    # Create notification for the organization dashboard (skip for independent doctors)
    if org_id is not None:
        patient_display = data.guest_name if data.booking_for == "someone_else" and data.guest_name else (
            patient.name if patient else "Unknown"
        )
        db.add(Notification(
            organization_id=org_id,
            title="New Appointment Booked",
            message=(
                f"Patient {patient_display} booked with Dr. {doctor.name} "
                f"on {data.appointment_date.strftime('%b %d, %Y')} at {slot_start.strftime('%H:%M')}"
            ),
            type="info",
        ))

    await db.commit()
    await db.refresh(appointment)

    # 11. Return booking confirmation
    return BookAppointmentResponse(
        id=appointment.id,
        booking_id=appointment.booking_id,
        organization_name=org.name if org else None,
        hospital_address=org.address if org else None,
        hospital_city=org.city if org else None,
        hospital_state=org.state if org else None,
        doctor_name=doctor.name,
        doctor_specialization=doctor.specialization,
        appointment_date=appointment.appointment_date,
        start_time=appointment.start_time.strftime("%H:%M"),
        end_time=appointment.end_time.strftime("%H:%M"),
        status=appointment.status,
        created_at=appointment.created_at,
        booking_for=appointment.booking_for,
        guest_name=appointment.guest_name,
        guest_age=appointment.guest_age,
        guest_sex=appointment.guest_sex,
        guest_phone=appointment.guest_phone,
        guest_email=appointment.guest_email,
    )
