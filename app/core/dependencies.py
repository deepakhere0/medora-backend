import logging
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise JWTError("missing sub claim")
    except JWTError as e:
        logger.warning("auth_user_jwt_error %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    if user.role == UserRole.org_admin and user.organization_id is not None:
        org_result = await db.execute(
            select(Organization).where(Organization.id == user.organization_id)
        )
        org = org_result.scalar_one_or_none()
        if org is None or not org.is_approved:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your organization is pending approval. You will be able to login once approved by the Medora administration.",
            )

    return user


async def get_current_patient(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Patient:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate patient credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        patient_id: str = payload.get("sub")
        role: str = payload.get("role")
        if patient_id is None or role != "patient":
            logger.warning(
                "auth_patient_invalid_claims sub=%s role=%s", patient_id, role
            )
            raise exc
    except JWTError as e:
        logger.warning("auth_patient_jwt_error %s", str(e))
        raise exc

    try:
        patient_uuid = uuid.UUID(patient_id)
    except ValueError:
        logger.warning("auth_patient_bad_uuid sub=%s", patient_id)
        raise exc

    result = await db.execute(select(Patient).where(Patient.id == patient_uuid))
    patient = result.scalar_one_or_none()

    if patient is None or not patient.is_active:
        logger.warning("auth_patient_not_found_or_inactive patient_id=%s", patient_id)
        raise exc

    return patient


async def get_current_doctor(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Doctor:
    """
    Dependency for authenticated doctor endpoints.

    Validates that the JWT belongs to a user with role='doctor' and that the
    linked Doctor record exists.  Use alongside get_current_user when you also
    need the User object in the same endpoint — FastAPI caches dependencies
    within a request so get_current_user is called only once.
    """
    if current_user.role != UserRole.doctor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action",
        )

    result = await db.execute(
        select(Doctor).where(Doctor.user_id == current_user.id)
    )
    doctor = result.scalar_one_or_none()

    if doctor is None or not doctor.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found",
        )

    return doctor


def require_role(required_role: "UserRole | list[UserRole]"):
    """
    Dependency factory: accepts a single role or a list of allowed roles.

    Usage:
        Depends(require_role(UserRole.org_admin))
        Depends(require_role([UserRole.org_admin, UserRole.doctor]))
    """
    allowed = required_role if isinstance(required_role, list) else [required_role]

    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed:
            allowed_names = ", ".join(r.value for r in allowed)
            logger.warning(
                "auth_role_denied user_id=%s user_role=%s required=%s",
                current_user.id,
                current_user.role,
                allowed_names,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {allowed_names}",
            )
        return current_user

    return dependency
