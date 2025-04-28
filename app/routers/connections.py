from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging

from app import models, crud # Removed schemas from here
from app.schemas import connection as connection_schemas # Import connection schemas specifically
from app.crud import crud_connection, crud_user # Import specific crud modules
# Also import user schema if needed for validation or response
# from app.schemas import user as user_schemas
from app.db.session import get_db
from app.security import get_current_active_user
# Import notification crud if needed for step 4.8
# from app.crud import crud_notification
# from app.utils.email import send_email # If sending emails

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

    connection = await crud_connection.create_connection(
        db=db, requester_id=current_user.id, obj_in=connection_in
    )

    # --- TODO: Step 4.8 Notification Logic --- 
    # if connection.status == 'pending': # Check if it's a new request vs existing
    #     # Create in-app notification for recipient
    #     await crud_notification.create_notification(
    #         db, user_id=recipient.id, type='connection_request', 
    #         related_entity_id=connection.id, 
    #         message=f"{current_user.full_name} wants to connect."
    #     )
    #     # Send email notification
    #     # send_email(...) 
    # --- End Notification Logic --- 

    return connection

@router.put("/{connection_id}/accept", response_model=connection_schemas.Connection)
async def accept_connection_request(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Accept a pending connection request."""
    connection = await crud_connection.get_connection_by_id(db=db, connection_id=connection_id)

    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection request not found.")

    if connection.recipient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to accept this request.")

    if connection.status != 'pending':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Connection request status is '{connection.status}', not 'pending'.")

    updated_connection = await crud_connection.update_connection_status(
        db=db, connection=connection, status='accepted'
    )

    # --- TODO: Step 4.8 Notification Logic --- 
    # # Create in-app notification for requester
    # await crud_notification.create_notification(
    #     db, user_id=connection.requester_id, type='connection_accepted', 
    #     related_entity_id=connection.id, 
    #     message=f"{current_user.full_name} accepted your connection request."
    # )
    # # Send email notification?
    # # send_email(...) 
    # --- End Notification Logic --- 

    return updated_connection

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
    updated_connection = await crud_connection.update_connection_status(
        db=db, connection=connection, status='declined'
    )
    return updated_connection

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