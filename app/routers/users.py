from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserProfileResponse

router = APIRouter(prefix="/users", tags=["Users"])


class UserMeUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.put("/me", response_model=UserProfileResponse, status_code=status.HTTP_200_OK)
async def update_me(
    payload: UserMeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.name is not None:
        current_user.name = payload.name
    if payload.phone is not None:
        current_user.phone = payload.phone
    await db.commit()
    await db.refresh(current_user)
    return current_user
