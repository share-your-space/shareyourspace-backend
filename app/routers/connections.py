from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict
import logging

from app import models, crud
from app.schemas import connection as connection_schemas
from app.crud.crud_connection import (
    create_connection,
    get_connection_by_id,
    update_connection_status,
    get_pending_connections_for_user,
    get_sent_pending_connections_for_user,
    get_accepted_connections_for_user,
    get_connection_between_users,
    get_connections_status_for_users,
    delete_connection_by_id_and_user
)
from app.crud import crud_user, crud_notification
from app.schemas.user import User as UserSchema
from app.db.session import get_db
from app.security import get_current_active_user
from app.utils.email import send_email
from app.schemas.connection import Connection, ConnectionCreate, ConnectionStatusCheck
from app.models.enums import NotificationType, ConnectionStatus

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/", response_model=connection_schemas.Connection, status_code=status.HTTP_201_CREATED)
async def create_connection_request(
    connection_in: connection_schemas.ConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Send a connection request to another user."""
    if current_user.id == connection_in.recipient_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot connect with yourself.")

    # Ensure recipient exists (optional, but good practice)
    recipient = await crud_user.get_user_by_id(db=db, user_id=connection_in.recipient_id)
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient user not found.")

    # TODO: Check if users are in the same space? Or allow cross-space requests?
    # if current_user.space_id != recipient.space_id:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Users must be in the same space to connect.")

    # Call the CRUD function which handles new requests AND re-sending declined ones
    # It returns the connection object (new or updated)
    connection_obj = await create_connection(
        db=db, requester_id=current_user.id, obj_in=connection_in
    )

    # Notification Logic (adjust if auto-accept happens)
    if connection_obj.status == ConnectionStatus.PENDING and connection_obj.requester_id == current_user.id:
        existing_notification = await crud_notification.get_notification_by_related_entity(
            db, 
            user_id=recipient.id, 
            type=NotificationType.CONNECTION_REQUEST,
            related_entity_id=connection_obj.id
        )
        if not existing_notification:
            notification_message = f"{current_user.full_name or current_user.email} wants to connect with you."
            await crud_notification.create_notification(
                db, 
                user_id=recipient.id, 
                type=NotificationType.CONNECTION_REQUEST,
                message=notification_message, 
                related_entity_id=connection_obj.id,
            )
            # Email sending (commented out for now)
    elif connection_obj.status == ConnectionStatus.ACCEPTED and connection_obj.recipient_id == current_user.id:
        # This means current_user just accepted a request by sending a new one (auto-accept)
        # Notify the other user (who was the original requester of the auto-accepted request)
        original_requester = await crud_user.get_user_by_id(db, user_id=connection_obj.requester_id)
        if original_requester:
            notification_message = f"{current_user.full_name or current_user.email} accepted your connection request."
            await crud_notification.create_notification(
                db,
                user_id=original_requester.id,
                type=NotificationType.CONNECTION_ACCEPTED,
                message=notification_message,
                related_entity_id=connection_obj.id,
            )
            # Also mark the original notification for current_user (who was recipient) as read
            original_pending_notification = await crud_notification.get_notification_by_related_entity(
                db,
                user_id=current_user.id,
                type=NotificationType.CONNECTION_REQUEST,
                related_entity_id=connection_obj.id # The ID of the connection they effectively accepted
            )
            if original_pending_notification:
                await crud_notification.mark_notification_as_read(db, notification=original_pending_notification)

    # Re-fetch the connection cleanly before returning to avoid serialization issues
    final_connection = await get_connection_by_id(db=db, connection_id=connection_obj.id)
    if not final_connection:
         # Should not happen, but handle defensively
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found after creation/update.")

    return final_connection

@router.put("/{connection_id}/accept", response_model=connection_schemas.Connection)
async def accept_connection_request(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Accept a pending connection request."""
    # Use the existing get_connection_by_id which already eager loads users
    connection = await get_connection_by_id(db=db, connection_id=connection_id)

    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection request not found.")

    if connection.recipient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to accept this request.")

    if connection.status != ConnectionStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Connection request status is '{connection.status.value}', not PENDING.")

    # Update the status - the CRUD function should commit
    # We pass the existing connection object which already has users loaded
    updated_connection = await update_connection_status(
        db=db, connection=connection, status=ConnectionStatus.ACCEPTED
    )

    # Notification Logic
    requester = await crud_user.get_user_by_id(db, user_id=updated_connection.requester_id) # Fetch requester if not loaded on connection object
    if requester:
        notification_message = f"{current_user.full_name or current_user.email} accepted your connection request."
        await crud_notification.create_notification(
            db, 
            user_id=requester.id, 
            type=NotificationType.CONNECTION_ACCEPTED,
            message=notification_message, 
            related_entity_id=updated_connection.id,
        )
    original_notification = await crud_notification.get_notification_by_related_entity(
        db, user_id=current_user.id, type=NotificationType.CONNECTION_REQUEST, related_entity_id=connection_id)
    if original_notification: await crud_notification.mark_notification_as_read(db=db, notification=original_notification)

    # No need to refresh here, as we re-fetch below
    # await db.refresh(connection)

    # Re-fetch the connection with users eagerly loaded AFTER the update to ensure latest data
    # Use the existing get_connection_by_id function
    final_connection = await get_connection_by_id(db=db, connection_id=connection_id)
    if not final_connection:
         # Should not happen if update succeeded, but handle defensively
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found after update.")

    # Return the Pydantic schema object, not the raw ORM object
    # Pydantic will handle serialization based on the response_model
    return final_connection

@router.put("/{connection_id}/decline", response_model=connection_schemas.Connection)
async def decline_connection_request(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Decline a pending connection request."""
    connection = await get_connection_by_id(db=db, connection_id=connection_id)

    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection request not found.")

    if connection.recipient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to decline this request.")

    if connection.status != ConnectionStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Connection request status is '{connection.status.value}', not PENDING.")

    # We update status, but maybe delete declined requests later?
    updated_connection = await update_connection_status(
        db=db, connection=connection, status=ConnectionStatus.DECLINED
    )
    
    # Notification Logic
    original_notification = await crud_notification.get_notification_by_related_entity(
        db, user_id=current_user.id, type=NotificationType.CONNECTION_REQUEST, related_entity_id=connection_id)
    if original_notification: await crud_notification.mark_notification_as_read(db=db, notification=original_notification)

    # Explicitly re-fetch the connection AFTER the update to ensure clean state for serialization
    # This avoids potential issues with the ORM object state during response model validation
    final_connection = await get_connection_by_id(db=db, connection_id=connection_id)
    if not final_connection:
         # Should not happen if update succeeded, but handle defensively
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found after update.")

    return final_connection

@router.get("/pending", response_model=List[connection_schemas.Connection])
async def get_pending_requests(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get pending INCOMING connection requests for the current user."""
    connections = await get_pending_connections_for_user(db=db, user_id=current_user.id)
    return connections

@router.get("/sent", response_model=List[connection_schemas.Connection])
async def get_sent_pending_requests(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get PENDING connection requests SENT BY the current user."""
    connections = await get_sent_pending_connections_for_user(db=db, user_id=current_user.id)
    return connections

@router.get("/accepted", response_model=List[connection_schemas.Connection])
async def get_accepted_connections(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all ACCEPTED connections for the current user."""
    connections = await get_accepted_connections_for_user(db=db, user_id=current_user.id)
    return connections

@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Delete a connection. Allows requester to cancel PENDING, or either party to remove an ACCEPTED connection."""
    deleted = await delete_connection_by_id_and_user(
        db=db, connection_id=connection_id, current_user_id=current_user.id
    )
    if not deleted: # Should not happen if no exception was raised by CRUD
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete connection.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/status/{other_user_id}", response_model=ConnectionStatusCheck)
async def get_connection_status_with_user(
    other_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get connection status between current user and another specific user."""
    if current_user.id == other_user_id:
        # Consider what to return: 'connected' to self, or error, or specific status?
        # For now, return a special status or disallow.
        # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot check connection status with yourself.")
        return ConnectionStatusCheck(status="self", connection_id=None)

    # This uses the batch status check for a single user, which is efficient.
    status_map = await get_connections_status_for_users(
        db=db, current_user_id=current_user.id, other_user_ids=[other_user_id]
    )
    if other_user_id not in status_map:
        # Should be handled by get_connections_status_for_users to return 'not_connected'
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status not determinable for the user.")
    return status_map[other_user_id]

@router.get("/status-batch", response_model=Dict[int, ConnectionStatusCheck])
async def get_connection_status_batch(
    user_ids: List[int] = Query(..., alias="user_id"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get connection status between current user and a list of other users."""
    # Filter out current_user_id from the list if present, as it's handled by /status/{id}
    # or could return a specific status here too.
    processed_user_ids = [uid for uid in user_ids if uid != current_user.id]
    if not processed_user_ids:
        return {}
    
    status_map = await get_connections_status_for_users(
        db=db, current_user_id=current_user.id, other_user_ids=processed_user_ids
    )
    # If original list included current_user.id, add a 'self' status for it
    if current_user.id in user_ids:
        status_map[current_user.id] = ConnectionStatusCheck(status="self", connection_id=None)
        
    return status_map 