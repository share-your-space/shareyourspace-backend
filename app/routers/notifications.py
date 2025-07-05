from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import models, schemas, services
from app.db.session import get_db
from app.dependencies import get_current_active_user

router = APIRouter()

@router.get("/", response_model=List[schemas.notification.Notification])
async def get_user_notifications(
    skip: int = 0,
    limit: int = 20,
    include_read: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Retrieve notifications for the current user."""
    return await services.notification_service.get_notifications(
        db, user_id=current_user.id, skip=skip, limit=limit, include_read=include_read
    )

@router.post("/{notification_id}/read", response_model=schemas.notification.Notification)
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Mark a specific notification as read."""
    return await services.notification_service.mark_as_read(
        db, notification_id=notification_id, user_id=current_user.id
    )

@router.post("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Mark all unread notifications for the current user as read."""
    count = await services.notification_service.mark_all_as_read(db, user_id=current_user.id)
    return {"message": f"Marked {count} notifications as read."} 