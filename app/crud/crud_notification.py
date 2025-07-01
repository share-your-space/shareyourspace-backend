from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
import logging

from app.models.notification import Notification
from app.models.enums import NotificationType, UserRole
from app.models.user import User

logger = logging.getLogger(__name__)

async def create_notification(
    db: AsyncSession, 
    *, 
    user_id: int, 
    type: NotificationType,
    message: str, 
    sender_id: Optional[int] = None,
    related_entity_id: Optional[int] = None,
    reference: Optional[str] = None,
    link: Optional[str] = None
) -> Notification:
    """Create a new notification."""
    db_notification = Notification(
        user_id=user_id,
        type=type.value,
        message=message,
        sender_id=sender_id,
        related_entity_id=related_entity_id,
        reference=reference,
        link=link,
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
    query = select(Notification).options(
        selectinload(Notification.sender).selectinload(User.profile),
        selectinload(Notification.user).selectinload(User.profile)
    ).filter(Notification.user_id == user_id)
    if not include_read:
        query = query.filter(Notification.is_read == False)
    
    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_notification_by_id(db: AsyncSession, *, notification_id: int, options: Optional[List] = None) -> Optional[Notification]:
    """Get a notification by its ID."""
    query = select(Notification).filter(Notification.id == notification_id)
    if options:
        query = query.options(*options)
    result = await db.execute(query)
    return result.scalars().first()

async def get_notification_by_related_entity(
    db: AsyncSession, 
    *, 
    user_id: int, 
    type: NotificationType,
    related_entity_id: int
) -> Optional[Notification]:
    """Get a specific notification based on user, type, and related entity ID."""
    query = select(Notification).filter(
        Notification.user_id == user_id,
        Notification.type == type.value,
        Notification.related_entity_id == related_entity_id,
        Notification.is_read == False
    ).order_by(Notification.created_at.desc())
    
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

async def mark_notification_as_actioned(db: AsyncSession, *, notification: Notification) -> Notification:
    """Mark a specific notification as actioned and also as read."""
    if not notification.is_actioned:
        notification.is_actioned = True
        notification.is_read = True # Actioning a request implies it has been read
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        logger.info(f"Marked notification id {notification.id} as actioned for user {notification.user_id}")
    return notification

async def mark_all_notifications_as_read(db: AsyncSession, *, user_id: int) -> int:
    """Mark all unread notifications for a user as read. Returns count of marked items."""
    stmt = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == False)
        .values(is_read=True)
    )
    result = await db.execute(stmt)
    await db.commit()
    count = result.rowcount
    logger.info(f"Marked {count} notifications as read for user {user_id}")
    return count

async def mark_notifications_as_read_by_ref(
    db: AsyncSession, 
    *, 
    user_id: int, 
    reference: str,
    notification_type: NotificationType
) -> int:
    """Mark all unread notifications for a user with a specific reference and type as read."""
    stmt = (
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.reference == reference,
            Notification.type == notification_type.value,
            Notification.is_read == False
        )
        .values(is_read=True)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    await db.commit()
    count = result.rowcount
    if count > 0:
        logger.info(f"Marked {count} notifications of type '{notification_type.value}' as read for user {user_id} with reference '{reference}'")
    return count

async def create_notification_for_org_admins(
    db: AsyncSession,
    *,
    org_id: int,
    org_type: str,
    message: str,
    notification_type: NotificationType = NotificationType.INVITATION_REQUEST,
    related_entity_id: Optional[int] = None,
    link: Optional[str] = None
):
    """
    Finds admins for a given organization and creates a notification for each one.
    This function does NOT commit the session.
    """
    logger.info(f"Queueing join request notification for {org_type} ID {org_id}")
    
    admin_role = UserRole.CORP_ADMIN if org_type == 'company' else UserRole.STARTUP_ADMIN

    stmt = select(User).where(
        and_(
            User.role == admin_role,
            User.company_id == org_id if org_type == 'company' else User.startup_id == org_id
        )
    )
    result = await db.execute(stmt)
    admin_users = result.scalars().all()

    if not admin_users:
        logger.warning(f"No admin found for {org_type} ID {org_id} to send join request notification.")
        return

    notifications_created = 0
    for admin in admin_users:
        db_notification = Notification(
            user_id=admin.id,
            type=notification_type.value,
            message=message,
            related_entity_id=related_entity_id,
            link=link
        )
        db.add(db_notification)
        notifications_created += 1
    
    logger.info(f"Added {notifications_created} notifications to session for {org_type} ID {org_id}. Awaiting commit from router.")

async def get_notifications_by_type_for_user(
    db: AsyncSession,
    user_id: int,
    notification_types: List[NotificationType],
    is_read: bool | None = None,
    skip: int = 0,
    limit: int = 100,
    options: Optional[List] = None
) -> List[Notification]:
    stmt = (
        select(Notification)
        .options(
            selectinload(Notification.sender).selectinload(User.profile),
            selectinload(Notification.user).selectinload(User.profile)
        )
        .where(
            Notification.user_id == user_id,
            Notification.type.in_([nt.value for nt in notification_types])
        )
    )
    if is_read is not None:
        stmt = stmt.where(Notification.is_read == is_read)
    
    if options:
        stmt = stmt.options(*options)
    
    stmt = stmt.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

async def mark_notification_as_read_by_id(db: AsyncSession, notification_id: int) -> Optional[Notification]:
    stmt = (
        update(Notification)
        .where(Notification.id == notification_id)
        .values(is_read=True)
        .returning(Notification)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one_or_none() 