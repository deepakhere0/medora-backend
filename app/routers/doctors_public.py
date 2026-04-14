"""
doctors_public.py

Public-facing doctor discovery endpoints — no authentication required except
for POST /reviews (patient must be logged in to leave a review).

Registered in main.py BEFORE the existing doctor_router so that static paths
(/search, /specialties) are matched before the /{doctor_id} pattern.

All endpoints hard-filter on is_verified=True so unverified doctors never
surface, regardless of query parameters.
"""

from datetime import date as date_type
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.patient import Patient
from app.schemas.doctor import (
    CreateReviewRequest,
    CreateReviewResponse,
    DoctorSearchResponse,
    PublicDoctorProfileResponse,
    ReviewsResponse,
    SpecialtiesResponse,
)
from app.services.doctors_public_service import (
    create_review,
    get_available_slots_public,
    get_public_profile,
    get_reviews,
    get_specialties,
    search_doctors,
)

router = APIRouter(tags=["Doctors Public"])


# ---------------------------------------------------------------------------
# GET /search
# ---------------------------------------------------------------------------

@router.get(
    "/search",
    response_model=DoctorSearchResponse,
    summary="Search verified independent doctors",
    description=(
        "Public endpoint. Returns paginated, filtered, and optionally sorted "
        "doctors. Only is_verified=True doctors whose user account is active "
        "are returned. Pass lat/lng to enable proximity filtering and distance "
        "in the response."
    ),
)
async def search_doctors_endpoint(
    lat: float | None = Query(default=None, description="Caller's latitude"),
    lng: float | None = Query(default=None, description="Caller's longitude"),
    radius_km: int = Query(default=20, ge=1, le=500, description="Search radius in km (requires lat/lng)"),
    specialty: str | None = Query(default=None, description="Filter by specialty (partial match)"),
    min_fee: int | None = Query(default=None, ge=0),
    max_fee: int | None = Query(default=None, ge=0),
    min_rating: float | None = Query(default=None, ge=0.0, le=5.0),
    min_experience: int | None = Query(default=None, ge=0),
    is_available_online: bool | None = Query(default=None),
    gender: str | None = Query(default=None, description="'male', 'female', or 'other'"),
    language: str | None = Query(default=None, description="Match against languages_spoken"),
    available_today: bool | None = Query(default=None, description="Has schedule active today"),
    sort_by: str = Query(
        default="relevance",
        description="relevance | rating | fee_low | fee_high | experience | distance",
    ),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> DoctorSearchResponse:
    result = await search_doctors(
        db,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        specialty=specialty,
        min_fee=min_fee,
        max_fee=max_fee,
        min_rating=min_rating,
        min_experience=min_experience,
        is_available_online=is_available_online,
        gender=gender,
        language=language,
        available_today=available_today,
        sort_by=sort_by,
        page=page,
        per_page=per_page,
    )
    return DoctorSearchResponse(**result)


# ---------------------------------------------------------------------------
# GET /specialties
# ---------------------------------------------------------------------------

@router.get(
    "/specialties",
    response_model=SpecialtiesResponse,
    summary="List all distinct specialties (for filter dropdown)",
    description="Returns a deduplicated, alphabetically sorted list of specialties from verified doctors. Cached for 5 minutes.",
)
async def list_specialties(
    db: AsyncSession = Depends(get_db),
) -> SpecialtiesResponse:
    specialties = await get_specialties(db)
    return SpecialtiesResponse(specialties=specialties)


# ---------------------------------------------------------------------------
# GET /{doctor_id}/public-profile
# ---------------------------------------------------------------------------

@router.get(
    "/{doctor_id}/public-profile",
    response_model=PublicDoctorProfileResponse,
    summary="Full public doctor profile",
    description=(
        "Returns full profile including about_text, qualifications, address, "
        "the 5 most recent verified reviews, and slot availability for the next 7 days. "
        "404 if the doctor is not verified or the user account is inactive."
    ),
)
async def get_public_profile_endpoint(
    doctor_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PublicDoctorProfileResponse:
    data = await get_public_profile(db, doctor_id)
    return PublicDoctorProfileResponse(**data)


# ---------------------------------------------------------------------------
# GET /{doctor_id}/available-slots
# ---------------------------------------------------------------------------

@router.get(
    "/{doctor_id}/available-slots",
    summary="Available appointment slots",
    description=(
        "Returns available time slots grouped by date for the next N days. "
        "Only future, un-booked slots are included. Days with no open slots "
        "are omitted from the response. "
        "Format: { '2026-04-15': ['09:00', '09:30', ...], ... }"
    ),
)
async def available_slots_endpoint(
    doctor_id: UUID,
    start_date: date_type | None = Query(
        default=None,
        alias="date",
        description="Start date (YYYY-MM-DD). Defaults to today.",
    ),
    days: int = Query(default=7, ge=1, le=30, description="Number of days to look ahead"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    from_date = start_date if start_date is not None else date_type.today()
    return await get_available_slots_public(db, doctor_id, from_date, days)


# ---------------------------------------------------------------------------
# GET /{doctor_id}/reviews
# ---------------------------------------------------------------------------

@router.get(
    "/{doctor_id}/reviews",
    response_model=ReviewsResponse,
    summary="Paginated verified reviews for a doctor",
)
async def get_reviews_endpoint(
    doctor_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=50),
    sort: str = Query(default="recent", description="recent | highest | lowest"),
    db: AsyncSession = Depends(get_db),
) -> ReviewsResponse:
    result = await get_reviews(db, doctor_id, page=page, per_page=per_page, sort=sort)
    return ReviewsResponse(**result)


# ---------------------------------------------------------------------------
# POST /{doctor_id}/reviews  (requires patient auth)
# ---------------------------------------------------------------------------

@router.post(
    "/{doctor_id}/reviews",
    response_model=CreateReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a review for a doctor (patient only)",
    description=(
        "Requires a valid patient JWT. The appointment must belong to the "
        "authenticated patient, reference this doctor, and have status='completed'. "
        "One review per appointment is enforced by a DB unique constraint. "
        "The doctor's cached average_rating and total_reviews are recalculated immediately."
    ),
)
async def create_review_endpoint(
    doctor_id: UUID,
    body: CreateReviewRequest,
    current_patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> CreateReviewResponse:
    result = await create_review(
        db,
        doctor_id=doctor_id,
        patient_id=current_patient.id,
        appointment_id=body.appointment_id,
        rating=body.rating,
        review_text=body.review_text,
    )
    return CreateReviewResponse(**result)
