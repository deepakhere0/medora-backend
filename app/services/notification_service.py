from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User


async def push_notification(
    db: AsyncSession,
    *,
    org_id: UUID,
    title: str,
    message: str,
    type: str = "info",
    recipient_user_id: UUID | None = None,
    recipient_patient_id: UUID | None = None,
    related_entity_type: str | None = None,
    related_entity_id: UUID | None = None,
) -> None:
    """Add a Notification to the session. Caller must commit."""
    db.add(Notification(
        organization_id=org_id,
        title=title,
        message=message,
        type=type,
        is_read=False,
        recipient_user_id=recipient_user_id,
        recipient_patient_id=recipient_patient_id,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    ))


async def get_unread_count(db: AsyncSession, user: User) -> int:
    result = await db.execute(
        select(func.count(Notification.id)).where(
            and_(
                Notification.recipient_user_id == user.id,
                Notification.is_read.is_(False),
            )
        )
    )
    return result.scalar_one() or 0


async def list_notifications(
    db: AsyncSession,
    user: User,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Notification], int]:
    where = Notification.recipient_user_id == user.id

    total_result = await db.execute(
        select(func.count(Notification.id)).where(where)
    )
    total: int = total_result.scalar_one() or 0

    rows_result = await db.execute(
        select(Notification)
        .where(where)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return rows_result.scalars().all(), total


async def mark_read(
    db: AsyncSession,
    user: User,
    notification_id: UUID,
) -> Notification | None:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if notif and not notif.is_read:
        notif.is_read = True
        await db.commit()
        await db.refresh(notif)
    return notif


async def mark_all_read(db: AsyncSession, user: User) -> int:
    result = await db.execute(
        select(Notification).where(
            Notification.recipient_user_id == user.id,
            Notification.is_read.is_(False),
        )
    )
    notifications = result.scalars().all()
    for n in notifications:
        n.is_read = True
    if notifications:
        await db.commit()
    return len(notifications)
