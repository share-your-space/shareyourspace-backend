from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict
import logging

from app import models, crud # Removed schemas from here
from app.schemas import connection as connection_schemas # Import connection schemas specifically
from app.crud import crud_connection, crud_user, crud_notification # Import specific crud modules and notification
# Also import user schema if needed for validation or response
from app.schemas.user import User as UserSchema
from app.db.session import get_db
from app.security import get_current_active_user
# Import email utility
from app.utils.email import send_email
from app.schemas.connection import Connection, ConnectionCreate, ConnectionStatusCheck # Import new schema

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
    connection_obj = await crud_connection.create_connection(
        db=db, requester_id=current_user.id, obj_in=connection_in
    )

    # --- Notification Logic (Only if a NEW pending request was actually created/updated) --- 
    # Check the status returned by the CRUD function
    if connection_obj.status == 'pending' and connection_obj.requester_id == current_user.id:
        # Check if notification ALREADY exists for this (e.g., if we just re-activated a declined request)
        existing_notification = await crud_notification.get_notification_by_related_entity(
            db, 
            user_id=recipient.id, 
            type='connection_request', 
            related_entity_id=connection_obj.id
        )
        if not existing_notification:
            # Create in-app notification for recipient
            notification_message = f"{current_user.full_name or current_user.email} wants to connect with you."
            await crud_notification.create_notification(
                db, 
                user_id=recipient.id, 
                type='connection_request', 
                related_entity_id=connection_obj.id, 
                message=notification_message
            )
            # Send email notification via Resend
            email_subject = "New Connection Request on ShareYourSpace"
            email_html_content = f"<p>Hi {recipient.full_name or recipient.email},</p>" \
                               f"<p>{current_user.full_name or current_user.email} wants to connect with you on ShareYourSpace.</p>" \
                               f"<p>Please log in to your account to accept or decline the request.</p>" \
                               f"<p>Thanks,<br>The ShareYourSpace Team</p>"
            send_email(to=recipient.email, subject=email_subject, html_content=email_html_content)
        else:
            logger.info(f"Skipping notification creation for connection {connection_obj.id}; existing notification found.")
    # --- End Notification Logic --- 

    # Re-fetch the connection cleanly before returning to avoid serialization issues
    final_connection = await crud_connection.get_connection_by_id(db=db, connection_id=connection_obj.id)
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
    connection = await crud_connection.get_connection_by_id(db=db, connection_id=connection_id)

    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection request not found.")

    if connection.recipient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to accept this request.")

    if connection.status != 'pending':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Connection request status is '{connection.status}', not 'pending'.")

    # Update the status - the CRUD function should commit
    # We pass the existing connection object which already has users loaded
    await crud_connection.update_connection_status(
        db=db, connection=connection, status='accepted'
    )

    # --- Notification Logic --- 
    # We already have the requester from the initial fetch
    requester = connection.requester 
    if requester:
        # Create notification for the requester
        notification_message = f"{current_user.full_name or current_user.email} accepted your connection request."
        await crud_notification.create_notification(
            db, 
            user_id=connection.requester_id, 
            type='connection_accepted', 
            related_entity_id=connection.id, 
            message=notification_message
        )
        # Send email notification
        email_subject = "Connection Request Accepted"
        email_html_content = f"<p>Hi {requester.full_name or requester.email},</p>" \
                           f"<p>{current_user.full_name or current_user.email} has accepted your connection request on ShareYourSpace.</p>" \
                           f"<p>You are now connected!</p>" \
                           f"<p>Thanks,<br>The ShareYourSpace Team</p>"
        send_email(to=requester.email, subject=email_subject, html_content=email_html_content)
        
    # Mark the original connection_request notification for the current user (recipient) as read
    original_notification = await crud_notification.get_notification_by_related_entity(
        db, 
        user_id=current_user.id, 
        type='connection_request', 
        related_entity_id=connection_id
    )
    if original_notification:
        await crud_notification.mark_notification_as_read(db=db, notification=original_notification)
    # --- End Notification Logic --- 

    # No need to refresh here, as we re-fetch below
    # await db.refresh(connection)

    # Re-fetch the connection with users eagerly loaded AFTER the update to ensure latest data
    # Use the existing get_connection_by_id function
    final_connection = await crud_connection.get_connection_by_id(db=db, connection_id=connection_id)
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
    connection = await crud_connection.get_connection_by_id(db=db, connection_id=connection_id)

    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection request not found.")

    if connection.recipient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to decline this request.")

    if connection.status != 'pending':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Connection request status is '{connection.status}', not 'pending'.")

    # We update status, but maybe delete declined requests later?
    await crud_connection.update_connection_status(
        db=db, connection=connection, status='declined'
    )
    
    # --- Mark original notification as read --- 
    original_notification = await crud_notification.get_notification_by_related_entity(
        db, 
        user_id=current_user.id, 
        type='connection_request', 
        related_entity_id=connection_id
    )
    if original_notification:
        await crud_notification.mark_notification_as_read(db=db, notification=original_notification)
    # --- End Notification Logic --- 

    # Explicitly re-fetch the connection AFTER the update to ensure clean state for serialization
    # This avoids potential issues with the ORM object state during response model validation
    final_connection = await crud_connection.get_connection_by_id(db=db, connection_id=connection_id)
    if not final_connection:
         # Should not happen if update succeeded, but handle defensively
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found after update.")

    return final_connection

@router.get("/pending", response_model=List[connection_schemas.Connection])
async def get_pending_requests(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get pending incoming connection requests for the current user."""
    pending_connections = await crud_connection.get_pending_connections_for_user(db=db, user_id=current_user.id)
    return pending_connections

@router.get("/accepted", response_model=List[connection_schemas.Connection])
async def get_accepted_connections(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get accepted connections for the current user."""
    accepted_connections = await crud_connection.get_accepted_connections_for_user(db=db, user_id=current_user.id)
    return accepted_connections

@router.get("/pending/outgoing", response_model=List[connection_schemas.Connection])
async def get_pending_outgoing_requests(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get pending outgoing connection requests made by the current user."""
    pending_outgoing = await crud_connection.get_pending_outgoing_connections_for_user(db=db, user_id=current_user.id)
    return pending_outgoing

@router.get("/declined", response_model=List[connection_schemas.Connection])
async def get_declined_connections(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get connections involving the current user that were declined."""
    declined_connections = await crud_connection.get_declined_connections_for_user(db=db, user_id=current_user.id)
    return declined_connections

@router.get("/status/{other_user_id}", response_model=ConnectionStatusCheck)
async def get_connection_status_with_user(
    other_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Check the connection status between the current user and another user."""
    if other_user_id == current_user.id:
        # Or maybe return a specific status?
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot check connection status with yourself.")

    connection = await crud_connection.get_connection_between_users(
        db=db, user1_id=current_user.id, user2_id=other_user_id
    )

    if not connection:
        return ConnectionStatusCheck(status='not_connected')

    status_detail = "unknown"
    if connection.status == 'accepted':
        status_detail = 'connected'
    elif connection.status == 'pending':
        if connection.requester_id == current_user.id:
            status_detail = 'pending_from_me'
        else:
            status_detail = 'pending_from_them'
    elif connection.status == 'declined':
        status_detail = 'declined' # Or maybe treat declined as not_connected?
    elif connection.status == 'blocked':
        status_detail = 'blocked' # Handle if blocking is implemented

    return ConnectionStatusCheck(status=status_detail, connection_id=connection.id)

# --- NEW BATCH ENDPOINT --- 
@router.get("/status-batch", response_model=Dict[int, ConnectionStatusCheck])
async def get_connection_status_batch(
    # Use Query for list parameters
    user_ids: List[int] = Query(..., alias="user_id"), # Read multiple user_id query params
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Check the connection status between the current user and multiple other users."""
    if not user_ids:
        return {}
    
    # Prevent checking status with self if included in the list
    user_ids_to_check = [uid for uid in user_ids if uid != current_user.id]
    if not user_ids_to_check:
        return {}

    status_map = await crud_connection.get_connections_status_for_users(
        db=db, current_user_id=current_user.id, other_user_ids=user_ids_to_check
    )
    return status_map 