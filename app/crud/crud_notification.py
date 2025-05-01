from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from typing import List, Optional
import logging

from app.models.notification import Notification

logger = logging.getLogger(__name__)

async def create_notification(
    db: AsyncSession, 
    *, 
    user_id: int, 
    type: str, 
    message: str, 
    related_entity_id: Optional[int] = None
) -> Notification:
    """Create a new notification."""
    db_notification = Notification(
        user_id=user_id,
        type=type,
        message=message,
        related_entity_id=related_entity_id,
        is_read=False
    )
    db.add(db_notification)
    await db.commit()
    await db.refresh(db_notification)
    logger.info(f"Created notification id {db_notification.id} for user {user_id}")
    return db_notification

async def get_notifications_for_user(
    db: AsyncSession, 
    *, 
    user_id: int, 
    skip: int = 0, 
    limit: int = 100, 
    include_read: bool = False
) -> List[Notification]:
    """Get notifications for a user, optionally filtering out read ones."""
    query = select(Notification).filter(Notification.user_id == user_id)
    if not include_read:
        query = query.filter(Notification.is_read == False)
    
    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_notification_by_id(db: AsyncSession, *, notification_id: int) -> Optional[Notification]:
    """Get a notification by its ID."""
    result = await db.execute(select(Notification).filter(Notification.id == notification_id))
    return result.scalars().first()

async def get_notification_by_related_entity(
    db: AsyncSession, 
    *, 
    user_id: int, 
    type: str, 
    related_entity_id: int
) -> Optional[Notification]:
    """Get a specific notification based on user, type, and related entity ID."""
    query = select(Notification).filter(
        Notification.user_id == user_id,
        Notification.type == type,
        Notification.related_entity_id == related_entity_id,
        Notification.is_read == False # Usually want the unread one
    ).order_by(Notification.created_at.desc()) # Get the latest if multiple somehow exist
    
    result = await db.execute(query)
    return result.scalars().first()

async def mark_notification_as_read(db: AsyncSession, *, notification: Notification) -> Notification:
    """Mark a specific notification as read."""
    if not notification.is_read:
        notification.is_read = True
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        logger.info(f"Marked notification id {notification.id} as read for user {notification.user_id}")
    return notification

async def mark_all_notifications_as_read(db: AsyncSession, *, user_id: int) -> int:
    """Mark all unread notifications for a user as read. Returns count of marked items."""
    stmt = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == False)
        .values(is_read=True)
    )
    result = await db.execute(stmt)
    await db.commit() # Commit the change
    count = result.rowcount
    logger.info(f"Marked {count} notifications as read for user {user_id}")
    return count 