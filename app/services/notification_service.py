from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import crud, models, schemas

async def get_notifications(
    db: AsyncSession, *, user_id: int, skip: int, limit: int, include_read: bool
) -> List[models.Notification]:
    return await crud.crud_notification.get_notifications_for_user(
        db, user_id=user_id, skip=skip, limit=limit, include_read=include_read
    )

async def mark_as_read(db: AsyncSession, *, notification_id: int, user_id: int) -> models.Notification:
    notification = await crud.crud_notification.get_notification_by_id(db, notification_id=notification_id)
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    if notification.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
        
    return await crud.crud_notification.mark_notification_as_read(db, notification=notification)

async def mark_all_as_read(db: AsyncSession, *, user_id: int) -> int:
    return await crud.crud_notification.mark_all_notifications_as_read(db, user_id=user_id) 