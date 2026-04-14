"""
Doctor auth router — registration, file uploads, login, profile.

All endpoints live under the prefix /api/v1/doctor (set in main.py).

Public (no JWT required):
  POST /register                  — self-registration
  POST /register/upload-photo     — profile photo upload
  POST /register/upload-certificate — NMC certificate upload
  POST /login                     — get JWT (only after admin approval)

Authenticated (JWT + role=doctor required):
  GET  /me                        — full profile for the doctor dashboard
"""

import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor, get_current_user
from app.core.storage import upload_doctor_certificate, upload_doctor_photo
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.user import User
from app.schemas.doctor import (
    DoctorLoginRequest,
    DoctorLoginResponse,
    DoctorProfileResponse,
    DoctorRegisterRequest,
    DoctorRegisterResponse,
)
from app.services.doctor_auth_service import (
    get_doctor_profile,
    login_doctor,
    register_doctor,
)

router = APIRouter(tags=["Doctor Auth"])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_ALLOWED_DOC_TYPES = {"application/pdf", "image/jpeg", "image/png"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=DoctorRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Doctor self-registration",
    description=(
        "Creates a User account (role='doctor', is_active=False) and a linked "
        "Doctor record (is_verified=False). The account is inactive until a "
        "supreme_admin approves it. Upload profile photo and NMC certificate "
        "using the /register/upload-photo and /register/upload-certificate "
        "endpoints immediately after."
    ),
)
async def register_doctor_endpoint(
    data: DoctorRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> DoctorRegisterResponse:
    return await register_doctor(db, data)


@router.post(
    "/register/upload-photo",
    summary="Upload doctor profile photo",
    description=(
        "Multipart upload of the doctor's profile photo. "
        "Stores it at doctors/{doctor_id}/profile.{ext} in the public bucket. "
        "No authentication required — call this right after /register."
    ),
)
async def upload_profile_photo(
    doctor_id: str = Form(..., description="doctor_id returned by /register"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # Validate content type
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: JPEG, PNG, WebP.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the 10 MB limit",
        )

    # Resolve doctor record
    result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    # Derive extension from filename or content-type
    ext = _get_extension(file.filename, file.content_type)

    public_url = upload_doctor_photo(
        file_bytes=file_bytes,
        content_type=file.content_type,
        doctor_id=doctor.id,
        ext=ext,
    )

    doctor.profile_photo_url = public_url
    await db.commit()

    return {"message": "Profile photo uploaded successfully", "profile_photo_url": public_url}


@router.post(
    "/register/upload-certificate",
    summary="Upload NMC registration certificate",
    description=(
        "Multipart upload of the doctor's NMC registration certificate (PDF or image). "
        "Stored at doctors/{doctor_id}/nmc_certificate.{ext} in the public bucket. "
        "No authentication required — call this right after /register."
    ),
)
async def upload_nmc_certificate(
    doctor_id: str = Form(..., description="doctor_id returned by /register"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in _ALLOWED_DOC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: PDF, JPEG, PNG.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the 10 MB limit",
        )

    result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    ext = _get_extension(file.filename, file.content_type)

    public_url = upload_doctor_certificate(
        file_bytes=file_bytes,
        content_type=file.content_type,
        doctor_id=doctor.id,
        ext=ext,
    )

    # Reuse registration_certificate_url — the existing field for credential docs
    doctor.registration_certificate_url = public_url
    await db.commit()

    return {
        "message": "NMC certificate uploaded successfully",
        "certificate_url": public_url,
    }


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=DoctorLoginResponse,
    summary="Doctor login",
    description=(
        "Returns a JWT access token plus the full doctor profile. "
        "Blocked with 403 if the account is not yet approved (is_active=False) "
        "or if the NMC verification is pending (is_verified=False)."
    ),
)
async def login_doctor_endpoint(
    data: DoctorLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> DoctorLoginResponse:
    return await login_doctor(db, data)


# ---------------------------------------------------------------------------
# Authenticated — doctor dashboard
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    response_model=DoctorProfileResponse,
    summary="Get authenticated doctor's profile",
    description="Returns the full doctor profile for the currently logged-in doctor.",
)
async def get_doctor_me(
    current_user: User = Depends(get_current_user),
    _doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
) -> DoctorProfileResponse:
    return await get_doctor_profile(db, current_user)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_extension(filename: str | None, content_type: str) -> str:
    """Derive a safe file extension from the filename or fall back to content-type."""
    if filename:
        _, ext = os.path.splitext(filename)
        if ext:
            return ext.lstrip(".").lower()
    _ct_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "application/pdf": "pdf",
    }
    return _ct_map.get(content_type, "bin")
