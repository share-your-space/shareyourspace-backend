from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, and_

from app.models.connection import Connection
from app.schemas.connection import ConnectionCreate
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

async def create_connection(db: AsyncSession, *, requester_id: int, obj_in: ConnectionCreate) -> Connection:
    """Create a new connection request."""
    # Check if an inverse connection already exists (recipient requested sender)
    # Or if a connection (pending or accepted) already exists
    existing_connection = await db.execute(
        select(Connection).filter(
            (
                (Connection.requester_id == requester_id) & (Connection.recipient_id == obj_in.recipient_id)
            ) |
            (
                (Connection.requester_id == obj_in.recipient_id) & (Connection.recipient_id == requester_id)
            )
        )
    )
    existing = existing_connection.scalars().first()

    if existing:
        # Handle cases: Already connected, request already pending, inverse request pending
        logger.warning(f"Attempt to create duplicate connection between {requester_id} and {obj_in.recipient_id}. Status: {existing.status}")
        # Optionally raise error or return existing connection?
        # For now, let's return the existing one
        return existing 

    db_connection = Connection(
        requester_id=requester_id,
        recipient_id=obj_in.recipient_id,
        status='pending' # Initial status
    )
    db.add(db_connection)
    await db.commit()
    await db.refresh(db_connection)
    logger.info(f"Created connection request from {requester_id} to {obj_in.recipient_id}")
    return db_connection

async def get_connection_by_id(db: AsyncSession, *, connection_id: int) -> Optional[Connection]:
    """Get a connection by its ID."""
    result = await db.execute(select(Connection).filter(Connection.id == connection_id))
    return result.scalars().first()

async def update_connection_status(db: AsyncSession, *, connection: Connection, status: str) -> Connection:
    """Update the status of a connection."""
    allowed_statuses = ['accepted', 'declined', 'blocked'] # Define valid statuses
    if status not in allowed_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {allowed_statuses}")
    
    connection.status = status
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    logger.info(f"Updated connection id {connection.id} status to {status}")
    return connection

async def get_pending_connections_for_user(db: AsyncSession, *, user_id: int) -> List[Connection]:
    """Get pending incoming connection requests for a user."""
    result = await db.execute(
        select(Connection)
        .filter(Connection.recipient_id == user_id, Connection.status == 'pending')
        .order_by(Connection.created_at.desc()) # Show newest first
    )
    return result.scalars().all()

async def get_accepted_connections_for_user(db: AsyncSession, *, user_id: int) -> List[Connection]:
    """Get accepted connections for a user (where they are requester or recipient)."""
    result = await db.execute(
        select(Connection)
        .filter(
            ((Connection.requester_id == user_id) | (Connection.recipient_id == user_id)) &
            (Connection.status == 'accepted')
        )
    )
    return result.scalars().all()

async def get_connection_between_users(db: AsyncSession, *, user1_id: int, user2_id: int) -> Optional[Connection]:
    """Find an existing connection (any status) between two users, regardless of who requested."""
    result = await db.execute(
        select(Connection).filter(
            and_(
                ((Connection.requester_id == user1_id) & (Connection.recipient_id == user2_id)) |
                ((Connection.requester_id == user2_id) & (Connection.recipient_id == user1_id))
            )
        )
    )
    return result.scalars().first() 