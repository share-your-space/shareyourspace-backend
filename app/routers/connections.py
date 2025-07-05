from fastapi import APIRouter, Depends, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict

from app import models, schemas, services
from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.schemas import connection as connection_schemas

router = APIRouter()

@router.post("/", response_model=connection_schemas.Connection, status_code=status.HTTP_201_CREATED)
async def create_connection_request(
    connection_in: connection_schemas.ConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Send a connection request to another user."""
    return await services.connection_service.create_connection(
        db, requester_id=current_user.id, connection_in=connection_in
    )

@router.put("/{connection_id}/accept", response_model=connection_schemas.Connection)
async def accept_connection_request(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Accept a pending connection request."""
    return await services.connection_service.accept_connection(
        db, connection_id=connection_id, current_user=current_user
    )

@router.put("/{connection_id}/decline", response_model=connection_schemas.Connection)
async def decline_connection_request(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Decline a pending connection request."""
    return await services.connection_service.decline_connection(
        db, connection_id=connection_id, current_user=current_user
    )

@router.get("/pending", response_model=List[connection_schemas.Connection])
async def get_pending_requests(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get pending INCOMING connection requests for the current user."""
    return await services.connection_service.get_pending_connections_for_user(db=db, user_id=current_user.id)

@router.get("/sent", response_model=List[connection_schemas.Connection])
async def get_sent_pending_requests(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get PENDING connection requests SENT BY the current user."""
    return await services.connection_service.get_sent_pending_connections_for_user(db=db, user_id=current_user.id)

@router.get("/accepted", response_model=List[connection_schemas.Connection])
async def get_accepted_connections(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get all ACCEPTED connections for the current user."""
    return await services.connection_service.get_accepted_connections_for_user(db=db, user_id=current_user.id)

@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Delete a connection."""
    await services.connection_service.delete_connection_by_id_and_user(
        db=db, connection_id=connection_id, current_user_id=current_user.id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/status/{other_user_id}", response_model=connection_schemas.ConnectionStatusCheck)
async def get_connection_status_with_user(
    other_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get connection status between current user and another specific user."""
    if current_user.id == other_user_id:
        return connection_schemas.ConnectionStatusCheck(status="self", connection_id=None)

    status_map = await services.connection_service.get_connection_statuses(
        db=db, current_user_id=current_user.id, other_user_ids=[other_user_id]
    )
    return status_map[other_user_id]

@router.get("/status-batch", response_model=Dict[int, connection_schemas.ConnectionStatusCheck])
async def get_connection_status_batch(
    user_ids: List[int] = Query(..., alias="user_id"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """Get connection status between current user and a list of other users."""
    processed_user_ids = [uid for uid in user_ids if uid != current_user.id]
    if not processed_user_ids:
        return {}
    
    status_map = await services.connection_service.get_connection_statuses(
        db=db, current_user_id=current_user.id, other_user_ids=processed_user_ids
    )
    if current_user.id in user_ids:
        status_map[current_user.id] = connection_schemas.ConnectionStatusCheck(status="self", connection_id=None)
        
    return status_map 