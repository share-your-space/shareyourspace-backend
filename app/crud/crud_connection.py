from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, and_, or_
from sqlalchemy.orm import selectinload

from app import models # Import models at the top level
from app.models.connection import ConnectionStatus # Import the enum
from app.models.user import User
from app.schemas.connection import ConnectionCreate, ConnectionStatusCheck # Import the necessary schema
from typing import List, Optional, Dict
import logging
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

async def create_connection(db: AsyncSession, *, requester_id: int, obj_in: ConnectionCreate) -> models.Connection:
    """Create a new connection request or resend if previously declined."""
    # Check if any connection (pending, accepted, declined, blocked) exists between the two users
    existing_connection = await db.execute(
        select(models.Connection).options(selectinload(models.Connection.requester), selectinload(models.Connection.recipient))
        .filter(
            or_(
                and_(models.Connection.requester_id == requester_id, models.Connection.recipient_id == obj_in.recipient_id),
                and_(models.Connection.requester_id == obj_in.recipient_id, models.Connection.recipient_id == requester_id)
            )
        )
    )
    existing = existing_connection.scalars().first()

    if existing:
        # If already pending or accepted, just return the existing record
        if existing.status in [ConnectionStatus.PENDING, ConnectionStatus.ACCEPTED]:
            logger.warning(f"Attempt to create duplicate connection between {requester_id} and {obj_in.recipient_id}. Status: {existing.status}. Returning existing.")
            return existing
        # If previously declined, allow resending by updating status to pending
        elif existing.status == ConnectionStatus.DECLINED:
            logger.info(f"Re-sending connection request between {requester_id} and {obj_in.recipient_id} (previously declined).")
            # Ensure the requester is the one initiating this new request
            if existing.requester_id != requester_id:
                # If the other person declined the current user before, update the direction
                existing.requester_id = requester_id
                existing.recipient_id = obj_in.recipient_id
            existing.status = ConnectionStatus.PENDING 
            # Update timestamp? Let's rely on updated_at for now.
            # existing.created_at = func.now() # Or keep original?
            db.add(existing)
            await db.commit()
            await db.refresh(existing, attribute_names=['requester', 'recipient'])
            return existing
        # If blocked, prevent any action (optional: raise specific error?)
        elif existing.status == ConnectionStatus.BLOCKED:
            logger.warning(f"Attempt to create connection between {requester_id} and {obj_in.recipient_id}, but connection is BLOCKED.")
            # Raise HTTPException or just return the blocked connection?
            # Raising error is probably better feedback
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot send connection request; connection is blocked."
            )
        else: # Should not happen
            logger.error(f"Existing connection found with unexpected status: {existing.status}")
            return existing # Fallback

    # If no existing connection, create a new one
    logger.info(f"Creating new connection request from {requester_id} to {obj_in.recipient_id}")
    db_connection = models.Connection(
        requester_id=requester_id,
        recipient_id=obj_in.recipient_id,
        status=ConnectionStatus.PENDING # Initial status
    )
    db.add(db_connection)
    await db.commit()
    await db.refresh(db_connection, attribute_names=['requester', 'recipient'])
    return db_connection

async def get_connection_by_id(db: AsyncSession, *, connection_id: int) -> Optional[models.Connection]:
    """Get a connection by its ID."""
    result = await db.execute(
        select(models.Connection)
        .options(selectinload(models.Connection.requester), selectinload(models.Connection.recipient))
        .filter(models.Connection.id == connection_id)
    )
    return result.scalars().first()

async def update_connection_status(db: AsyncSession, *, connection: models.Connection, status: str) -> models.Connection:
    """Update the status of a connection."""
    allowed_statuses = ['accepted', 'declined', 'blocked'] # Define valid statuses
    if status not in allowed_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {allowed_statuses}")
    
    connection.status = status
    db.add(connection)
    await db.commit()
    await db.refresh(connection, attribute_names=['requester', 'recipient'])
    logger.info(f"Updated connection id {connection.id} status to {status}")
    return connection

async def get_pending_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    """Get pending incoming connection requests for a user."""
    result = await db.execute(
        select(models.Connection)
        .options(selectinload(models.Connection.requester), selectinload(models.Connection.recipient))
        .filter(models.Connection.recipient_id == user_id, models.Connection.status == 'pending')
        .order_by(models.Connection.created_at.desc()) # Show newest first
    )
    return result.scalars().all()

async def get_accepted_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    """Get accepted connections for a user (where they are requester or recipient)."""
    result = await db.execute(
        select(models.Connection)
        .options(selectinload(models.Connection.requester), selectinload(models.Connection.recipient))
        .filter(
            or_(models.Connection.requester_id == user_id, models.Connection.recipient_id == user_id),
            models.Connection.status == 'accepted'
        )
        .order_by(models.Connection.updated_at.desc())
    )
    return result.scalars().all()

async def get_connection_between_users(db: AsyncSession, *, user1_id: int, user2_id: int) -> models.Connection | None:
    """Check if a connection exists between two specific users, regardless of direction."""
    query = select(models.Connection).options(
        selectinload(models.Connection.requester),
        selectinload(models.Connection.recipient)
    ).where(
        or_(
            and_(models.Connection.requester_id == user1_id, models.Connection.recipient_id == user2_id),
            and_(models.Connection.requester_id == user2_id, models.Connection.recipient_id == user1_id)
        )
    )
    result = await db.execute(query)
    return result.scalars().first()

async def get_connections_status_for_users(db: AsyncSession, *, current_user_id: int, other_user_ids: List[int]) -> Dict[int, ConnectionStatusCheck]:
    """Get the connection status between the current user and a list of other users."""
    if not other_user_ids:
        return {}

    # Fetch all relevant connections in one query
    # Use models.Connection
    query = select(models.Connection).where(
        or_(
            # Current user is requester, other user is recipient
            and_(models.Connection.requester_id == current_user_id, models.Connection.recipient_id.in_(other_user_ids)),
            # Other user is requester, current user is recipient
            and_(models.Connection.requester_id.in_(other_user_ids), models.Connection.recipient_id == current_user_id)
        )
    )
    result = await db.execute(query)
    connections = result.scalars().all()

    # Process connections into a dictionary keyed by other_user_id
    # Use the correct type hint
    status_map: Dict[int, ConnectionStatusCheck] = {}
    for conn in connections:
        other_id = conn.recipient_id if conn.requester_id == current_user_id else conn.requester_id
        
        status_detail = "unknown"
        # Use the enum for comparison
        if conn.status == ConnectionStatus.ACCEPTED:
            status_detail = 'connected'
        elif conn.status == ConnectionStatus.PENDING:
            if conn.requester_id == current_user_id:
                status_detail = 'pending_from_me'
            else:
                status_detail = 'pending_from_them'
        elif conn.status == ConnectionStatus.DECLINED:
            status_detail = 'declined' # Or maybe treat declined as not_connected?
        elif conn.status == ConnectionStatus.BLOCKED:
            status_detail = 'blocked' # Handle if blocking is implemented

        # Assign the correct schema object
        status_map[other_id] = ConnectionStatusCheck(status=status_detail, connection_id=conn.id)

    # Fill in 'not_connected' for users without an existing connection record
    for user_id in other_user_ids:
        if user_id not in status_map:
            # Assign the correct schema object
            status_map[user_id] = ConnectionStatusCheck(status='not_connected')

    return status_map 

async def get_pending_outgoing_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    """Get pending outgoing connection requests made by a user."""
    query = select(models.Connection).options(
        selectinload(models.Connection.requester).selectinload(models.User.profile),
        selectinload(models.Connection.recipient).selectinload(models.User.profile)
    ).where(
        models.Connection.requester_id == user_id,
        models.Connection.status == ConnectionStatus.PENDING
    ).order_by(models.Connection.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()

async def get_declined_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    """Get connections involving the user that have been declined (either by them or by the other party)."""
    query = select(models.Connection).options(
        selectinload(models.Connection.requester).selectinload(models.User.profile),
        selectinload(models.Connection.recipient).selectinload(models.User.profile)
    ).where(
        or_(models.Connection.requester_id == user_id, models.Connection.recipient_id == user_id),
        models.Connection.status == ConnectionStatus.DECLINED
    ).order_by(models.Connection.updated_at.desc())
    result = await db.execute(query)
    return result.scalars().all() 