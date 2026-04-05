import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.otp import OTPRecord
from app.models.patient import Patient
from app.schemas.patient_auth import (
    ForgotPasswordRequest,
    PatientLoginRequest,
    PatientRegisterRequest,
    ResetPasswordRequest,
    VerifyOTPRequest,
)


async def _generate_patient_code(db: AsyncSession) -> str:
    """Generate the next global PAT-NNNN code across all self-registered patients."""
    result = await db.execute(
        select(func.max(Patient.patient_code)).where(
            Patient.patient_code.like("PAT-%")
        )
    )
    max_code: str | None = result.scalar_one_or_none()
    if max_code is None:
        next_number = 1
    else:
        try:
            next_number = int(max_code.split("-")[1]) + 1
        except (IndexError, ValueError):
            next_number = 1
    return f"PAT-{next_number:04d}"


async def register_patient(db: AsyncSession, data: PatientRegisterRequest) -> dict:
    # 1. Email uniqueness check
    existing_email = await db.execute(
        select(Patient).where(Patient.email == data.email)
    )
    if existing_email.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # 2. Phone uniqueness check
    existing_phone = await db.execute(
        select(Patient).where(Patient.phone == data.phone)
    )
    if existing_phone.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already registered",
        )

    # 3. Hash password
    hashed = hash_password(data.password)

    # 4. Generate patient code
    patient_code = await _generate_patient_code(db)

    # 5. Create patient record (no org_id at self-registration time)
    patient = Patient(
        name=data.name,
        email=data.email,
        phone=data.phone,
        date_of_birth=data.date_of_birth,
        hashed_password=hashed,
        patient_code=patient_code,
        organization_id=None,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    # 6. Generate JWT (auto-login)
    access_token = create_access_token(subject=str(patient.id), role="patient")

    # 7. Return combined response dict
    return {
        "id": patient.id,
        "name": patient.name,
        "email": patient.email,
        "phone": patient.phone,
        "date_of_birth": patient.date_of_birth,
        "patient_code": patient.patient_code,
        "created_at": patient.created_at,
        "access_token": access_token,
        "token_type": "bearer",
    }


async def login_patient(db: AsyncSession, data: PatientLoginRequest) -> dict:
    # 1. Determine lookup field
    if "@" in data.identifier:
        result = await db.execute(
            select(Patient).where(Patient.email == data.identifier)
        )
    else:
        result = await db.execute(
            select(Patient).where(Patient.phone == data.identifier)
        )
    patient = result.scalar_one_or_none()

    # 2. Patient not found
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # 3. No password set (org-admin-created patient, never self-registered)
    if patient.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # 4. Wrong password
    if not verify_password(data.password, patient.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # 5. Deactivated account
    if not patient.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # 6. Generate token
    access_token = create_access_token(subject=str(patient.id), role="patient")

    # 7. Return token + brief info
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "email": patient.email,
            "phone": patient.phone,
            "patient_code": patient.patient_code,
        },
    }


def _mask_identifier(identifier: str) -> str:
    if "@" in identifier:
        local, domain = identifier.split("@", 1)
        return f"{local[:2]}***@{domain}"
    return f"****{identifier[-4:]}"


async def _find_patient_by_identifier(db: AsyncSession, identifier: str) -> Patient | None:
    if "@" in identifier:
        result = await db.execute(select(Patient).where(Patient.email == identifier))
    else:
        result = await db.execute(select(Patient).where(Patient.phone == identifier))
    return result.scalar_one_or_none()


async def forgot_password(db: AsyncSession, data: ForgotPasswordRequest) -> dict:
    patient = await _find_patient_by_identifier(db, data.identifier)

    # Always return the same response — don't reveal whether account exists
    masked = _mask_identifier(data.identifier)
    generic_response = {
        "message": "If this account exists, an OTP has been sent",
        "masked_identifier": masked,
    }

    if patient is None or not patient.is_active:
        return generic_response

    # Generate 6-digit OTP
    otp_code = f"{secrets.randbelow(1000000):06d}"

    # Delete any existing unused OTPs for this patient
    await db.execute(
        delete(OTPRecord).where(
            OTPRecord.patient_id == patient.id,
            OTPRecord.is_used == False,  # noqa: E712
        )
    )

    # Create new OTP record (expires in 10 minutes)
    otp = OTPRecord(
        patient_id=patient.id,
        otp_code=otp_code,
        identifier=data.identifier,
        purpose="password_reset",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(otp)
    await db.commit()

    # TODO: Send via email/SMS provider
    print(f"[MEDORA OTP] Patient {patient.email or patient.phone}: {otp_code}")

    return generic_response


async def verify_otp(db: AsyncSession, data: VerifyOTPRequest) -> dict:
    patient = await _find_patient_by_identifier(db, data.identifier)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

    # Rate-limit: 5+ failed (unused, expired or wrong) OTPs in last hour → 429
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    rate_result = await db.execute(
        select(func.count()).select_from(OTPRecord).where(
            OTPRecord.patient_id == patient.id,
            OTPRecord.is_used == False,  # noqa: E712
            OTPRecord.created_at >= one_hour_ago,
        )
    )
    if rate_result.scalar_one() >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts, try again later",
        )

    # Find latest unused OTP for this patient
    otp_result = await db.execute(
        select(OTPRecord)
        .where(
            OTPRecord.patient_id == patient.id,
            OTPRecord.purpose == "password_reset",
            OTPRecord.is_used == False,  # noqa: E712
        )
        .order_by(OTPRecord.created_at.desc())
        .limit(1)
    )
    otp = otp_result.scalar_one_or_none()

    if otp is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

    if datetime.now(timezone.utc) > otp.expires_at.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired")

    if otp.otp_code != data.otp_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

    # Mark as used
    otp.is_used = True
    await db.commit()

    # Issue short-lived reset token (15 minutes)
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload = {"sub": str(patient.id), "purpose": "password_reset", "exp": expire}
    reset_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return {"message": "OTP verified", "reset_token": reset_token}


async def google_login_patient(db: AsyncSession, credential: str) -> dict:
    from app.core.config import settings
    from app.core.google_auth import verify_google_token

    # 1. Verify Google token
    try:
        user_info = verify_google_token(credential, settings.GOOGLE_CLIENT_ID)
    except Exception:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    email = user_info.get("email")
    name = user_info.get("name") or email

    if not email:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token did not provide an email address",
        )

    # 2. Look up existing patient by email
    result = await db.execute(select(Patient).where(Patient.email == email))
    patient = result.scalar_one_or_none()

    if patient is not None:
        # Existing patient — just log in
        if not patient.is_active:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )
    else:
        # New patient — auto-register
        patient_code = await _generate_patient_code(db)
        # phone and date_of_birth are NOT NULL in the DB; use placeholders the
        # user can update from their profile later.
        placeholder_phone = f"GOOGLE_{secrets.token_hex(6)}"
        placeholder_dob = date(1900, 1, 1)

        patient = Patient(
            name=name,
            email=email,
            phone=placeholder_phone,
            date_of_birth=placeholder_dob,
            hashed_password=None,
            patient_code=patient_code,
            organization_id=None,
            is_active=True,
        )
        db.add(patient)
        await db.commit()
        await db.refresh(patient)

    # 3. Issue JWT
    access_token = create_access_token(subject=str(patient.id), role="patient")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "email": patient.email,
            "phone": patient.phone,
            "patient_code": patient.patient_code,
        },
    }


async def reset_password(db: AsyncSession, data: ResetPasswordRequest) -> dict:
    # Decode and validate reset token
    try:
        payload = jwt.decode(
            data.reset_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        patient_id: str = payload.get("sub")
        purpose: str = payload.get("purpose")
        if patient_id is None or purpose != "password_reset":
            raise JWTError
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token"
        )

    try:
        from uuid import UUID
        patient_uuid = UUID(patient_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token"
        )

    result = await db.execute(select(Patient).where(Patient.id == patient_uuid))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token"
        )

    # Update password
    patient.hashed_password = hash_password(data.new_password)

    # Cleanup all unused OTPs for this patient
    await db.execute(
        delete(OTPRecord).where(
            OTPRecord.patient_id == patient.id,
            OTPRecord.is_used == False,  # noqa: E712
        )
    )

    await db.commit()
    return {"message": "Password reset successful"}
