from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict

from app import crud, models, schemas
from app.models.enums import NotificationType, ConnectionStatus

async def create_connection(
    db: AsyncSession, *, requester_id: int, connection_in: schemas.connection.ConnectionCreate
) -> models.Connection:
    if requester_id == connection_in.recipient_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot connect with yourself.")

    recipient = await crud.crud_user.get_user_by_id(db=db, user_id=connection_in.recipient_id)
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient user not found.")

    connection = await crud.crud_connection.create_connection(
        db=db, requester_id=requester_id, obj_in=connection_in
    )

    if connection.status == ConnectionStatus.PENDING:
        await crud.crud_notification.create_notification(
            db,
            user_id=recipient.id,
            type=NotificationType.CONNECTION_REQUEST,
            message=f"You have a new connection request.",
            related_entity_id=connection.id,
        )
    elif connection.status == ConnectionStatus.ACCEPTED:
        # Auto-accepted, notify the original requester
        await crud.crud_notification.create_notification(
            db,
            user_id=connection.requester_id,
            type=NotificationType.CONNECTION_ACCEPTED,
            message=f"{recipient.full_name} accepted your connection request.",
            related_entity_id=connection.id,
        )

    return await crud.crud_connection.get_connection_by_id(db=db, connection_id=connection.id)


async def accept_connection(db: AsyncSession, *, connection_id: int, current_user: models.User) -> models.Connection:
    connection = await crud.crud_connection.get_connection_by_id(db=db, connection_id=connection_id)
    if not connection or connection.recipient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to accept this request.")
    if connection.status != ConnectionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Connection request is not pending.")

    updated_connection = await crud.crud_connection.update_connection_status(
        db=db, connection=connection, status=ConnectionStatus.ACCEPTED
    )

    await crud.crud_notification.create_notification(
        db,
        user_id=updated_connection.requester_id,
        type=NotificationType.CONNECTION_ACCEPTED,
        message=f"{current_user.full_name} accepted your connection request.",
        related_entity_id=updated_connection.id,
    )
    
    return updated_connection

async def decline_connection(db: AsyncSession, *, connection_id: int, current_user: models.User) -> models.Connection:
    connection = await crud.crud_connection.get_connection_by_id(db=db, connection_id=connection_id)
    if not connection or connection.recipient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to decline this request.")
    if connection.status != ConnectionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Connection request is not pending.")

    return await crud.crud_connection.update_connection_status(
        db=db, connection=connection, status=ConnectionStatus.DECLINED
    )

async def get_connection_statuses(
    db: AsyncSession, *, current_user_id: int, other_user_ids: List[int]
) -> Dict[int, schemas.connection.ConnectionStatusCheck]:
    return await crud.crud_connection.get_connections_status_for_users(
        db, current_user_id=current_user_id, other_user_ids=other_user_ids
    )

async def get_pending_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    """Get pending INCOMING connection requests for a user."""
    return await crud.crud_connection.get_pending_connections_for_user(db=db, user_id=user_id)

async def get_sent_pending_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    """Get PENDING connection requests SENT BY a user."""
    return await crud.crud_connection.get_sent_pending_connections_for_user(db=db, user_id=user_id)

async def get_accepted_connections_for_user(db: AsyncSession, *, user_id: int) -> List[models.Connection]:
    """Get all ACCEPTED connections for a user."""
    return await crud.crud_connection.get_accepted_connections_for_user(db=db, user_id=user_id)

async def delete_connection_by_id_and_user(db: AsyncSession, *, connection_id: int, current_user_id: int):
    """Delete a connection."""
    # We might want to add checks here to ensure user has permission to delete.
    # For now, just passing through to CRUD.
    connection = await crud.crud_connection.get_connection_by_id(db=db, connection_id=connection_id)
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found.")
    
    if connection.requester_id != current_user_id and connection.recipient_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this connection.")

    return await crud.crud_connection.remove(db=db, id=connection_id) 