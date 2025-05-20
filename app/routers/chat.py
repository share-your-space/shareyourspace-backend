from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status # Add WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging # Add logging

from app import crud, models, schemas # schemas.chat will be used
from app.db.session import get_db
from app.security import get_current_active_user # Assuming this dependency exists
from app.schemas.chat import MessageReactionCreate, MessageReactionResponse, MessageReactionsListResponse, ChatMessageUpdate, ChatMessageSchema
from app.socket_instance import sio # <--- IMPORT SIO FROM NEW LOCATION
from app.schemas.notification import NotificationUpdate # Assuming this schema exists or we will create it
from app.crud.crud_notification import mark_notifications_as_read_by_ref # Assuming this exists or we will create it

router = APIRouter()
logger = logging.getLogger(__name__) # Add logger instance


@router.get(
    "/conversations",
    response_model=List[schemas.chat.ConversationInfo], # Changed to ConversationInfo
    summary="Get User's Conversations",
    description="Retrieves a list of conversations the current user is part of, ordered by the most recent message."
)
async def get_user_conversations_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Retrieve conversations for the current user.
    Each conversation includes the other participant's user info and the last message exchanged.
    """
    conversations_data = await crud.crud_chat.get_user_conversations_with_details(db=db, user_id=current_user.id)
    # The CRUD function now returns a list of dicts that should match ConversationInfo structure
    # Pydantic will validate this structure upon return. No explicit model_validate loop needed if CRUD matches schema.
    return conversations_data


@router.get(
    "/conversations/{other_user_id}/messages",
    response_model=List[schemas.chat.ChatMessageSchema], # Changed to ChatMessageSchema
    summary="Get Messages Between Two Users for their Conversation",
    description="Retrieves the message history for the conversation between the current user and another specified user."
)
async def get_messages_for_conversation_with_user(
    other_user_id: int,
    skip: int = Query(0, ge=0, description="Number of messages to skip"),
    limit: int = Query(100, ge=1, le=200, description="Maximum number of messages to return"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Retrieve message history between the current user and `other_user_id`.
    Messages are returned ordered from oldest to newest.
    """
    # Optional: Check if other_user_id exists or if users are connected
    other_user = await crud.crud_user.get_user_by_id(db, user_id=other_user_id)
    if not other_user:
        raise HTTPException(status_code=404, detail="Other user not found")

    # Get or create the 1-on-1 conversation between current_user and other_user
    conversation = await crud.crud_chat.get_or_create_conversation(
        db=db, user1_id=current_user.id, user2_id=other_user_id
    )
    if not conversation:
        # This case should ideally not be reached if get_or_create always returns or creates
        raise HTTPException(status_code=404, detail="Conversation could not be found or created.")

    messages = await crud.crud_chat.get_messages_for_conversation(
        db=db, conversation_id=conversation.id, skip=skip, limit=limit
    )
    return messages

@router.post("/messages/{message_id}/reactions", response_model=MessageReactionResponse | None)
async def add_or_toggle_reaction(
    message_id: int,
    reaction_in: MessageReactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    reaction_orm = await crud.crud_chat.add_or_toggle_reaction(
        db,
        message_id=message_id,
        user_id=current_user.id,
        emoji=reaction_in.emoji
    )

    chat_message = await crud.crud_chat.get_chat_message_by_id(db, message_id=message_id)
    if chat_message and chat_message.conversation:
        conversation = chat_message.conversation
        action = "added" if reaction_orm else "removed"
        reaction_payload = None
        if reaction_orm:
            await db.refresh(reaction_orm) 
            reaction_payload = MessageReactionResponse.model_validate(reaction_orm).model_dump(mode='json')

        for participant in conversation.participants:
            logger.info(f"Attempting to emit 'reaction_updated' to room: {str(participant.id)} for conversation {conversation.id}")
            logger.info(f"Reaction payload for emit: {reaction_payload}")
            await sio.emit(
                "reaction_updated",
                data={
                    "message_id": message_id,
                    "conversation_id": conversation.id,
                    "reaction": reaction_payload,
                    "user_id_who_reacted": current_user.id,
                    "emoji": reaction_in.emoji, # The emoji that was acted upon
                    "action": action,
                },
                room=str(participant.id)
            )
    
    return reaction_orm

@router.delete("/messages/{message_id}/reactions", response_model=dict)
async def remove_reaction(
    message_id: int,
    emoji: str, # emoji is a query parameter for DELETE
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    success = await crud.crud_chat.remove_reaction(
        db,
        message_id=message_id,
        user_id=current_user.id,
        emoji=emoji
    )
    if not success:
        raise HTTPException(status_code=404, detail="Reaction not found or already removed")

    chat_message = await crud.crud_chat.get_chat_message_by_id(db, message_id=message_id)
    if chat_message and chat_message.conversation:
        conversation = chat_message.conversation
        logger.info(f"Attempting to emit 'reaction_updated' (action: removed) to rooms for conversation {conversation.id}")
        for participant in conversation.participants:
            logger.info(f"Emitting reaction removal to user {str(participant.id)} for message {message_id}, emoji {emoji}")
            await sio.emit(
                "reaction_updated",
                data={
                    "message_id": message_id,
                    "conversation_id": conversation.id,
                    "reaction": None, 
                    "user_id_who_reacted": current_user.id,
                    "emoji": emoji, 
                    "action": "removed",
                },
                room=str(participant.id)
            )

    return {"ok": True}

@router.get("/messages/{message_id}/reactions", response_model=MessageReactionsListResponse)
async def get_reactions_for_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    reactions = await crud.crud_chat.get_reactions_for_message(db, message_id=message_id)
    return {"reactions": reactions}

@router.post(
    "/conversations/{conversation_id}/read", 
    status_code=status.HTTP_204_NO_CONTENT, # Use 204 No Content for successful updates with no body
    summary="Mark Conversation as Read",
    description="Updates the timestamp indicating the current user has read the specified conversation."
)
async def mark_conversation_as_read_endpoint(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Marks a conversation as read for the current user by updating their 
    `last_read_at` timestamp in the ConversationParticipant record.
    Also marks related 'new_chat_message' notifications as read.
    """
    updated = await crud.crud_chat.mark_conversation_as_read(
        db=db, 
        conversation_id=conversation_id, 
        user_id=current_user.id
    )
    
    if not updated:
        # This could mean the conversation doesn't exist or the user isn't a participant.
        # Raising 404 is appropriate as the target resource (user's participation) wasn't found/updated.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or user is not a participant."
        )

    # Now, mark related notifications as read
    # We need a way to link notifications to conversations. Assuming a reference like `conversation:{id}`
    notification_ref = f"conversation:{conversation_id}"
    try:
        # Assuming mark_notifications_as_read_by_ref exists and handles not finding notifications gracefully
        # We'll implement/verify this function in crud_notification next.
        await crud.crud_notification.mark_notifications_as_read_by_ref(
            db=db,
            user_id=current_user.id,
            reference=notification_ref
        )
        logger.info(f"Marked notifications as read for user {current_user.id} with reference {notification_ref}")
    except Exception as e:
        # Log error but don't fail the request just because notification update failed
        logger.error(f"Failed to mark notifications as read for user {current_user.id} with reference {notification_ref}: {e}")

    # If successful, return No Content (HTTP 204)
    return None 

@router.put(
    "/messages/{message_id}",
    response_model=schemas.chat.ChatMessageSchema,
    summary="Edit a Chat Message",
    description="Allows the sender of a message to edit its content within a configured time window."
)
async def edit_chat_message(
    message_id: int,
    message_update: schemas.chat.ChatMessageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    updated_message_orm = await crud.crud_chat.update_message(
        db=db, 
        message_id=message_id, 
        current_user_id=current_user.id, 
        new_content=message_update.content
    )

    if not updated_message_orm:
        original_message = await crud.crud_chat.get_chat_message_by_id(db=db, message_id=message_id)
        if not original_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        if original_message.sender_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot edit this message")
        # Check if it was due to time window or other condition like already deleted
        # This part can be more granular if needed, for now, a generic 403 if update fails for valid reasons
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Message cannot be edited (e.g., time window expired or already deleted)")

    # Emit event to conversation participants
    if updated_message_orm.conversation:
        # The ORM object from crud.update_message should have conversation loaded or be None
        # For safety, re-fetch if necessary, or ensure CRUD loads it if conversation_id exists
        conversation_participants = updated_message_orm.conversation.participants
        if not conversation_participants:
            # If somehow participants are not loaded, fetch them
            conv_with_participants = await db.get(models.Conversation, updated_message_orm.conversation_id, options=[selectinload(models.Conversation.participants)])
            if conv_with_participants:
                conversation_participants = conv_with_participants.participants

        if conversation_participants:
            updated_message_data = schemas.chat.ChatMessageSchema.model_validate(updated_message_orm).model_dump(mode='json')
            for participant in conversation_participants:
                logger.info(f"Emitting 'message_updated' to room: {str(participant.id)} for message {updated_message_orm.id}")
                await sio.emit(
                    "message_updated",
                    data=updated_message_data,
                    room=str(participant.id)
                )

    return updated_message_orm

@router.delete(
    "/messages/{message_id}",
    response_model=schemas.chat.ChatMessageSchema, # Or a specific schema for deleted messages
    summary="Delete a Chat Message",
    description="Allows the sender of a message to soft-delete it within a configured time window."
)
async def delete_chat_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    deleted_message_orm = await crud.crud_chat.delete_message(
        db=db, 
        message_id=message_id, 
        current_user_id=current_user.id
    )

    if not deleted_message_orm:
        # Similar error handling as edit
        original_message = await crud.crud_chat.get_chat_message_by_id(db=db, message_id=message_id)
        if not original_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        if original_message.sender_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot delete this message")
        # If it was already deleted, the CRUD returns the message, so this path is for other denials like time window.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Message cannot be deleted (e.g., time window expired)")
    
    # Emit event to conversation participants
    if deleted_message_orm.conversation:
        conversation_participants = deleted_message_orm.conversation.participants
        if not conversation_participants:
            conv_with_participants = await db.get(models.Conversation, deleted_message_orm.conversation_id, options=[selectinload(models.Conversation.participants)])
            if conv_with_participants:
                conversation_participants = conv_with_participants.participants
        
        if conversation_participants:
            # For delete, we only need to send the ID and conversation_id usually
            # But sending the full object with is_deleted=True is also fine and matches response_model
            deleted_message_data = schemas.chat.ChatMessageSchema.model_validate(deleted_message_orm).model_dump(mode='json')
            for participant in conversation_participants:
                logger.info(f"Emitting 'message_deleted' to room: {str(participant.id)} for message {deleted_message_orm.id}")
                await sio.emit(
                    "message_deleted",
                    data=deleted_message_data, # Or simpler: {"id": message_id, "conversation_id": deleted_message_orm.conversation_id}
                    room=str(participant.id)
                )

    return deleted_message_orm 