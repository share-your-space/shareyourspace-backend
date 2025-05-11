from sqlalchemy import select, or_, and_, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.chat import ChatMessage, Conversation, ConversationParticipant
from app.models.user import User
from app.schemas.chat import ChatMessageCreate, ConversationCreate
from typing import List, Optional

async def get_or_create_conversation(
    db: AsyncSession, *, user1_id: int, user2_id: int
) -> Conversation:
    """Gets an existing 1-on-1 conversation or creates a new one."""
    # Ensure order for consistent lookup
    participant_ids_sorted = sorted([user1_id, user2_id])

    # Try to find an existing conversation with these exact two participants
    # This query is a bit more complex because we need to match participants exactly.
    stmt = (
        select(Conversation)
        .join(Conversation.participants)
        .group_by(Conversation.id)
        .having(func.count(User.id) == 2) # Ensure exactly two participants
        .having(func.bool_and(User.id.in_(participant_ids_sorted))) # Both users are in this conversation
    )
    result = await db.execute(stmt)
    conversation = result.scalars().first()

    if not conversation:
        # Create new conversation
        conversation = Conversation()
        db.add(conversation)
        await db.flush() # Ensure conversation.id is populated before use
        # Add participants
        user1_participant = ConversationParticipant(conversation_id=conversation.id, user_id=user1_id)
        user2_participant = ConversationParticipant(conversation_id=conversation.id, user_id=user2_id)
        db.add_all([user1_participant, user2_participant])
        await db.commit()
        await db.refresh(conversation, attribute_names=['participants'])
    return conversation

async def create_message(db: AsyncSession, *, obj_in: ChatMessageCreate, sender_id: int) -> ChatMessage:
    """Creates a new chat message and links it to a conversation."""
    
    conversation_id = obj_in.conversation_id
    if not conversation_id and obj_in.recipient_id:
        # If no conversation_id is provided but a recipient_id is, get/create 1-on-1 conversation
        conversation = await get_or_create_conversation(db, user1_id=sender_id, user2_id=obj_in.recipient_id)
        conversation_id = conversation.id
    elif not conversation_id:
        raise ValueError("Message creation requires either a conversation_id or a recipient_id.")

    db_obj_data = obj_in.model_dump()
    db_obj_data.pop('recipient_id', None) # Remove recipient_id if present, as it's handled by conversation
    db_obj_data.pop('conversation_id', None) # Ensure conversation_id from schema is not passed if we explicitly set it
    
    db_obj = ChatMessage(
        **db_obj_data,
        sender_id=sender_id,
        conversation_id=conversation_id # This is the definitive conversation_id
    )
    db.add(db_obj)
    await db.commit()
    
    # Eager load necessary fields for the response
    # Refresh sender and conversation (which can include participants)
    await db.refresh(db_obj, attribute_names=['sender', 'conversation'])
    if db_obj.conversation:
        await db.refresh(db_obj.conversation, attribute_names=['participants'])
        
    return db_obj

async def get_messages_for_conversation(
    db: AsyncSession, *, conversation_id: int, skip: int = 0, limit: int = 100
) -> List[ChatMessage]:
    """Retrieves messages for a specific conversation, ordered by creation time."""
    statement = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .options(selectinload(ChatMessage.sender)) # Use selectinload for related objects
        .order_by(ChatMessage.created_at.asc()) # Oldest first for typical chat UI display
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(statement)
    return result.scalars().all()

async def get_user_conversations_with_details(
    db: AsyncSession, *, user_id: int
) -> List[dict]: # Consider returning List[ConversationInfo] schema
    """Retrieves a list of conversations for the given user, 
       with the other participant(s) and the latest message for each."""
    stmt = (
        select(Conversation)
        .join(Conversation.participants)
        .where(User.id == user_id) # Filter conversations where the current user is a participant
        .options(
            selectinload(Conversation.participants).selectinload(User),
            selectinload(Conversation.messages).selectinload(ChatMessage.sender) # Load messages and their senders
        )
        .order_by(Conversation.created_at.desc()) # Or by last message time if preferred
    )
    result = await db.execute(stmt)
    conversations_orm = result.unique().scalars().all()

    # Format data according to ConversationInfo or similar DTO
    formatted_conversations = []
    for conv_orm in conversations_orm:
        other_participants = [p for p in conv_orm.participants if p.id != user_id]
        if not other_participants: # Should not happen in 1-on-1 or group chats
            continue
        
        # For 1-on-1, there will be one other participant
        # For group, you might list all or handle differently
        other_user = other_participants[0] if len(other_participants) == 1 else None 
        
        last_message = None
        if conv_orm.messages: # Messages are ordered by created_at in the model relationship
            # Sort messages by created_at descending to get the latest one
            sorted_messages = sorted(conv_orm.messages, key=lambda m: m.created_at, reverse=True)
            if sorted_messages:
                last_message = sorted_messages[0]
        
        # This part is a placeholder for unread count logic
        # You'd typically query ChatMessage.read_at for messages where recipient is user_id and in this conv_id
        unread_count = 0 
        # Example: count messages in conv_orm.messages where recipient_id == user_id and read_at is None
        # This requires recipient_id on ChatMessage or a more complex unread tracking mechanism if strictly conversation based.
        # For MVP, if recipient_id is on ChatMessage, it's easier:
        if last_message and last_message.recipient_id == user_id and not last_message.read_at:
            # This is a simplistic view for unread, true unread count needs more logic
             #unread_count = await db.scalar(...) # actual query for unread messages in this convo for user_id
             pass 

        formatted_conversations.append({
            "id": conv_orm.id,
            "other_user": other_user, # This assumes 1-on-1 for `other_user` field
            "last_message": last_message,
            "unread_count": unread_count
        })

    return formatted_conversations

async def mark_conversation_messages_as_read(
    db: AsyncSession, *, conversation_id: int, reader_id: int
) -> int:
    """Marks all unread messages in a conversation as read by the reader_id.
       This assumes messages in the conversation are directed towards the reader implicitly
       or that recipient_id is not strictly used for read status in a conversation context.
       For more precise 'recipient' based read status, recipient_id on ChatMessage is key.
    """
    statement = (
        update(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.sender_id != reader_id,  # Don't mark own messages as read by self
            ChatMessage.read_at.is_(None)
        )
        .values(read_at=func.now())
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(statement)
    await db.commit()
    return result.rowcount

# Old get_conversation_messages - to be replaced or removed
# async def get_conversation_messages(
#     db: AsyncSession, *, user1_id: int, user2_id: int, skip: int = 0, limit: int = 100
# ) -> list[ChatMessage]:
#     """Retrieves messages exchanged between two users, ordered by creation time."""
#     statement = (
#         select(ChatMessage)
#         .where(
#             or_(
#                 and_(ChatMessage.sender_id == user1_id, ChatMessage.recipient_id == user2_id),
#                 and_(ChatMessage.sender_id == user2_id, ChatMessage.recipient_id == user1_id),
#             )
#         )
#         .options(joinedload(ChatMessage.sender), joinedload(ChatMessage.recipient)) # Eager load users
#         .order_by(ChatMessage.created_at.desc()) # Get latest first
#         .offset(skip)
#         .limit(limit)
#     )
#     result = await db.execute(statement)
#     messages = result.scalars().all()
#     return list(reversed(messages)) # Reverse to show oldest first in typical chat UI

# Old mark_messages_as_read - to be replaced or removed
# async def mark_messages_as_read(
#     db: AsyncSession, *, recipient_id: int, sender_id: int
# ) -> int:
#     """Marks all unread messages from sender_id to recipient_id as read."""
#     statement = (
#         update(ChatMessage)
#         .where(
#             ChatMessage.recipient_id == recipient_id,
#             ChatMessage.sender_id == sender_id,
#             ChatMessage.read_at.is_(None) # Only update unread messages
#         )
#         .values(read_at=func.now())
#         .execution_options(synchronize_session=False) # Important for async updates
#     )
#     result = await db.execute(statement)
#     await db.commit()
#     return result.rowcount 