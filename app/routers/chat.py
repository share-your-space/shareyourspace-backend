from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status # Add WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging # Add logging

from app import crud, models, schemas, services # schemas.chat will be used
from app.db.session import get_db
from app.security import get_current_active_user, get_current_user_for_chat # Assuming this dependency exists
from app.schemas.chat import MessageReactionCreate, MessageReactionResponse, MessageReactionsListResponse, ChatMessageUpdate, ChatMessageSchema
from app.socket_instance import sio # <--- IMPORT SIO FROM NEW LOCATION
from app.schemas.notification import NotificationUpdate # Assuming this schema exists or we will create it
from app.crud.crud_notification import mark_notifications_as_read_by_ref # Assuming this exists or we will create it
from app.security import get_current_user_with_roles # Assuming this exists or we will create it

router = APIRouter()
logger = logging.getLogger(__name__) # Add logger instance


@router.get(
    "/conversations",
    response_model=List[schemas.chat.ConversationForList], # USE ConversationForList
    summary="Get User's Conversations",
    description="Retrieves a list of conversations the current user is part of, ordered by the most recent message."
)
async def get_user_conversations_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_for_chat),
):
    """
    Retrieve conversations for the current user.
    Each conversation includes the other participant's user info and the last message exchanged.
    """
    return await services.chat_service.get_user_conversations(db=db, user_id=current_user.id)


@router.get(
    "/conversations/{conversation_id}",
    response_model=schemas.chat.ConversationSchema,
    summary="Get a specific conversation by ID",
    description="Retrieves details for a single conversation, if the user is a participant."
)
async def get_conversation_endpoint(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_for_chat),
):
    conversation = await services.chat_service.get_conversation(
        db=db, conversation_id=conversation_id, user_id=current_user.id
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or user is not a participant."
        )
    return conversation


@router.get(
    "/conversations/with/{other_user_id}",
    response_model=schemas.chat.ConversationSchema,
    summary="Get or create a conversation with a specific user",
    description="Retrieves an existing conversation or creates a new one between the current user and the specified user."
)
async def get_or_create_conversation_with_user(
    other_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_for_chat),
):
    other_user = await crud.crud_user.get_user_by_id(db, user_id=other_user_id)
    if not other_user:
        raise HTTPException(status_code=404, detail="Other user not found")

    conversation = await services.chat_service.get_or_create_conversation(
        db=db, user1_id=current_user.id, user2_id=other_user_id
    )
    if not conversation:
        raise HTTPException(status_code=500, detail="Could not get or create conversation.")

    return conversation


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[schemas.chat.ChatMessageSchema], # Changed to ChatMessageSchema
    summary="Get Messages Between Two Users for their Conversation",
    description="Retrieves the message history for the conversation between the current user and another specified user."
)
async def get_messages_for_conversation(
    conversation_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_for_chat),
):
    """
    Retrieve message history for a conversation.
    Messages are returned ordered from oldest to newest.
    """
    # Ensure user is part of the conversation before fetching messages
    await services.chat_service.get_conversation(db, conversation_id=conversation_id, user_id=current_user.id)
    messages = await services.chat_service.get_messages(
        db=db, conversation_id=conversation_id, skip=skip, limit=limit
    )
    return messages

@router.post("/messages/{message_id}/reactions", response_model=schemas.chat.MessageReactionResponse | None)
async def add_or_toggle_reaction(
    message_id: int,
    reaction_in: schemas.chat.MessageReactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Add or toggle a reaction on a message."""
    return await services.chat_service.add_or_toggle_reaction(
        db, message_id=message_id, user_id=current_user.id, emoji=reaction_in.emoji
    )

@router.delete("/messages/{message_id}/reactions", response_model=dict)
async def remove_reaction(
    message_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Remove a reaction from a message."""
    await services.chat_service.remove_reaction(
        db, message_id=message_id, user_id=current_user.id, emoji=emoji
    )
    return {"ok": True}

@router.get("/messages/{message_id}/reactions", response_model=schemas.chat.MessageReactionsListResponse)
async def get_reactions_for_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all reactions for a message."""
    reactions = await services.chat_service.get_reactions(db, message_id=message_id)
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
    await services.chat_service.mark_conversation_as_read(
        db=db, conversation_id=conversation_id, user_id=current_user.id
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
    """Edit a chat message."""
    return await services.chat_service.edit_message(
        db=db, message_id=message_id, current_user_id=current_user.id, new_content=message_update.content
    )

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
    """Delete a chat message."""
    return await services.chat_service.delete_message(
        db=db, message_id=message_id, current_user_id=current_user.id
    )

@router.post(
    "/initiate-external",
    response_model=schemas.chat.ConversationSchema,
    dependencies=[Depends(get_current_user_with_roles(required_roles=["CORP_ADMIN"]))],
)
async def initiate_external_chat(
    chat_in: schemas.chat.ExternalChatCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Initiate an external chat with a user.
    """
    recipient = await crud.crud_user.get_user_by_id(db, user_id=chat_in.recipient_id)
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")

    conversation_orm = await services.chat_service.get_or_create_conversation(
        db, user1_id=current_user.id, user2_id=recipient.id, is_external=True
    )

    return conversation_orm 