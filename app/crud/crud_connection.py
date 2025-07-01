from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, and_, or_, delete
from sqlalchemy.orm import selectinload, joinedload

from app import models # Import models at the top level
from app.models.connection import ConnectionStatus # Import the enum
from app.models.user import User
from app.models.profile import UserProfile # Import UserProfile
from app.schemas.connection import ConnectionCreate, ConnectionStatusCheck # Import the necessary schema
from typing import List, Optional, Dict
import logging
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Helper to transform User ORM object to UserReference-like dict for schema compatibility
# This is a placeholder for actual GCS signed URL generation logic for profile_picture_signed_url
# In a real app, you might have a utility function or service for this.
def _prepare_user_reference_data(user_orm: User) -> Dict:
    if not user_orm:
        return {
            "user_id": 0, # Should not happen if data is clean
            "full_name": "Unknown User",
            "title": None,
            "profile_picture_signed_url": None
        }
    return {
        "user_id": user_orm.id,
        "full_name": user_orm.full_name,
        "title": user_orm.profile.title if user_orm.profile else None,
        # Placeholder: In a real app, generate signed URL if profile_picture_url is a GCS path
        # For now, assuming it's directly usable or will be handled by a separate utility.
        "profile_picture_signed_url": user_orm.profile.profile_picture_url if user_orm.profile else None
    }

async def get_connection_by_id(db: AsyncSession, connection_id: int) -> Optional[models.Connection]:
    logger.debug(f"Attempting to fetch connection by ID: {connection_id} with eager loading")
    result = await db.execute(
        select(models.Connection)
        .options(
            selectinload(models.Connection.requester).options(
                selectinload(User.profile)
            ),
            selectinload(models.Connection.recipient).options(
                selectinload(User.profile)
            )
        )
        .filter(models.Connection.id == connection_id)
    )
    connection = result.scalars().first()
    if connection:
        logger.debug(f"Found connection {connection.id}. Requester loaded: {hasattr(connection.requester, 'id')}, Recipient loaded: {hasattr(connection.recipient, 'id')}")
        if connection.requester and hasattr(connection.requester, 'profile'): # Check if profile was loaded
             logger.debug(f"Requester profile: {connection.requester.profile}")
        if connection.recipient and hasattr(connection.recipient, 'profile'): # Check if profile was loaded
             logger.debug(f"Recipient profile: {connection.recipient.profile}")
    else:
        logger.debug(f"No connection found for ID: {connection_id}")
    return connection

async def create_connection(db: AsyncSession, *, obj_in: ConnectionCreate, requester_id: int) -> models.Connection:
    logger.info(f"User {requester_id} attempting to create connection with {obj_in.recipient_id}")
    # Check if users are the same
    if requester_id == obj_in.recipient_id:
        logger.warning(f"Connection attempt from user {requester_id} to themselves failed.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot create a connection with yourself.")

    existing_connection = await get_connection_between_users(db, user1_id=requester_id, user2_id=obj_in.recipient_id)
    if existing_connection:
        if existing_connection.status == ConnectionStatus.ACCEPTED:
            logger.warning(f"Connection attempt between {requester_id} and {obj_in.recipient_id} failed: Already accepted (ID: {existing_connection.id})")
            # Return existing accepted connection instead of erroring, or handle as per product req.
            # For now, let's consider it an idempotent operation if already accepted.
            # return existing_connection # Or raise HTTPException as before
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection already exists and is accepted.")
        if existing_connection.status == ConnectionStatus.PENDING:
            if existing_connection.requester_id == requester_id:
                logger.warning(f"Connection attempt between {requester_id} and {obj_in.recipient_id} failed: Already pending from requester (ID: {existing_connection.id})")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection request already pending from you.")
            else: # Pending from the other side
                logger.info(f"Existing pending connection from {obj_in.recipient_id} to {requester_id}. Auto-accepting.")
                # Auto-accept the existing request
                return await update_connection_status(db, connection=existing_connection, status=ConnectionStatus.ACCEPTED)
        if existing_connection.status == ConnectionStatus.DECLINED:
            logger.info(f"Re-initiating connection after previous decline between {requester_id} and {obj_in.recipient_id}. ID: {existing_connection.id}")
            # Allow re-request after decline by updating status to pending and swapping requester/recipient if needed.
            # This simplifies to just creating a new one if the old one is just deleted or marked as "superseded"
            # For now, let's assume a new request is fine, or update existing declined one:
            existing_connection.status = ConnectionStatus.PENDING
            existing_connection.requester_id = requester_id # Ensure current user is requester
            existing_connection.recipient_id = obj_in.recipient_id
            db.add(existing_connection)
            await db.commit()
            loaded_connection = await get_connection_by_id(db, connection_id=existing_connection.id)
            if not loaded_connection: raise HTTPException(status_code=500, detail="Failed to update connection.")
            return loaded_connection
        
        logger.warning(f"Unhandled existing connection status: {existing_connection.status} between {requester_id} and {obj_in.recipient_id}. ID: {existing_connection.id}")
        # Fallthrough to create new or raise specific error for other statuses if needed

    db_connection = models.Connection(
        requester_id=requester_id,
        recipient_id=obj_in.recipient_id,
        status=ConnectionStatus.PENDING
    )
    db.add(db_connection)
    await db.commit()
    loaded_connection = await get_connection_by_id(db, connection_id=db_connection.id)
    if not loaded_connection:
        logger.error(f"Critical error: Failed to re-fetch connection {db_connection.id} immediately after creation.")
        raise HTTPException(status_code=500, detail="Could not retrieve connection after creation.")

    logger.info(f"Successfully created connection id {loaded_connection.id} from user {requester_id} to user {obj_in.recipient_id}")
    return loaded_connection

async def update_connection_status(
    db: AsyncSession, 
    *, 
    connection: models.Connection, 
    status: ConnectionStatus
) -> models.Connection:
    logger.info(f"Attempting to update connection ID {connection.id} to status {status.value}")
    connection.status = status
    db.add(connection)
    await db.commit()
    updated_connection = await get_connection_by_id(db, connection_id=connection.id)
    if not updated_connection:
        logger.error(f"Critical error: Failed to re-fetch connection {connection.id} after status update to {status.value}.")
        raise HTTPException(status_code=500, detail="Could not retrieve connection after update.")
    logger.info(f"Successfully updated connection id {updated_connection.id} to status {status.value}")
    return updated_connection

async def get_pending_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    logger.debug(f"Fetching pending connections for user ID: {user_id} (as recipient)")
    query = select(models.Connection).options(
        selectinload(models.Connection.requester).options(selectinload(User.profile)),
        selectinload(models.Connection.recipient).options(selectinload(User.profile))
    ).filter(models.Connection.recipient_id == user_id, models.Connection.status == ConnectionStatus.PENDING)
    result = await db.execute(query)
    connections = result.scalars().all()
    logger.debug(f"Found {len(connections)} pending connections for user ID: {user_id}")
    return connections

# Renamed from get_pending_outgoing_connections_for_user for clarity with frontend
async def get_sent_pending_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    logger.debug(f"Fetching sent pending connections for user ID: {user_id} (as requester)")
    query = select(models.Connection).options(
        selectinload(models.Connection.requester).options(selectinload(User.profile)),
        selectinload(models.Connection.recipient).options(selectinload(User.profile))
    ).filter(models.Connection.requester_id == user_id, models.Connection.status == ConnectionStatus.PENDING)
    result = await db.execute(query)
    connections = result.scalars().all()
    logger.debug(f"Found {len(connections)} sent pending connections for user ID: {user_id}")
    return connections

async def get_accepted_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    logger.debug(f"Fetching accepted connections for user ID: {user_id}")
    query = select(models.Connection).options(
        selectinload(models.Connection.requester).options(selectinload(User.profile)),
        selectinload(models.Connection.recipient).options(selectinload(User.profile))
    ).filter(
        ((models.Connection.requester_id == user_id) | (models.Connection.recipient_id == user_id)),
        models.Connection.status == ConnectionStatus.ACCEPTED
    )
    result = await db.execute(query)
    connections = result.scalars().all()
    logger.debug(f"Found {len(connections)} accepted connections for user ID: {user_id}")
    return connections

async def get_connection_between_users(db: AsyncSession, *, user1_id: int, user2_id: int) -> models.Connection | None:
    logger.debug(f"Fetching connection between user ID: {user1_id} and user ID: {user2_id}")
    query = select(models.Connection).options(
        selectinload(models.Connection.requester).options(selectinload(User.profile)),
        selectinload(models.Connection.recipient).options(selectinload(User.profile))
    ).filter(
        ((models.Connection.requester_id == user1_id) & (models.Connection.recipient_id == user2_id)) |
        ((models.Connection.requester_id == user2_id) & (models.Connection.recipient_id == user1_id))
    ).order_by(models.Connection.created_at.desc())
    result = await db.execute(query)
    connection = result.scalars().first()
    if connection:
        logger.debug(f"Found connection ID {connection.id} between user {user1_id} and {user2_id} with status {connection.status.value}")
    else:
        logger.debug(f"No connection found between user {user1_id} and {user2_id}")
    return connection

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

async def get_declined_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    # This might include connections declined by the user or by others for requests made by the user.
    logger.debug(f"Fetching declined connections involving user ID: {user_id}")
    query = select(models.Connection).options(
        selectinload(models.Connection.requester).options(selectinload(User.profile), selectinload(User.managed_space), selectinload(User.space)),
        selectinload(models.Connection.recipient).options(selectinload(User.profile), selectinload(User.managed_space), selectinload(User.space))
    ).filter(
        ((models.Connection.requester_id == user_id) | (models.Connection.recipient_id == user_id)),
        models.Connection.status == ConnectionStatus.DECLINED
    )
    result = await db.execute(query)
    connections = result.scalars().all()
    logger.debug(f"Found {len(connections)} declined connections involving user ID: {user_id}")
    return connections 

# DELETE connection function
async def delete_connection_by_id_and_user(db: AsyncSession, *, connection_id: int, current_user_id: int) -> bool:
    logger.info(f"User {current_user_id} attempting to delete connection ID {connection_id}")
    connection = await get_connection_by_id(db, connection_id=connection_id) # Fetches with eager loads

    if not connection:
        logger.warning(f"Connection ID {connection_id} not found for deletion attempt by user {current_user_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found.")

    # Authorization check
    is_requester = connection.requester_id == current_user_id
    is_recipient = connection.recipient_id == current_user_id

    can_delete = False
    if connection.status == ConnectionStatus.PENDING and is_requester:
        can_delete = True # User can cancel their own pending request
        logger.info(f"Authorizing deletion of PENDING connection ID {connection_id} by requester {current_user_id}.")
    elif connection.status == ConnectionStatus.ACCEPTED and (is_requester or is_recipient):
        can_delete = True # Either party can remove an accepted connection
        logger.info(f"Authorizing deletion of ACCEPTED connection ID {connection_id} by user {current_user_id}.")
    # Add other conditions if e.g. admin can delete, or if declined connections can be cleared by specific users.
    
    if not can_delete:
        logger.warning(f"User {current_user_id} not authorized to delete connection ID {connection_id} with status {connection.status.value}.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not authorized to perform this action on this connection.")

    # Perform deletion
    # await db.delete(connection) # This is correct syntax for ORM object
    stmt = delete(models.Connection).where(models.Connection.id == connection_id)
    await db.execute(stmt)
    await db.commit()
    logger.info(f"Successfully deleted connection ID {connection_id} by user {current_user_id}.")
    return True

async def create_accepted_connection(db: AsyncSession, *, user_one_id: int, user_two_id: int) -> Optional[models.Connection]:
    """Creates a direct 'accepted' connection between two users if one doesn't already exist."""
    if user_one_id == user_two_id:
        logger.warning(f"Attempt to create self-connection for user {user_one_id} was blocked.")
        return None

    logger.info(f"Attempting to create accepted connection between user {user_one_id} and {user_two_id}")
    
    existing_connection = await get_connection_between_users(db, user1_id=user_one_id, user2_id=user_two_id)

    if existing_connection:
        logger.info(f"Connection between users {user_one_id} and {user_two_id} already exists with status {existing_connection.status}.")
        # If it's not accepted for some reason, we can update it.
        if existing_connection.status != ConnectionStatus.ACCEPTED:
            logger.info(f"Updating existing connection {existing_connection.id} to ACCEPTED.")
            return await update_connection_status(db, connection=existing_connection, status=ConnectionStatus.ACCEPTED)
        return existing_connection

    logger.info(f"No existing connection found. Creating a new accepted connection.")
    db_connection = models.Connection(
        requester_id=user_one_id,
        recipient_id=user_two_id,
        status=ConnectionStatus.ACCEPTED
    )
    db.add(db_connection)
    await db.flush()
    
    # Eagerly load the created connection to return it with relationships populated
    loaded_connection = await get_connection_by_id(db, connection_id=db_connection.id)
    if not loaded_connection:
        logger.error(f"Critical error: Failed to re-fetch accepted connection {db_connection.id} immediately after creation.")
        # This case should ideally not be reached if the DB is consistent.
        raise HTTPException(status_code=500, detail="Could not retrieve connection after creation.")

    logger.info(f"Successfully created accepted connection id {loaded_connection.id} between user {user_one_id} and user {user_two_id}")
    return loaded_connection

# Note: The _prepare_user_reference_data helper is not directly used here as Pydantic will handle serialization
# from ORM models (User with User.profile) to the UserReference schema based on field names, assuming
# User.id maps to UserReference.user_id, User.full_name to UserReference.full_name etc.
# The main challenge is `profile_picture_signed_url`. If `User.profile.profile_picture_url` is just a path,
# the transformation to a signed URL would typically happen in the router/response model layer, not deep in CRUD.
# For simplicity, the current Pydantic UserReference schema expects `profile_picture_signed_url` and will try to map it.
# If User.profile.profile_picture_url exists, it will be mapped if the field name in UserProfileSchema matches.
# The selectinload ensures `requester.profile` and `recipient.profile` are available.

# Final check for selectinload in list functions:
# get_pending_connections_for_user - OK
# get_sent_pending_connections_for_user - OK
# get_accepted_connections_for_user - OK
# These should correctly populate the User objects and their profiles for Pydantic serialization. 