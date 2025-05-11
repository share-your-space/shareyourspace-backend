from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List # Import List

from app import crud, models, schemas # schemas.chat will be used
from app.db.session import get_db
from app.security import get_current_active_user # Assuming this dependency exists

router = APIRouter()


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