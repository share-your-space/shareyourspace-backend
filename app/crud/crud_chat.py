from sqlalchemy import select, or_, and_, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload, contains_eager
from datetime import datetime, timedelta, timezone # Ensure datetime and timedelta are imported

from app.models.chat import ChatMessage, Conversation, ConversationParticipant, MessageReaction
from app.models.user import User
from app.schemas.chat import ChatMessageCreate, ConversationCreate, ChatMessageUpdate
from typing import List, Optional, Set
from app.core.config import settings # Import settings

# Need crud_notification for creating notifications
from app.crud import crud_notification
import logging # Add logger

logger = logging.getLogger(__name__) # Add logger instance

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

async def create_message(
    db: AsyncSession, 
    *, 
    obj_in: ChatMessageCreate, 
    sender_id: int, 
    online_user_ids: Set[int] # Added parameter for online users
) -> ChatMessage:
    """Creates a new chat message, links it to a conversation,
       and creates notifications for offline participants."""
    
    conversation_id = obj_in.conversation_id
    conversation = None
    if not conversation_id and obj_in.recipient_id:
        conversation = await get_or_create_conversation(db, user1_id=sender_id, user2_id=obj_in.recipient_id)
        conversation_id = conversation.id
    elif conversation_id:
        # Fetch the conversation if only ID was provided initially
        res = await db.execute(select(Conversation).where(Conversation.id == conversation_id).options(selectinload(Conversation.participants)))
        conversation = res.scalars().first()
    
    if not conversation or not conversation_id:
        raise ValueError("Message creation requires a valid conversation.")

    db_obj_data = obj_in.model_dump()
    db_obj_data.pop('recipient_id', None)
    db_obj_data.pop('conversation_id', None)
    
    db_obj = ChatMessage(
        **db_obj_data,
        sender_id=sender_id,
        conversation_id=conversation_id
    )
    db.add(db_obj)
    await db.commit()
    
    # Eager load necessary fields for the response and for notification creation
    # First, refresh the message itself to get IDs and basic relationships populated
    await db.refresh(db_obj, attribute_names=['sender', 'conversation', 'reactions'])
    
    # Ensure the sender object is fully loaded (especially for full_name)
    sender_for_notification = None
    if db_obj.sender:
        await db.refresh(db_obj.sender) # Refresh the User object linked as sender
        sender_for_notification = db_obj.sender
    
    # Ensure the conversation object and its participants are loaded
    conversation_for_notification = None
    if db_obj.conversation:
        await db.refresh(db_obj.conversation, attribute_names=['participants'])
        conversation_for_notification = db_obj.conversation

    # --- Create Notifications for Offline Recipients --- 
    if conversation_for_notification and sender_for_notification: 
        sender_name = sender_for_notification.full_name or f"User {sender_for_notification.id}" # Fallback name
        notification_ref = f"conversation:{conversation_for_notification.id}"
        notification_link = f"/chat?conversationId={conversation_for_notification.id}"

        for participant_user_obj in conversation_for_notification.participants:
            if participant_user_obj.id != sender_id and participant_user_obj.id not in online_user_ids:
                try:
                    await crud_notification.create_notification(
                        db=db,
                        user_id=participant_user_obj.id,
                        type="new_chat_message",
                        message=f"New message from {sender_name}",
                        reference=notification_ref,
                        link=notification_link,
                        related_entity_id=db_obj.id # ID of the chat message itself
                    )
                    logger.info(f"Created new_chat_message notification for offline user {participant_user_obj.id} regarding conversation {conversation_for_notification.id}")
                except Exception as e:
                    logger.error(f"Failed to create notification for user {participant_user_obj.id}: {e}", exc_info=True)
        
    return db_obj

async def get_messages_for_conversation(
    db: AsyncSession, *, conversation_id: int, skip: int = 0, limit: int = 100
) -> List[ChatMessage]:
    """Retrieves messages for a specific conversation, ordered by creation time."""
    statement = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .options(
            selectinload(ChatMessage.sender), 
            selectinload(ChatMessage.reactions) # Eager load reactions
        )
        .order_by(ChatMessage.created_at.asc()) 
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(statement)
    return result.scalars().all()

async def get_user_conversations_with_details(db: AsyncSession, user_id: int) -> List[dict]:
    """Fetches conversations for a user, eager loading participants, the last message,
       and determining if there are unread messages for the user."""
    
    # Subquery to find the latest message timestamp for each conversation the user is part of
    latest_message_subquery = (
        select(
            ChatMessage.conversation_id,
            func.max(ChatMessage.created_at).label("max_created_at")
        )
        # Ensure we only consider conversations the current user is in for the latest message context
        .join(ConversationParticipant, 
              (ChatMessage.conversation_id == ConversationParticipant.conversation_id) & 
              (ConversationParticipant.user_id == user_id)
             )
        .group_by(ChatMessage.conversation_id)
        .subquery('latest_message_sq')
    )

    # Main statement to select Conversation, the actual last ChatMessage, 
    # and the current user's ConversationParticipant record for last_read_at
    stmt = (
        select(
            Conversation,
            ChatMessage,  # The last message object
            ConversationParticipant  # The specific participant record for the current user
        )
        .join(
            ConversationParticipant,
            (Conversation.id == ConversationParticipant.conversation_id) &
            (ConversationParticipant.user_id == user_id) # Join to get *this* user's participation details
        )
        .outerjoin( # Join to the subquery to find the timestamp of the latest message
            latest_message_subquery, 
            Conversation.id == latest_message_subquery.c.conversation_id
        )
        .outerjoin( # Join to ChatMessage again to get the actual latest message content
            ChatMessage,
            (Conversation.id == ChatMessage.conversation_id) &
            (ChatMessage.created_at == latest_message_subquery.c.max_created_at)
        )
        .options(
            selectinload(Conversation.participants), # Eager load all participants for "other_user" logic
            # No need to selectinload current_user_participant_orm as it's directly selected
        )
        .order_by(latest_message_subquery.c.max_created_at.desc().nulls_last(), Conversation.id)
    )

    result = await db.execute(stmt)
    # result_tuples will contain (Conversation, ChatMessage (or None), ConversationParticipant)
    result_tuples = result.unique().all()

    conversations_data = []
    for conv_orm, last_msg_orm_from_query, current_user_participant_orm in result_tuples:
        other_participant_user = next((p for p in conv_orm.participants if p.id != user_id), None)
        if not other_participant_user:
            # This should ideally not happen if data is consistent
            # (i.e., user is a participant and there's another participant)
            continue

        processed_last_message = None
        if last_msg_orm_from_query:
            # Refresh required attributes for the Pydantic model serialization
            await db.refresh(last_msg_orm_from_query, attribute_names=['sender', 'reactions'])
            processed_last_message = last_msg_orm_from_query

        # Calculate has_unread_messages
        has_unread = False
        if processed_last_message and current_user_participant_orm:
            # Check if the last message is not from the current user
            if processed_last_message.sender_id != user_id:
                # Ensure datetimes are comparable (both UTC aware)
                participant_last_read_dt = current_user_participant_orm.last_read_at
                last_message_created_dt = processed_last_message.created_at

                # Convert participant_last_read_dt if it's not None
                if participant_last_read_dt:
                    if participant_last_read_dt.tzinfo is None:
                        participant_last_read_dt = participant_last_read_dt.replace(tzinfo=timezone.utc)
                    elif participant_last_read_dt.tzinfo != timezone.utc:
                        participant_last_read_dt = participant_last_read_dt.astimezone(timezone.utc)
                
                # Convert last_message_created_dt (should always exist if processed_last_message exists)
                if last_message_created_dt.tzinfo is None:
                    last_message_created_dt = last_message_created_dt.replace(tzinfo=timezone.utc)
                elif last_message_created_dt.tzinfo != timezone.utc:
                    last_message_created_dt = last_message_created_dt.astimezone(timezone.utc)

                if participant_last_read_dt is None or \
                   participant_last_read_dt < last_message_created_dt:
                    has_unread = True
        
        conversations_data.append({
            "id": conv_orm.id,
            "other_user": other_participant_user,
            "last_message": processed_last_message,
            "has_unread_messages": has_unread # Add the new field
        })

    return conversations_data

async def mark_conversation_as_read(db: AsyncSession, *, conversation_id: int, user_id: int) -> bool:
    """Updates the last_read_at timestamp for a user in a specific conversation."""
    stmt = (
        update(ConversationParticipant)
        .where(
            (ConversationParticipant.conversation_id == conversation_id) &
            (ConversationParticipant.user_id == user_id)
        )
        .values(last_read_at=func.now())
        # Ensure that the update actually happens if the row exists, 
        # and we can check if it did.
        .execution_options(synchronize_session=False) 
    )
    result = await db.execute(stmt)
    await db.commit()
    # result.rowcount will be 1 if the update occurred, 0 otherwise.
    return result.rowcount > 0

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

async def add_or_toggle_reaction(db, *, message_id: int, user_id: int, emoji: str):
    # Check if reaction exists
    stmt = select(MessageReaction).where(
        MessageReaction.message_id == message_id,
        MessageReaction.user_id == user_id,
        MessageReaction.emoji == emoji
    )
    result = await db.execute(stmt)
    reaction = result.scalars().first()
    if reaction:
        # If exists, remove (toggle off)
        await db.delete(reaction)
        await db.commit()
        return None
    else:
        # Add new reaction
        new_reaction = MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji)
        db.add(new_reaction)
        await db.commit()
        await db.refresh(new_reaction)
        return new_reaction

async def remove_reaction(db, *, message_id: int, user_id: int, emoji: str):
    stmt = select(MessageReaction).where(
        MessageReaction.message_id == message_id,
        MessageReaction.user_id == user_id,
        MessageReaction.emoji == emoji
    )
    result = await db.execute(stmt)
    reaction = result.scalars().first()
    if reaction:
        await db.delete(reaction)
        await db.commit()
        return True
    return False

async def get_reactions_for_message(db, *, message_id: int):
    stmt = select(MessageReaction).where(MessageReaction.message_id == message_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_chat_message_by_id(db: AsyncSession, *, message_id: int) -> ChatMessage | None:
    """Fetches a specific chat message by its ID, eager loading sender, reactions, and conversation with its participants."""
    statement = (
        select(ChatMessage)
        .where(ChatMessage.id == message_id)
        .options(
            selectinload(ChatMessage.sender),
            selectinload(ChatMessage.reactions),
            selectinload(ChatMessage.conversation).selectinload(Conversation.participants)
        )
    )
    result = await db.execute(statement)
    return result.scalars().first()

async def update_message(
    db: AsyncSession, *, message_id: int, current_user_id: int, new_content: str
) -> ChatMessage | None:
    """Updates a chat message if the user is the sender and it's within the edit window."""
    message = await get_chat_message_by_id(db=db, message_id=message_id)

    if not message:
        return None # Message not found
    
    if message.sender_id != current_user_id:
        return None # User is not the sender

    if message.is_deleted:
        return None # Message is already deleted

    # Ensure created_at is offset-aware (UTC)
    created_at_utc = message.created_at
    if created_at_utc.tzinfo is None:
        created_at_utc = created_at_utc.replace(tzinfo=timezone.utc)
    else:
        created_at_utc = created_at_utc.astimezone(timezone.utc)

    # Current time in UTC
    now_utc = datetime.now(timezone.utc)
    
    # Check if within the editable window
    if now_utc > created_at_utc + timedelta(seconds=settings.MESSAGE_EDIT_DELETE_WINDOW_SECONDS):
        return None # Past editable window

    message.content = new_content
    message.updated_at = now_utc
    
    db.add(message)
    await db.commit()
    await db.refresh(message, attribute_names=['sender', 'reactions'])
    return message

async def delete_message(
    db: AsyncSession, *, message_id: int, current_user_id: int
) -> ChatMessage | None:
    """Soft deletes a chat message if the user is the sender and it's within the delete window."""
    message = await get_chat_message_by_id(db=db, message_id=message_id)

    if not message:
        return None # Message not found

    if message.sender_id != current_user_id:
        return None # User is not the sender

    if message.is_deleted:
        return message # Already deleted, return current state

    # Ensure created_at is offset-aware (UTC)
    created_at_utc = message.created_at
    if created_at_utc.tzinfo is None:
        created_at_utc = created_at_utc.replace(tzinfo=timezone.utc)
    else:
        created_at_utc = created_at_utc.astimezone(timezone.utc)
    
    # Current time in UTC
    now_utc = datetime.now(timezone.utc)

    # Check if within the deletable window
    if now_utc > created_at_utc + timedelta(seconds=settings.MESSAGE_EDIT_DELETE_WINDOW_SECONDS):
        return None # Past deletable window

    message.is_deleted = True
    message.updated_at = now_utc # Mark when the deletion occurred
    # Optionally, clear content for privacy, though frontend will handle display
    # message.content = "This message was deleted."

    db.add(message)
    await db.commit()
    await db.refresh(message, attribute_names=['sender', 'reactions'])
    return message

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