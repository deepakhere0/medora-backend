from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.notification_service import (
    get_unread_count,
    list_notifications,
    mark_all_read,
    mark_read,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    message: str
    type: str
    is_read: bool
    related_entity_type: str | None = None
    related_entity_id: UUID | None = None
    created_at: datetime


class UnreadCountResponse(BaseModel):
    count: int


class NotificationListResponse(BaseModel):
    notifications: list[NotificationItem]
    total: int
    page: int
    limit: int


@router.get(
    "/unread/count",
    response_model=UnreadCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Unread notification count for the bell badge",
)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> UnreadCountResponse:
    count = await get_unread_count(db, current_user)
    return UnreadCountResponse(count=count)


@router.get(
    "",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List notifications for the current doctor",
)
async def list_notifications_endpoint(
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> NotificationListResponse:
    notifications, total = await list_notifications(db, current_user, page=page, limit=limit)
    return NotificationListResponse(
        notifications=[NotificationItem.model_validate(n) for n in notifications],
        total=total,
        page=page,
        limit=limit,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationItem,
    status_code=status.HTTP_200_OK,
    summary="Mark a single notification as read",
)
async def mark_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> NotificationItem:
    notif = await mark_read(db, current_user, notification_id)
    if notif is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return NotificationItem.model_validate(notif)


@router.patch(
    "/read-all",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Mark all notifications as read",
)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.doctor)),
) -> dict:
    count = await mark_all_read(db, current_user)
    return {"marked_read": count}
