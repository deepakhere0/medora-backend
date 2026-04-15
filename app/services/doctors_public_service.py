"""
doctors_public_service.py

All business logic for the public-facing doctor discovery API.

Design rules:
  - ONLY verified doctors (is_verified=True, user.is_active=True) are returned.
  - Doctor email / phone are NEVER included in any response.
  - Haversine distance is computed in PostgreSQL via func.acos; the argument is
    clamped to [-1, 1] to avoid a domain error from floating-point rounding.
  - Specialties are held in a module-level TTL cache (5 minutes) to avoid a
    full-table scan on every filter dropdown load.
"""

import time as _time
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.patient import Patient
from app.models.review import Review
from app.models.user import User


# ---------------------------------------------------------------------------
# Haversine helper
# ---------------------------------------------------------------------------

def _haversine_expr(lat: float, lng: float):
    """
    SQLAlchemy column expression for great-circle distance (km) from a fixed
    point (lat, lng) to Doctor.latitude / Doctor.longitude.

    The acos argument is clamped to [-1, 1] so that floating-point precision
    near 0° distance never produces NaN / a domain error.
    """
    inner = (
        func.cos(func.radians(lat))
        * func.cos(func.radians(Doctor.latitude))
        * func.cos(func.radians(Doctor.longitude) - func.radians(lng))
        + func.sin(func.radians(lat))
        * func.sin(func.radians(Doctor.latitude))
    )
    clamped = func.least(1.0, func.greatest(-1.0, inner))
    return (6371 * func.acos(clamped)).label("distance_km")


# ---------------------------------------------------------------------------
# Specialty cache
# ---------------------------------------------------------------------------

_specialty_cache: list[str] | None = None
_specialty_cache_ts: float = 0.0
_CACHE_TTL_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Slot generation (lightweight, no morning/afternoon split)
# ---------------------------------------------------------------------------

def _available_slot_strings(
    schedule: DoctorSchedule,
    target_date: date,
    booked_starts: set[time],
    now: datetime,
) -> list[str]:
    """
    Return HH:MM strings for every slot that is in the future and not booked.
    Mirrors the logic in booking_service._generate_slots_for_day but produces
    a flat list of available start-time strings instead of AvailableSlot objects.
    """
    slots: list[str] = []
    duration = timedelta(minutes=schedule.slot_duration_minutes)
    cur = datetime.combine(target_date, schedule.start_time)
    end = datetime.combine(target_date, schedule.end_time)

    while cur + duration <= end:
        slot_start = cur.time()

        # Skip break window
        if schedule.break_start and schedule.break_end:
            if schedule.break_start <= slot_start < schedule.break_end:
                cur += duration
                continue

        is_past = target_date < now.date() or (
            target_date == now.date() and slot_start <= now.time()
        )
        if not is_past and slot_start not in booked_starts:
            slots.append(slot_start.strftime("%H:%M"))

        cur += duration

    return slots


# ---------------------------------------------------------------------------
# Base verified-doctor filter (shared by all public queries)
# ---------------------------------------------------------------------------

def _verified_doctor_base_stmt():
    """
    SELECT doctors.* JOIN users ON doctors.user_id = users.id
    WHERE doctors.is_verified = true
      AND users.is_active   = true
      AND doctors.is_active  = true

    INNER JOIN means hospital-affiliated doctors (user_id IS NULL) are excluded,
    which is intentional — they're discovered through the hospital booking flow.
    """
    return (
        select(Doctor)
        .join(User, Doctor.user_id == User.id)
        .where(Doctor.is_verified == True)
        .where(User.is_active == True)
        .where(Doctor.is_active == True)
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search_doctors(
    db: AsyncSession,
    *,
    lat: float | None,
    lng: float | None,
    radius_km: int,
    specialty: str | None,
    min_fee: int | None,
    max_fee: int | None,
    min_rating: float | None,
    min_experience: int | None,
    is_available_online: bool | None,
    gender: str | None,
    language: str | None,
    available_today: bool | None,
    sort_by: str,
    page: int,
    per_page: int,
) -> dict:
    use_location = lat is not None and lng is not None
    haversine = _haversine_expr(lat, lng) if use_location else None

    # ------------------------------------------------------------------
    # Build base statement
    # ------------------------------------------------------------------
    if use_location:
        stmt = (
            select(Doctor, haversine)
            .join(User, Doctor.user_id == User.id)
            .where(Doctor.is_verified == True)
            .where(User.is_active == True)
            .where(Doctor.is_active == True)
            .where(Doctor.latitude.is_not(None))
            .where(Doctor.longitude.is_not(None))
        )
    else:
        stmt = _verified_doctor_base_stmt()

    # ------------------------------------------------------------------
    # Optional filters
    # ------------------------------------------------------------------
    if specialty:
        # Match against both the new `specialty` column and legacy `specialization`
        stmt = stmt.where(
            Doctor.specialty.ilike(f"%{specialty}%")
            | Doctor.specialization.ilike(f"%{specialty}%")
        )
    if min_fee is not None:
        stmt = stmt.where(Doctor.consultation_fee >= min_fee)
    if max_fee is not None:
        stmt = stmt.where(Doctor.consultation_fee <= max_fee)
    if min_rating is not None:
        stmt = stmt.where(Doctor.average_rating >= min_rating)
    if min_experience is not None:
        stmt = stmt.where(Doctor.experience_years >= min_experience)
    if is_available_online is not None:
        stmt = stmt.where(Doctor.is_available_online == is_available_online)
    if gender:
        stmt = stmt.where(Doctor.gender == gender)
    if language:
        stmt = stmt.where(Doctor.languages_spoken.ilike(f"%{language}%"))
    if available_today:
        today_dow = date.today().weekday()
        has_schedule = exists(
            select(DoctorSchedule.id).where(
                and_(
                    DoctorSchedule.doctor_id == Doctor.id,
                    DoctorSchedule.day_of_week == today_dow,
                    DoctorSchedule.is_active == True,
                )
            )
        )
        stmt = stmt.where(has_schedule)

    # Radius filter (applied via WHERE to avoid HAVING without GROUP BY)
    if use_location and radius_km:
        stmt = stmt.where(
            (6371 * func.acos(
                func.least(1.0, func.greatest(-1.0,
                    func.cos(func.radians(lat)) * func.cos(func.radians(Doctor.latitude))
                    * func.cos(func.radians(Doctor.longitude) - func.radians(lng))
                    + func.sin(func.radians(lat)) * func.sin(func.radians(Doctor.latitude))
                ))
            )) <= radius_km
        )

    # ------------------------------------------------------------------
    # Count (separate query without ORDER BY / LIMIT)
    # ------------------------------------------------------------------
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    # ------------------------------------------------------------------
    # Sort
    # ------------------------------------------------------------------
    if sort_by == "rating":
        stmt = stmt.order_by(Doctor.average_rating.desc(), Doctor.total_reviews.desc())
    elif sort_by == "fee_low":
        stmt = stmt.order_by(Doctor.consultation_fee.asc())
    elif sort_by == "fee_high":
        stmt = stmt.order_by(Doctor.consultation_fee.desc())
    elif sort_by == "experience":
        stmt = stmt.order_by(Doctor.experience_years.desc())
    elif sort_by == "distance" and use_location:
        stmt = stmt.order_by(haversine.asc())
    else:  # "relevance"
        stmt = stmt.order_by(Doctor.average_rating.desc(), Doctor.total_reviews.desc())

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    # ------------------------------------------------------------------
    # Shape results
    # ------------------------------------------------------------------
    doctors_out = []
    if use_location:
        # select(Doctor, haversine) → Row[Doctor, float]; use integer indexing
        rows = (await db.execute(stmt)).all()
        for row in rows:
            doctor, dist = row[0], row[1]
            doctors_out.append(_doctor_to_search_item(doctor, dist))
    else:
        # select(Doctor) → use .scalars() to get plain Doctor ORM instances
        doctors = (await db.execute(stmt)).scalars().all()
        for doctor in doctors:
            doctors_out.append(_doctor_to_search_item(doctor, None))

    return {
        "doctors": doctors_out,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


def _doctor_to_search_item(doctor: Doctor, distance_km: float | None) -> dict:
    return {
        "doctor_id": doctor.id,
        "name": doctor.name,
        "specialty": doctor.specialty,
        "specialization": doctor.specialization,
        "degree": doctor.degree,
        "experience_years": doctor.experience_years,
        "consultation_fee": doctor.consultation_fee,
        "online_consultation_fee": doctor.online_consultation_fee,
        "is_available_online": doctor.is_available_online,
        "average_rating": doctor.average_rating,
        "total_reviews": doctor.total_reviews,
        "profile_photo_url": doctor.profile_photo_url,
        "city": doctor.city,
        "state": doctor.state,
        "languages_spoken": doctor.languages_spoken,
        "gender": str(doctor.gender),
        "distance_km": round(float(distance_km), 2) if distance_km is not None else None,
    }


# ---------------------------------------------------------------------------
# Public profile
# ---------------------------------------------------------------------------

async def get_public_profile(db: AsyncSession, doctor_id: UUID) -> dict:
    # Verified doctor + user check via join
    result = await db.execute(
        _verified_doctor_base_stmt().where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found or not yet verified",
        )

    # Recent 5 verified reviews
    reviews_result = await db.execute(
        select(Review, Patient.name.label("patient_name"))
        .join(Patient, Review.patient_id == Patient.id)
        .where(Review.doctor_id == doctor_id)
        .where(Review.is_verified == True)
        .order_by(Review.created_at.desc())
        .limit(5)
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

    # Available slots for next 7 days
    available_slots = await _compute_slots(db, doctor_id, date.today(), days=7)

    return {
        "doctor_id": doctor.id,
        "name": doctor.name,
        "specialty": doctor.specialty,
        "specialization": doctor.specialization,
        "degree": doctor.degree,
        "experience_years": doctor.experience_years,
        "gender": str(doctor.gender),
        "consultation_fee": doctor.consultation_fee,
        "online_consultation_fee": doctor.online_consultation_fee,
        "is_available_online": doctor.is_available_online,
        "languages_spoken": doctor.languages_spoken,
        "about_text": doctor.about_text,
        "profile_photo_url": doctor.profile_photo_url,
        "registration_certificate_url": doctor.registration_certificate_url,
        "address": doctor.address,
        "pincode": doctor.pincode,
        "city": doctor.city,
        "state": doctor.state,
        "latitude": doctor.latitude,
        "longitude": doctor.longitude,
        "average_rating": doctor.average_rating,
        "total_reviews": doctor.total_reviews,
        "recent_reviews": recent_reviews,
        "available_slots": available_slots,
    }


# ---------------------------------------------------------------------------
# Available slots
# ---------------------------------------------------------------------------

async def get_available_slots_public(
    db: AsyncSession,
    doctor_id: UUID,
    from_date: date,
    days: int,
) -> dict[str, list[str]]:
    # Basic existence check (no user join needed — slots are public for any verified doctor)
    doc_result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id).where(Doctor.is_verified == True)
    )
    if doc_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found or not verified",
        )
    return await _compute_slots(db, doctor_id, from_date, days)


async def _compute_slots(
    db: AsyncSession,
    doctor_id: UUID,
    from_date: date,
    days: int,
) -> dict[str, list[str]]:
    """Shared implementation used by both get_available_slots_public and get_public_profile."""
    # Load schedules
    sched_result = await db.execute(
        select(DoctorSchedule)
        .where(DoctorSchedule.doctor_id == doctor_id)
        .where(DoctorSchedule.is_active == True)
    )
    schedules = sched_result.scalars().all()
    if not schedules:
        return {}

    schedule_by_dow: dict[int, DoctorSchedule] = {s.day_of_week: s for s in schedules}
    now = datetime.now()
    slots_by_date: dict[str, list[str]] = {}

    for offset in range(days):
        target_date = from_date + timedelta(days=offset)
        dow = target_date.weekday()
        schedule = schedule_by_dow.get(dow)
        if schedule is None:
            continue  # Doctor doesn't work this weekday

        # Already-booked start times for this doctor on this date
        booked_result = await db.execute(
            select(Appointment.start_time)
            .where(Appointment.doctor_id == doctor_id)
            .where(Appointment.appointment_date == target_date)
            .where(Appointment.status.in_(["scheduled", "confirmed", "in_progress"]))
            .where(Appointment.is_active == True)
        )
        booked_starts: set[time] = {row[0] for row in booked_result.all()}

        day_slots = _available_slot_strings(schedule, target_date, booked_starts, now)
        if day_slots:  # Only include days that have at least one open slot
            slots_by_date[target_date.isoformat()] = day_slots

    return slots_by_date


# ---------------------------------------------------------------------------
# Reviews (read)
# ---------------------------------------------------------------------------

async def get_reviews(
    db: AsyncSession,
    doctor_id: UUID,
    page: int,
    per_page: int,
    sort: str,
) -> dict:
    # Verify doctor exists and is verified
    doc_result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id).where(Doctor.is_verified == True)
    )
    if doc_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found or not verified",
        )

    base = (
        select(Review, Patient.name.label("patient_name"))
        .join(Patient, Review.patient_id == Patient.id)
        .where(Review.doctor_id == doctor_id)
        .where(Review.is_verified == True)
    )

    # Count
    count_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total: int = count_result.scalar_one()

    # Sort
    if sort == "highest":
        base = base.order_by(Review.rating.desc(), Review.created_at.desc())
    elif sort == "lowest":
        base = base.order_by(Review.rating.asc(), Review.created_at.desc())
    else:  # "recent"
        base = base.order_by(Review.created_at.desc())

    base = base.offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(base)).all()

    reviews = [
        {
            "id": row.Review.id,
            "patient_first_name": row.patient_name.split()[0] if row.patient_name else "Patient",
            "rating": row.Review.rating,
            "review_text": row.Review.review_text,
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
# Reviews (write)
# ---------------------------------------------------------------------------

async def create_review(
    db: AsyncSession,
    doctor_id: UUID,
    patient_id: UUID,
    appointment_id: UUID,
    rating: int,
    review_text: str | None,
) -> dict:
    # 1. Doctor must be verified
    doc_result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id).where(Doctor.is_verified == True)
    )
    doctor = doc_result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found or not verified",
        )

    # 2. Appointment must exist, belong to this patient, and be completed
    appt_result = await db.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .where(Appointment.patient_id == patient_id)
        .where(Appointment.doctor_id == doctor_id)
    )
    appointment = appt_result.scalar_one_or_none()
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    if appointment.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can only review a completed appointment",
        )

    # 3. One review per appointment (DB also enforces this via UNIQUE constraint)
    existing = await db.execute(
        select(Review).where(
            Review.doctor_id == doctor_id,
            Review.appointment_id == appointment_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already reviewed this appointment",
        )

    # 4. Create review — automatically verified because it's linked to a completed appointment
    review = Review(
        doctor_id=doctor_id,
        patient_id=patient_id,
        appointment_id=appointment_id,
        rating=rating,
        review_text=review_text,
        is_verified=True,
    )
    db.add(review)
    await db.flush()  # persist before recalculating aggregates

    # 5. Recalculate doctor's cached rating and review count
    agg_result = await db.execute(
        select(
            func.avg(Review.rating).label("avg_rating"),
            func.count(Review.id).label("review_count"),
        ).where(Review.doctor_id == doctor_id)
    )
    agg = agg_result.one()
    doctor.average_rating = round(float(agg.avg_rating or 0), 2)
    doctor.total_reviews = agg.review_count or 0

    await db.commit()
    await db.refresh(review)

    return {
        "id": review.id,
        "doctor_id": review.doctor_id,
        "rating": review.rating,
        "review_text": review.review_text,
        "is_verified": review.is_verified,
        "created_at": review.created_at,
        "message": "Review submitted successfully",
    }


# ---------------------------------------------------------------------------
# Specialties
# ---------------------------------------------------------------------------

async def get_specialties(db: AsyncSession) -> list[str]:
    """
    Returns distinct specialty labels from all verified doctors.
    Result is cached for 5 minutes so the filter dropdown is cheap to load.
    """
    global _specialty_cache, _specialty_cache_ts

    if _specialty_cache is not None and (_time.time() - _specialty_cache_ts) < _CACHE_TTL_SECONDS:
        return _specialty_cache

    result = await db.execute(
        select(Doctor.specialty)
        .join(User, Doctor.user_id == User.id)
        .where(Doctor.is_verified == True)
        .where(User.is_active == True)
        .where(Doctor.specialty.is_not(None))
        .distinct()
        .order_by(Doctor.specialty.asc())
    )
    specialties = [row[0] for row in result.all() if row[0]]

    _specialty_cache = specialties
    _specialty_cache_ts = _time.time()
    return specialties
