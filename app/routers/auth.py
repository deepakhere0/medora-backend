from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginResponse
from app.schemas.user import (
    ChangePasswordRequest,
    UserCreate,
    UserProfileResponse,
    UserProfileUpdate,
    UserResponse,
    LoginRequest,
)
from app.services.auth_service import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await register_user(db, user_create)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return user


@router.post("/login", response_model=LoginResponse)
async def login(
    user_create: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    user = await authenticate_user(db, user_create.email, user_create.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(subject=str(user.id), role=user.role.value)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        organization_id=user.organization_id,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.put("/me", response_model=UserProfileResponse)
async def update_me(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.email is not None and payload.email != current_user.email:
        result = await db.execute(select(User).where(User.email == payload.email))
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use",
            )
        current_user.email = payload.email

    if payload.name is not None:
        current_user.name = payload.name
    if payload.phone is not None:
        current_user.phone = payload.phone

    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"message": "Password updated successfully"}
