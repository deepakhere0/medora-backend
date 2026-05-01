"""
doctor_dashboard_service.py

Business logic for the authenticated doctor dashboard.

All functions receive the authenticated User and resolve the linked Doctor
record via Doctor.user_id == user.id.  Every DB query is scoped to that
single doctor — a doctor can never see another doctor's data.

Earnings note:
  The Appointment table does not store a per-row consultation_fee.
  In-clinic earnings are therefore: doctor.consultation_fee × count(completed).
  Online-consultation earnings are read from the online_consultations table
  where the actual fee is stored per session.
"""

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

from fastapi import HTTPException, status
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.audit_log import AuditLog
from app.models.doctor_schedule import DoctorSchedule
from app.models.online_consultation import OnlineConsultation
from app.models.patient import Patient
from app.models.report import Report
from app.models.review import Review
from app.models.user import User
from app.schemas.doctor_dashboard import (
    ScheduleEntryInput,
)

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_doctor_for_user(db: AsyncSession, user: User) -> Doctor:
    """Resolve the Doctor record linked to the authenticated user. 404 on miss."""
    result = await db.execute(
        select(Doctor).where(Doctor.user_id == user.id)
    )
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found for this account",
        )
    return doctor


def _parse_time(t_str: str) -> time:
    h, m = t_str.split(":")
    return time(int(h), int(m))


def _count_open_slots(schedule: DoctorSchedule, target_date: date, booked: set[time]) -> int:
    """Count available (future, un-booked) slots for a single day."""
    now = datetime.now()
    duration = timedelta(minutes=schedule.slot_duration_minutes)
    cur = datetime.combine(target_date, schedule.start_time)
    end = datetime.combine(target_date, schedule.end_time)
    count = 0
    while cur + duration <= end:
        slot_start = cur.time()
        if schedule.break_start and schedule.break_end:
            if schedule.break_start <= slot_start < schedule.break_end:
                cur += duration
                continue
        is_past = target_date < now.date() or (
            target_date == now.date() and slot_start <= now.time()
        )
        if not is_past and slot_start not in booked:
            count += 1
        cur += duration
    return count


def _month_bounds(ref: date) -> tuple[date, date]:
    """Return (first_day, last_day) for the month of ref."""
    first = ref.replace(day=1)
    last = ref.replace(day=monthrange(ref.year, ref.month)[1])
    return first, last


def _prev_month(ref: date) -> date:
    """Return any day in the month before ref."""
    return (ref.replace(day=1) - timedelta(days=1))


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

async def get_doctor_dashboard(db: AsyncSession, user: User) -> dict:
    doctor = await _get_doctor_for_user(db, user)
    today = date.today()
    first_this_month, _ = _month_bounds(today)
    first_last_month, last_last_month = _month_bounds(_prev_month(today))

    # --- Today's in-clinic appointments ---
    today_appts_result = await db.execute(
        select(func.count(Appointment.id))
        .where(Appointment.doctor_id == doctor.id)
        .where(Appointment.appointment_date == today)
        .where(Appointment.is_active == True)
        .where(Appointment.status.not_in(["cancelled"]))
    )
    today_appointments: int = today_appts_result.scalar_one() or 0

    # --- Today's online consultations ---
    today_online_result = await db.execute(
        select(func.count(OnlineConsultation.id))
        .where(OnlineConsultation.doctor_id == doctor.id)
        .where(func.date(OnlineConsultation.scheduled_at) == today)
        .where(OnlineConsultation.status.not_in(["cancelled"]))
    )
    today_online_consults: int = today_online_result.scalar_one() or 0

    # --- This month earnings ---
    this_month_count_result = await db.execute(
        select(func.count(Appointment.id))
        .where(Appointment.doctor_id == doctor.id)
        .where(Appointment.appointment_date >= first_this_month)
        .where(Appointment.appointment_date <= today)
        .where(Appointment.status == "completed")
        .where(Appointment.is_active == True)
    )
    this_month_count: int = this_month_count_result.scalar_one() or 0
    this_month_earnings = Decimal(str(doctor.consultation_fee)) * this_month_count

    # Online earnings this month (stored per-row)
    this_online_result = await db.execute(
        select(func.coalesce(func.sum(OnlineConsultation.consultation_fee), 0))
        .where(OnlineConsultation.doctor_id == doctor.id)
        .where(func.date(OnlineConsultation.scheduled_at) >= first_this_month)
        .where(OnlineConsultation.status == "completed")
        .where(OnlineConsultation.payment_status == "paid")
    )
    this_month_earnings += Decimal(str(this_online_result.scalar_one() or 0))

    # --- Last month earnings ---
    last_month_count_result = await db.execute(
        select(func.count(Appointment.id))
        .where(Appointment.doctor_id == doctor.id)
        .where(Appointment.appointment_date >= first_last_month)
        .where(Appointment.appointment_date <= last_last_month)
        .where(Appointment.status == "completed")
        .where(Appointment.is_active == True)
    )
    last_month_count: int = last_month_count_result.scalar_one() or 0
    last_month_earnings = Decimal(str(doctor.consultation_fee)) * last_month_count

    last_online_result = await db.execute(
        select(func.coalesce(func.sum(OnlineConsultation.consultation_fee), 0))
        .where(OnlineConsultation.doctor_id == doctor.id)
        .where(func.date(OnlineConsultation.scheduled_at) >= first_last_month)
        .where(func.date(OnlineConsultation.scheduled_at) <= last_last_month)
        .where(OnlineConsultation.status == "completed")
        .where(OnlineConsultation.payment_status == "paid")
    )
    last_month_earnings += Decimal(str(last_online_result.scalar_one() or 0))

    if last_month_earnings > 0:
        earnings_comparison_pct = round(
            float((this_month_earnings - last_month_earnings) / last_month_earnings * 100), 1
        )
    else:
        earnings_comparison_pct = 0.0

    # --- Upcoming appointments (next 5) ---
    upcoming_result = await db.execute(
        select(Appointment, Patient)
        .join(Patient, Patient.id == Appointment.patient_id)
        .where(Appointment.doctor_id == doctor.id)
        .where(Appointment.appointment_date >= today)
        .where(Appointment.status.not_in(["cancelled", "completed"]))
        .where(Appointment.is_active == True)
        .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
        .limit(5)
    )
    upcoming_appointments = [
        {
            "id": appt.id,
            "patient_name": patient.name,
            "appointment_date": appt.appointment_date,
            "start_time": appt.start_time.strftime("%H:%M"),
            "end_time": appt.end_time.strftime("%H:%M"),
            "type": "in_clinic",
            "status": appt.status,
            "consultation_fee": doctor.consultation_fee,
        }
        for appt, patient in upcoming_result.all()
    ]

    # --- Weekly slots summary (next 7 days) ---
    sched_result = await db.execute(
        select(DoctorSchedule)
        .where(DoctorSchedule.doctor_id == doctor.id)
        .where(DoctorSchedule.is_active == True)
    )
    schedules = sched_result.scalars().all()
    schedule_by_dow = {s.day_of_week: s for s in schedules}
    weekly_slots = []
    for offset in range(7):
        target_date = today + timedelta(days=offset)
        dow = target_date.weekday()
        schedule = schedule_by_dow.get(dow)
        open_count = 0
        if schedule:
            booked_result = await db.execute(
                select(Appointment.start_time)
                .where(Appointment.doctor_id == doctor.id)
                .where(Appointment.appointment_date == target_date)
                .where(Appointment.status.not_in(["cancelled"]))
                .where(Appointment.is_active == True)
            )
            booked: set[time] = {row[0] for row in booked_result.all()}
            open_count = _count_open_slots(schedule, target_date, booked)
        weekly_slots.append({
            "date": target_date,
            "day_name": target_date.strftime("%A"),
            "open_slots_count": open_count,
        })

    # --- Recent reviews (last 3 verified) ---
    reviews_result = await db.execute(
        select(Review, Patient.name.label("patient_name"))
        .join(Patient, Review.patient_id == Patient.id)
        .where(Review.doctor_id == doctor.id)
        .where(Review.is_verified == True)
        .order_by(Review.created_at.desc())
        .limit(3)
    )
    recent_reviews = [
        {
            "id": row.Review.id,
            "patient_first_name": row.patient_name.split()[0] if row.patient_name else "Patient",
            "rating": row.Review.rating,
            "review_text": row.Review.review_text,
            "created_at": row.Review.created_at,
        }
        for row in reviews_result.all()
    ]

    return {
        "today_appointments": today_appointments,
        "today_online_consults": today_online_consults,
        "this_month_earnings": this_month_earnings,
        "last_month_earnings": last_month_earnings,
        "earnings_comparison_pct": earnings_comparison_pct,
        "rating": doctor.average_rating,
        "total_reviews": doctor.total_reviews,
        "upcoming_appointments": upcoming_appointments,
        "weekly_slots": weekly_slots,
        "recent_reviews": recent_reviews,
    }


# ---------------------------------------------------------------------------
# Appointments list
# ---------------------------------------------------------------------------

async def get_doctor_appointments(
    db: AsyncSession,
    user: User,
    appt_status: str,
    date_from: date | None,
    date_to: date | None,
    appt_type: str,
    page: int,
    per_page: int,
) -> dict:
    doctor = await _get_doctor_for_user(db, user)
    today = date.today()

    base = (
        select(Appointment, Patient)
        .join(Patient, Patient.id == Appointment.patient_id)
        .where(Appointment.doctor_id == doctor.id)
        .where(Appointment.is_active == True)
    )

    # Status filter
    if appt_status == "upcoming":
        base = base.where(Appointment.appointment_date >= today).where(
            Appointment.status.not_in(["cancelled", "completed"])
        )
    elif appt_status == "completed":
        base = base.where(Appointment.status == "completed")
    elif appt_status == "cancelled":
        base = base.where(Appointment.status == "cancelled")
    # else "all" — no filter

    # Date range filter
    if date_from:
        base = base.where(Appointment.appointment_date >= date_from)
    if date_to:
        base = base.where(Appointment.appointment_date <= date_to)

    # type filter — all appointments in this table are in_clinic
    # "video" type would come from online_consultations (not yet wired into booking)
    if appt_type == "video":
        return {
            "appointments": [],
            "total": 0,
            "page": page,
            "per_page": per_page,
            "total_pages": 0,
        }

    # Count
    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = count_result.scalar_one() or 0

    # Order: upcoming → ascending date/time; otherwise descending
    if appt_status == "upcoming":
        base = base.order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
    else:
        base = base.order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())

    base = base.offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(base)).all()

    appointments = [
        {
            "id": appt.id,
            "patient_name": patient.name,
            "patient_phone": patient.phone,
            "appointment_date": appt.appointment_date,
            "start_time": appt.start_time.strftime("%H:%M"),
            "end_time": appt.end_time.strftime("%H:%M"),
            "type": "in_clinic",
            "status": appt.status,
            "consultation_fee": doctor.consultation_fee,
            "booking_id": appt.booking_id,
            "notes": appt.notes,
        }
        for appt, patient in rows
    ]

    return {
        "appointments": appointments,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


# ---------------------------------------------------------------------------
# Profile update
# ---------------------------------------------------------------------------

_UPDATABLE_FIELDS = frozenset({
    "specialty", "degree", "experience_years",
    "consultation_fee", "online_consultation_fee",
    "is_available_online", "languages_spoken", "about_text", "gender",
    "address", "pincode", "city", "state", "latitude", "longitude",
})


async def update_doctor_profile(db: AsyncSession, user: User, updates: dict) -> Doctor:
    doctor = await _get_doctor_for_user(db, user)

    for field, value in updates.items():
        if field not in _UPDATABLE_FIELDS:
            continue  # silently skip immutable / admin-only fields
        setattr(doctor, field, value)

    await db.commit()
    await db.refresh(doctor)
    return doctor


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

async def get_doctor_schedule(db: AsyncSession, user: User) -> list[dict]:
    doctor = await _get_doctor_for_user(db, user)

    result = await db.execute(
        select(DoctorSchedule)
        .where(DoctorSchedule.doctor_id == doctor.id)
        .order_by(DoctorSchedule.day_of_week.asc())
    )
    schedules = result.scalars().all()

    return [
        {
            "id": s.id,
            "day_of_week": s.day_of_week,
            "day_name": _DAY_NAMES[s.day_of_week],
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
            "slot_duration_minutes": s.slot_duration_minutes,
            "break_start": s.break_start.strftime("%H:%M") if s.break_start else None,
            "break_end": s.break_end.strftime("%H:%M") if s.break_end else None,
            "is_active": s.is_active,
        }
        for s in schedules
    ]


async def update_doctor_schedule(
    db: AsyncSession,
    user: User,
    entries: list[ScheduleEntryInput],
) -> list[dict]:
    doctor = await _get_doctor_for_user(db, user)

    # Validate: start_time must be before end_time; break window must be within hours
    for entry in entries:
        start = _parse_time(entry.start_time)
        end = _parse_time(entry.end_time)
        if start >= end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Day {entry.day_of_week}: start_time must be before end_time",
            )
        if entry.break_start and entry.break_end:
            bs = _parse_time(entry.break_start)
            be = _parse_time(entry.break_end)
            if bs >= be:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Day {entry.day_of_week}: break_start must be before break_end",
                )
            if bs < start or be > end:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Day {entry.day_of_week}: break window must fall within working hours",
                )

    # Full replace: delete existing, insert new
    await db.execute(
        delete(DoctorSchedule).where(DoctorSchedule.doctor_id == doctor.id)
    )

    new_schedules = []
    for entry in entries:
        sched = DoctorSchedule(
            doctor_id=doctor.id,
            organization_id=doctor.organization_id,   # NULL for independent doctors — now nullable
            day_of_week=entry.day_of_week,
            start_time=_parse_time(entry.start_time),
            end_time=_parse_time(entry.end_time),
            slot_duration_minutes=entry.slot_duration_minutes,
            break_start=_parse_time(entry.break_start) if entry.break_start else None,
            break_end=_parse_time(entry.break_end) if entry.break_end else None,
            is_active=entry.is_active,
        )
        db.add(sched)
        new_schedules.append(sched)

    await db.commit()
    for s in new_schedules:
        await db.refresh(s)

    return [
        {
            "id": s.id,
            "day_of_week": s.day_of_week,
            "day_name": _DAY_NAMES[s.day_of_week],
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
            "slot_duration_minutes": s.slot_duration_minutes,
            "break_start": s.break_start.strftime("%H:%M") if s.break_start else None,
            "break_end": s.break_end.strftime("%H:%M") if s.break_end else None,
            "is_active": s.is_active,
        }
        for s in new_schedules
    ]


# ---------------------------------------------------------------------------
# Earnings
# ---------------------------------------------------------------------------

async def get_doctor_earnings(
    db: AsyncSession,
    user: User,
    period: str,
    date_from: date | None,
    date_to: date | None,
) -> dict:
    doctor = await _get_doctor_for_user(db, user)
    today = date.today()

    # --- Resolve current period bounds ---
    if period == "this_month":
        start, end = _month_bounds(today)
        end = today
        prev_start, prev_end = _month_bounds(_prev_month(today))
        period_label = today.strftime("%B %Y")
    elif period == "last_month":
        start, end = _month_bounds(_prev_month(today))
        pp = _prev_month(start)
        prev_start, prev_end = _month_bounds(pp)
        period_label = start.strftime("%B %Y")
    elif period == "this_year":
        start = today.replace(month=1, day=1)
        end = today
        prev_start = start.replace(year=start.year - 1)
        prev_end = end.replace(year=end.year - 1)
        period_label = str(today.year)
    else:  # "custom"
        if not date_from or not date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from and date_to are required for custom period",
            )
        start, end = date_from, date_to
        delta = (end - start).days + 1
        prev_start = start - timedelta(days=delta)
        prev_end = start - timedelta(days=1)
        period_label = f"{start.isoformat()} – {end.isoformat()}"

    # --- In-clinic earnings (count × fee) ---
    async def _count_completed(d_start: date, d_end: date) -> int:
        r = await db.execute(
            select(func.count(Appointment.id))
            .where(Appointment.doctor_id == doctor.id)
            .where(Appointment.status == "completed")
            .where(Appointment.is_active == True)
            .where(Appointment.appointment_date >= d_start)
            .where(Appointment.appointment_date <= d_end)
        )
        return r.scalar_one() or 0

    async def _online_earnings(d_start: date, d_end: date) -> Decimal:
        r = await db.execute(
            select(func.coalesce(func.sum(OnlineConsultation.consultation_fee), 0))
            .where(OnlineConsultation.doctor_id == doctor.id)
            .where(OnlineConsultation.status == "completed")
            .where(OnlineConsultation.payment_status == "paid")
            .where(func.date(OnlineConsultation.scheduled_at) >= d_start)
            .where(func.date(OnlineConsultation.scheduled_at) <= d_end)
        )
        return Decimal(str(r.scalar_one() or 0))

    current_count = await _count_completed(start, end)
    in_clinic_earnings = Decimal(str(doctor.consultation_fee)) * current_count
    online_earnings = await _online_earnings(start, end)
    total_earnings = in_clinic_earnings + online_earnings

    prev_count = await _count_completed(prev_start, prev_end)
    prev_in_clinic = Decimal(str(doctor.consultation_fee)) * prev_count
    prev_online = await _online_earnings(prev_start, prev_end)
    prev_total = prev_in_clinic + prev_online

    if prev_total > 0:
        comparison_pct = round(float((total_earnings - prev_total) / prev_total * 100), 1)
    else:
        comparison_pct = 0.0

    # --- Daily breakdown for chart ---
    daily_result = await db.execute(
        select(
            Appointment.appointment_date.label("appt_date"),
            func.count(Appointment.id).label("cnt"),
        )
        .where(Appointment.doctor_id == doctor.id)
        .where(Appointment.status == "completed")
        .where(Appointment.is_active == True)
        .where(Appointment.appointment_date >= start)
        .where(Appointment.appointment_date <= end)
        .group_by(Appointment.appointment_date)
        .order_by(Appointment.appointment_date.asc())
    )
    daily_earnings = [
        {
            "date": row.appt_date,
            "amount": Decimal(str(doctor.consultation_fee)) * row.cnt,
            "count": row.cnt,
        }
        for row in daily_result.all()
    ]

    return {
        "period_label": period_label,
        "total_earnings": total_earnings,
        "breakdown": {
            "in_clinic": in_clinic_earnings,
            "online": online_earnings,
        },
        "daily_earnings": daily_earnings,
        "comparison_percentage": comparison_pct,
    }


# ---------------------------------------------------------------------------
# Doctor's own reviews
# ---------------------------------------------------------------------------

async def get_doctor_reviews(
    db: AsyncSession,
    user: User,
    page: int,
    per_page: int,
) -> dict:
    doctor = await _get_doctor_for_user(db, user)

    base = (
        select(Review, Patient.name.label("patient_name"), Appointment.appointment_date.label("appt_date"))
        .join(Patient, Review.patient_id == Patient.id)
        .outerjoin(Appointment, Review.appointment_id == Appointment.id)
        .where(Review.doctor_id == doctor.id)
    )

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = count_result.scalar_one() or 0

    base = base.order_by(Review.created_at.desc())
    base = base.offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(base)).all()

    reviews = [
        {
            "id": row.Review.id,
            "patient_first_name": row.patient_name.split()[0] if row.patient_name else "Patient",
            "rating": row.Review.rating,
            "review_text": row.Review.review_text,
            "appointment_date": row.appt_date,
            "created_at": row.Review.created_at,
            "is_verified": row.Review.is_verified,
        }
        for row in rows
    ]

    return {
        "reviews": reviews,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


# ---------------------------------------------------------------------------
# Doctor's patients
# ---------------------------------------------------------------------------

async def get_doctor_patients(
    db: AsyncSession,
    user: User,
    page: int,
    per_page: int,
) -> dict:
    doctor = await _get_doctor_for_user(db, user)

    # Distinct patients who have had at least one appointment with this doctor
    patients_base = (
        select(
            Patient.id.label("patient_id"),
            Patient.name.label("patient_name"),
            Patient.phone.label("patient_phone"),
            func.max(Appointment.appointment_date).label("last_visit_date"),
            func.count(Appointment.id).label("total_visits"),
        )
        .join(Appointment, Appointment.patient_id == Patient.id)
        .where(Appointment.doctor_id == doctor.id)
        .where(Appointment.is_active == True)
        .where(Appointment.status == "completed")
        .group_by(Patient.id, Patient.name, Patient.phone)
    )

    # Count distinct patients
    count_result = await db.execute(
        select(func.count()).select_from(patients_base.subquery())
    )
    total: int = count_result.scalar_one() or 0

    patients_base = (
        patients_base
        .order_by(func.max(Appointment.appointment_date).desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(patients_base)).all()

    patients = [
        {
            "patient_id": row.patient_id,
            "patient_name": row.patient_name,
            "patient_phone": row.patient_phone,
            "last_visit_date": row.last_visit_date,
            "total_visits": row.total_visits,
        }
        for row in rows
    ]

    return {
        "patients": patients,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }

async def get_doctor_patient_detail(
    db: AsyncSession,
    user: User,
    patient_id: UUID,
) -> dict:
    doctor = await _get_doctor_for_user(db, user)

    # Fetch patient details
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    # Verify doctor has access
    appt_base = (
        select(Appointment)
        .where(Appointment.doctor_id == doctor.id)
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.is_active == True)
        .order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())
    )
    appointments_result = await db.execute(appt_base)
    appts = appointments_result.scalars().all()

    if not appts:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this patient")

    appointments_list = [
        {
            "id": appt.id,
            "patient_name": patient.name,
            "patient_phone": patient.phone,
            "appointment_date": appt.appointment_date,
            "start_time": appt.start_time.strftime("%H:%M"),
            "end_time": appt.end_time.strftime("%H:%M"),
            "type": "in_clinic",
            "status": appt.status,
            "consultation_fee": doctor.consultation_fee,
            "booking_id": appt.booking_id,
            "notes": appt.notes,
        }
        for appt in appts
    ]

    reports_base = (
        select(Report)
        .where(Report.patient_id == patient_id)
        .where(Report.is_active == True)
        .order_by(Report.created_at.desc())
    )
    reports_result = await db.execute(reports_base)
    reports = reports_result.scalars().all()

    from app.services.report_upload_service import get_public_url

    reports_list = [
        {
            "id": r.id,
            "title": r.title or r.file_name,
            "upload_type": r.upload_type or "report",
            "file_url": get_public_url(r.file_url) if r.file_url else None,
            "file_type": r.file_type or "application/pdf",
            "ai_analysis": r.ai_analysis,
            "ai_analysis_status": r.ai_analysis_status,
            "is_report_analysis": bool((r.file_type or "").startswith("image/")),
            "created_at": r.created_at,
        }
        for r in reports
    ]

    last_visit = next((a.appointment_date for a in appts if a.status == "completed"), None)
    
    patient_user = await db.get(User, patient.user_id) if patient.user_id else None
    
    # Extract allergies if it exists
    allergies = None
    if hasattr(patient, "allergies"):
        allergies = patient.allergies

    return {
        "patient_id": patient.id,
        "patient_name": patient.name,
        "patient_phone": patient.phone,
        "date_of_birth": patient.date_of_birth,
        "gender": patient.gender,
        "blood_group": patient.blood_group,
        "allergies": allergies,
        "avatar_url": patient_user.avatar_url if patient_user else None,
        "last_visit_date": last_visit,
        "total_visits": sum(1 for a in appts if a.status == "completed"),
        "reports": reports_list,
        "appointments": appointments_list,
    }


# ---------------------------------------------------------------------------
# Consultation Notes
# ---------------------------------------------------------------------------

async def upsert_consultation_note(
    db: AsyncSession,
    user: User,
    patient_id: UUID,
    content: str,
    client_updated_at: datetime | None = None,
    client_version: int | None = None,
) -> dict:
    """
    Create or update the doctor's note for a given patient.
    Uses INSERT … ON CONFLICT DO UPDATE so the caller never
    needs to worry whether a note already exists.
    """
    from app.models.consultation_note import ConsultationNote

    doctor = await _get_doctor_for_user(db, user)

    # Verify the patient has at least one appointment with this doctor
    access_check = await db.execute(
        select(Appointment).where(
            Appointment.doctor_id == doctor.id,
            Appointment.patient_id == patient_id,
        ).limit(1)
    )
    if access_check.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this patient's records.",
        )

    # Check for existing note
    result = await db.execute(
        select(ConsultationNote).where(
            ConsultationNote.doctor_id == doctor.id,
            ConsultationNote.patient_id == patient_id,
        )
    )
    note = result.scalar_one_or_none()

    if note is None:
        note = ConsultationNote(
            doctor_id=doctor.id,
            patient_id=patient_id,
            content=content,
            version=1
        )
        db.add(note)
    else:
        # Idempotency check: ignore stale updates based on version
        if client_version is not None and client_version < note.version:
            logger.info(f"AUDIT: Ignoring stale note update for Patient {patient_id}. Client version {client_version} < Server {note.version}")
            return {
                "id": note.id,
                "doctor_id": note.doctor_id,
                "patient_id": note.patient_id,
                "content": note.content,
                "version": note.version,
                "created_at": note.created_at,
                "updated_at": note.updated_at,
            }
        
        note.content = content
        note.version = note.version + 1

    audit = AuditLog(
        doctor_id=doctor.id,
        patient_id=patient_id,
        action="note_update"
    )
    db.add(audit)

    await db.commit()
    await db.refresh(note)

    logger.info(f"AUDIT: Consultation notes updated for Patient {patient_id} by Doctor {doctor.id}")

    return {
        "id": note.id,
        "doctor_id": note.doctor_id,
        "patient_id": note.patient_id,
        "content": note.content,
        "version": note.version,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


async def get_consultation_note(
    db: AsyncSession,
    user: User,
    patient_id: UUID,
) -> dict | None:
    """Return the doctor's note for a patient, or None if not yet created."""
    from app.models.consultation_note import ConsultationNote

    doctor = await _get_doctor_for_user(db, user)

    result = await db.execute(
        select(ConsultationNote).where(
            ConsultationNote.doctor_id == doctor.id,
            ConsultationNote.patient_id == patient_id,
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        return None

    return {
        "id": note.id,
        "doctor_id": note.doctor_id,
        "patient_id": note.patient_id,
        "content": note.content,
        "version": note.version,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }

async def get_audit_logs(
    db: AsyncSession,
    user: User,
    patient_id: UUID | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return recent audit logs for a doctor, optionally filtered by patient."""
    doctor = await _get_doctor_for_user(db, user)

    stmt = select(AuditLog).where(AuditLog.doctor_id == doctor.id)
    if patient_id:
        stmt = stmt.where(AuditLog.patient_id == patient_id)
    
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "doctor_id": log.doctor_id,
            "patient_id": log.patient_id,
            "appointment_id": log.appointment_id,
            "action": log.action,
            "created_at": log.created_at,
        }
        for log in logs
    ]
