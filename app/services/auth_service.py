from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


async def register_user(db: AsyncSession, user_create: UserCreate) -> User:
    result = await db.execute(select(User).where(User.email == user_create.email))
    if result.scalar_one_or_none() is not None:
        raise ValueError("Email already registered")

    user = User(
        email=user_create.email,
        hashed_password=hash_password(user_create.password),
        role=user_create.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
