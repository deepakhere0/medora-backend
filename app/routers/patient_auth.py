from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_patient
from app.db.session import get_db
from app.models.patient import Patient
from app.schemas.patient_auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GoogleLoginRequest,
    PatientBrief,
    PatientLoginRequest,
    PatientLoginResponse,
    PatientRegisterRequest,
    PatientRegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.services.patient_auth_service import (
    forgot_password,
    google_login_patient,
    login_patient,
    register_patient,
    reset_password,
    verify_otp,
)

router = APIRouter(prefix="/auth/patient", tags=["Patient Auth"])


@router.post(
    "/register",
    response_model=PatientRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_patient_endpoint(
    data: PatientRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    return await register_patient(db, data)


@router.post("/login", response_model=PatientLoginResponse)
async def login_patient_endpoint(
    data: PatientLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    return await login_patient(db, data)


@router.get("/me", response_model=PatientBrief)
async def get_patient_me(
    current_patient: Patient = Depends(get_current_patient),
):
    return current_patient


@router.post("/google-login", response_model=PatientLoginResponse)
async def google_login_patient_endpoint(
    data: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    return await google_login_patient(db, data.credential)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password_endpoint(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    return await forgot_password(db, data)


@router.post("/verify-otp", response_model=VerifyOTPResponse)
async def verify_otp_endpoint(
    data: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
):
    return await verify_otp(db, data)


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password_endpoint(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    return await reset_password(db, data)
