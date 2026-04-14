"""
Doctor auth service — registration, login, profile.

Self-registered doctors are independent practitioners who sign up through
the patient-facing app. They go through a manual verification step where a
supreme_admin reviews their NMC certificate before they can log in.

Flow:
  1. POST /doctor/register    → creates User (is_active=False) + Doctor (is_verified=False)
  2. POST /doctor/register/upload-photo       → stores profile photo
  3. POST /doctor/register/upload-certificate → stores NMC certificate
  4. Admin reviews & approves via admin panel (sets is_active=True + is_verified=True)
  5. POST /doctor/login       → returns JWT once both flags are True
"""

from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.doctor import Doctor, DoctorEmploymentType
from app.models.user import User, UserRole
from app.schemas.doctor import (
    DoctorLoginRequest,
    DoctorLoginResponse,
    DoctorProfileResponse,
    DoctorRegisterRequest,
    DoctorRegisterResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_profile_response(user: User, doctor: Doctor) -> DoctorProfileResponse:
    return DoctorProfileResponse(
        user_id=user.id,
        name=user.name or "",
        email=user.email,
        phone=user.phone,
        doctor_id=doctor.id,
        nmc_registration_number=doctor.nmc_registration_number,
        specialty=doctor.specialty,
        specialization=doctor.specialization,
        degree=doctor.degree,
        experience_years=doctor.experience_years,
        gender=str(doctor.gender),
        consultation_fee=doctor.consultation_fee,
        online_consultation_fee=doctor.online_consultation_fee,
        is_available_online=doctor.is_available_online,
        languages_spoken=doctor.languages_spoken,
        about_text=doctor.about_text,
        profile_photo_url=doctor.profile_photo_url,
        registration_certificate_url=doctor.registration_certificate_url,
        address=doctor.address,
        pincode=doctor.pincode,
        city=doctor.city,
        state=doctor.state,
        latitude=doctor.latitude,
        longitude=doctor.longitude,
        average_rating=doctor.average_rating,
        total_reviews=doctor.total_reviews,
        is_independent=doctor.is_independent,
        is_verified=doctor.is_verified,
        self_registered=doctor.self_registered,
        is_active=user.is_active,
        created_at=doctor.created_at,
        updated_at=doctor.updated_at,
    )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

async def register_doctor(
    db: AsyncSession,
    data: DoctorRegisterRequest,
) -> DoctorRegisterResponse:
    # 1. Email uniqueness — check users table
    existing_user = await db.execute(
        select(User).where(User.email == data.email)
    )
    if existing_user.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # 2. NMC registration number uniqueness — check doctors table
    existing_nmc = await db.execute(
        select(Doctor).where(Doctor.nmc_registration_number == data.nmc_registration_number)
    )
    if existing_nmc.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This NMC registration number is already registered",
        )

    # 3. Create User account (inactive until admin approves)
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        name=data.name,
        phone=data.phone,
        role=UserRole.doctor,
        is_active=False,
        organization_id=None,
    )
    db.add(user)
    await db.flush()  # Get user.id without full commit

    # 4. Create Doctor record
    #    Hospital-legacy columns have sensible defaults for independent doctors:
    #      specialization  = specialty (same concept, different column name)
    #      license_number  = NMC number (the only license independent doctors have)
    #      license_expiry  = 10 years from today (placeholder — admin can update)
    #      employment_type = visiting (most appropriate for independent)
    doctor = Doctor(
        user_id=user.id,
        name=data.name,
        gender=data.gender,
        phone=data.phone,
        email=data.email,
        organization_id=None,
        # Legacy NOT NULL columns — mapped from self-registration fields
        specialization=data.specialty,
        license_number=data.nmc_registration_number,
        license_expiry=date.today() + timedelta(days=3650),
        employment_type=DoctorEmploymentType.visiting,
        experience_years=data.experience_years,
        # New independent-doctor columns
        is_independent=True,
        self_registered=True,
        is_verified=False,
        nmc_registration_number=data.nmc_registration_number,
        specialty=data.specialty,
        degree=data.degree,
        consultation_fee=data.consultation_fee,
        online_consultation_fee=data.online_consultation_fee,
        is_available_online=data.is_available_online,
        languages_spoken=data.languages_spoken,
        about_text=data.about_text,
        address=data.address,
        pincode=data.pincode,
        city=data.city,
        state=data.state,
        latitude=data.latitude,
        longitude=data.longitude,
        is_active=True,  # The doctor record itself is active; the user account is not
    )
    db.add(doctor)
    await db.commit()
    await db.refresh(user)
    await db.refresh(doctor)

    return DoctorRegisterResponse(
        message=(
            "Registration successful. Your profile is under verification. "
            "You will be notified once approved by the Medora administration."
        ),
        doctor_id=doctor.id,
        user_id=user.id,
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

async def login_doctor(
    db: AsyncSession,
    data: DoctorLoginRequest,
) -> DoctorLoginResponse:
    # 1. Find user by email
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Must be a doctor account
    if user.role != UserRole.doctor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account does not have doctor access",
        )

    # 3. Account activation check (admin must approve)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your profile is under verification. You will be able to login once approved by the Medora administration.",
        )

    # 4. Fetch linked doctor record
    doc_result = await db.execute(
        select(Doctor).where(Doctor.user_id == user.id)
    )
    doctor = doc_result.scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Doctor profile not found. Please contact support.",
        )

    # 5. NMC verification check
    if not doctor.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Profile pending NMC verification by admin. You will be notified once verified.",
        )

    # 6. Issue JWT
    access_token = create_access_token(subject=str(user.id), role=user.role.value)

    return DoctorLoginResponse(
        access_token=access_token,
        token_type="bearer",
        doctor=_build_profile_response(user, doctor),
    )


# ---------------------------------------------------------------------------
# Profile (GET /me)
# ---------------------------------------------------------------------------

async def get_doctor_profile(db: AsyncSession, user: User) -> DoctorProfileResponse:
    result = await db.execute(
        select(Doctor).where(Doctor.user_id == user.id)
    )
    doctor = result.scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found",
        )

    return _build_profile_response(user, doctor)
