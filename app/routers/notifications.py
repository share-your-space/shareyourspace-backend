from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging

from app import models, crud
from app.schemas.notification import Notification # Assuming schema exists
from app.db.session import get_db
from app.security import get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=List[Notification])
async def get_user_notifications(
    skip: int = 0,
    limit: int = 20, # Default to fewer items for API response
    include_read: bool = False, 
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Retrieve notifications for the current user."""
    notifications = await crud.crud_notification.get_notifications_for_user(
        db=db, user_id=current_user.id, skip=skip, limit=limit, include_read=include_read
    )
    return notifications

@router.post("/{notification_id}/read", response_model=Notification)
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Mark a specific notification as read."""
    notification = await crud.crud_notification.get_notification_by_id(db=db, notification_id=notification_id)

    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    # Ensure the notification belongs to the current user
    if notification.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to mark this notification as read.")

    updated_notification = await crud.crud_notification.mark_notification_as_read(db=db, notification=notification)
    return updated_notification

@router.post("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Mark all unread notifications for the current user as read."""
    count = await crud.crud_notification.mark_all_notifications_as_read(db=db, user_id=current_user.id)
    return {"message": f"Marked {count} notifications as read."} 