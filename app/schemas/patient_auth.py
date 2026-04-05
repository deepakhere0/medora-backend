import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


class PatientRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    date_of_birth: date
    password: str

    @field_validator("name")
    @classmethod
    def name_min_length(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip()

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        digits = re.sub(r"[\s\-\(\)]", "", v)
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return digits

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v


class PatientRegisterResponse(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str
    date_of_birth: date
    patient_code: str
    created_at: datetime
    access_token: str
    token_type: str = "bearer"

    model_config = {"from_attributes": True}


class PatientBrief(BaseModel):
    id: UUID
    name: str
    email: str | None
    phone: str
    patient_code: str

    model_config = {"from_attributes": True}


class PatientLoginRequest(BaseModel):
    identifier: str
    password: str


class PatientLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    patient: PatientBrief


class ForgotPasswordRequest(BaseModel):
    identifier: str


class ForgotPasswordResponse(BaseModel):
    message: str
    masked_identifier: str


class VerifyOTPRequest(BaseModel):
    identifier: str
    otp_code: str


class VerifyOTPResponse(BaseModel):
    message: str
    reset_token: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v


class ResetPasswordResponse(BaseModel):
    message: str


class GoogleLoginRequest(BaseModel):
    credential: str
