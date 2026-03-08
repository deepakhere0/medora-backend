from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginResponse
from app.schemas.user import UserCreate, UserResponse, LoginRequest
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
