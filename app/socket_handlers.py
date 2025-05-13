import socketio
import logging
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session # For DB operations

from app.core.config import settings
from app.db.session import AsyncSessionLocal # Import session factory
from app import crud, models # Ensure models is imported
from app.crud import crud_user # <<< ADDED IMPORT
from app.schemas.token import TokenPayload # Import schema
from app.schemas.chat import ChatMessageCreate, ChatMessageSchema # Import chat schemas
from app.crud.crud_chat import (
    create_message, 
    get_messages_for_conversation, 
    mark_conversation_messages_as_read,
    get_or_create_conversation
) # Corrected import names
from app.models.user import User as UserModel # Import UserModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory mapping for MVP: {sid: user_id}. NOTE: This will not scale beyond a single process.
# Consider Redis or another shared store for multi-process/distributed deployments.
sid_user_map = {}
online_user_ids = set() # Set to store IDs of currently online users

async def _get_user_from_token(token: str, db: AsyncSession) -> int | None:
    """Helper to validate token and get user ID."""
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY.get_secret_value(), algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload) # Validate payload structure
        if token_data.user_id is None:
            logger.warning("Token payload missing user_id")
            return None
    except JWTError as e:
        logger.warning(f"JWT Error: {e}")
        return None
    except Exception as e: # Catch potential Pydantic validation errors too
        logger.error(f"Token validation error: {e}")
        return None

    user = await crud.crud_user.get_user_by_id(db, user_id=token_data.user_id)
    if user is None:
        logger.warning(f"User not found for ID: {token_data.user_id}")
        return None

    # Optional: Add checks like user.is_active or status == 'ACTIVE'
    if not user.is_active: # or user.status != 'ACTIVE':
         logger.warning(f"Attempted connection by inactive user: {user.id}")
         return None

    return user.id

def register_socketio_handlers(sio: socketio.AsyncServer):
    @sio.event
    async def connect(sid, environ, auth):
        """Handles new client connections with authentication."""
        logger.info(f"Socket.IO client connecting: {sid}")

        token = auth.get('token') if auth else None

        if not token:
             logger.warning(f"Connection attempt refused for {sid}: No token provided in auth")
             return False

        async with AsyncSessionLocal() as db:
            user_id = await _get_user_from_token(token, db)

        if not user_id:
            logger.warning(f"Socket.IO connection refused for {sid}: Invalid token or user")
            return False

        logger.info(f"Socket.IO client connected: {sid}, User ID: {user_id}")
        sid_user_map[sid] = user_id
        online_user_ids.add(user_id)
        logger.info(f"Authenticated user {user_id} mapped to sid {sid}. Online users: {len(online_user_ids)}")

        await sio.enter_room(sid, str(user_id))
        logger.info(f"Sid {sid} joined room '{user_id}'")

        await sio.emit('user_online', {'user_id': user_id}, skip_sid=sid)
        await sio.emit('online_users_list', list(online_user_ids), room=sid)

    @sio.event
    async def disconnect(sid):
        """Handles client disconnections."""
        logger.info(f"Socket.IO client disconnected: {sid}")
        user_id = sid_user_map.pop(sid, None)
        if user_id:
            online_user_ids.discard(user_id)
            logger.info(f"Removed mapping for sid {sid} (User: {user_id}). Online users: {len(online_user_ids)}")
            await sio.emit('user_offline', {'user_id': user_id}, skip_sid=sid)
        else:
            logger.warning(f"No user ID found for disconnected sid {sid}")

    # --- Chat Message Handler ---
    @sio.on('send_message')
    async def handle_send_message(sid, data):
        """Handles receiving and broadcasting chat messages, now with attachment support."""
        sender_id = sid_user_map.get(sid)
        if not sender_id:
            logger.warning(f"Received 'send_message' from unknown sid: {sid}")
            return

        try:
            # Expecting data = {"recipient_id": int, "content": str, 
            #                   "attachment_url": Optional[str], "attachment_filename": Optional[str], 
            #                   "attachment_mimetype": Optional[str]}
            recipient_id = int(data['recipient_id']) # Assuming direct messages for now
            content = str(data.get('content', '')) # Content can be empty for attachments
            
            attachment_url = data.get('attachment_url')
            attachment_filename = data.get('attachment_filename')
            attachment_mimetype = data.get('attachment_mimetype')

            # A message should have content or an attachment
            if not content and not attachment_url:
                 logger.warning(f"User {sender_id} sent an empty message (no content, no attachment) to {recipient_id}")
                 return

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Invalid 'send_message' data from {sid} (User: {sender_id}): {data} - Error: {e}")
            return

        logger.info(f"User {sender_id} sending message to {recipient_id}. Content: '{content[:30]}...'. Attachment: {attachment_filename if attachment_url else 'None'}")

        async with AsyncSessionLocal() as db:
            # Create message object for saving
            message_in = ChatMessageCreate(
                recipient_id=recipient_id,
                content=content,
                attachment_url=attachment_url,
                attachment_filename=attachment_filename,
                attachment_mimetype=attachment_mimetype
            )

            # Save message to database
            try:
                db_message = await create_message( 
                    db=db, 
                    obj_in=message_in, 
                    sender_id=sender_id,
                    online_user_ids=online_user_ids # Pass the global set
                )
                logger.info(f"Message saved to DB (ID: {db_message.id}), Att: {db_message.attachment_filename}")
            except Exception as e:
                logger.error(f"Failed to save message from {sender_id} to {recipient_id}: {e}")
                return

            # Convert to Pydantic schema for broadcasting
            message_data = ChatMessageSchema.model_validate(db_message).model_dump(mode='json')

            # Fetch sender's details for notification
            sender_user = await crud_user.get_user_by_id(db, user_id=sender_id)
            sender_name = sender_user.full_name if sender_user else "Someone"

        recipient_room = str(recipient_id)
        logger.info(f"Emitting 'receive_message' to room: {recipient_room}")
        await sio.emit('receive_message', message_data, room=recipient_room)

        sender_room = str(sender_id)
        logger.info(f"Emitting 'receive_message' back to sender room: {sender_room}")
        await sio.emit('receive_message', message_data, room=sender_room)

        # Emit notification to recipient (if not themselves)
        if sender_id != recipient_id:
            message_preview = (db_message.content[:50] + '...') if db_message.content and len(db_message.content) > 50 else db_message.content
            if not message_preview and db_message.attachment_filename: # If no content, use filename as preview
                message_preview = f"Attachment: {db_message.attachment_filename}"
            
            notification_payload = {
                "message_id": db_message.id,
                "conversation_id": db_message.conversation_id,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "message_preview": message_preview,
                "created_at": db_message.created_at.isoformat() # Include timestamp
            }
            logger.info(f"Emitting 'new_message_notification' to room {recipient_room} for message {db_message.id}")
            await sio.emit('new_message_notification', notification_payload, room=recipient_room)

    # --- Read Receipt Handler ---
    @sio.on('mark_as_read')
    async def handle_mark_as_read(sid, data):
        """Handles when a client marks messages in a conversation as read."""
        reader_user_id = sid_user_map.get(sid) # The user who is reading
        if not reader_user_id:
            logger.warning(f"Received 'mark_as_read' from unknown sid: {sid}")
            return

        try:
            conversation_partner_id = int(data['sender_id']) # The other user in the conversation
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Invalid 'mark_as_read' data from {sid} (User: {reader_user_id}): {data} - Error: {e}")
            return

        logger.info(f"User {reader_user_id} marking messages with user {conversation_partner_id} as read.")

        async with AsyncSessionLocal() as db:
            try:
                # First, get or create the conversation to ensure we have its ID
                conversation = await crud.crud_chat.get_or_create_conversation(
                    db=db, user1_id=reader_user_id, user2_id=conversation_partner_id
                )
                if not conversation:
                    logger.error(f"Could not get or create conversation between {reader_user_id} and {conversation_partner_id}")
                    return

                updated_count = await crud.crud_chat.mark_conversation_messages_as_read(
                    db=db, conversation_id=conversation.id, reader_id=reader_user_id
                )
                logger.info(f"Marked {updated_count} messages as read in conversation {conversation.id} for reader {reader_user_id}.")
                
                if updated_count > 0:
                    # Notify the conversation partner that their messages have been read
                    partner_room = str(conversation_partner_id)
                    await sio.emit('messages_read', 
                                   {'reader_id': reader_user_id, 
                                    'conversation_id': conversation.id, 
                                    'conversation_partner_id': conversation_partner_id, # Keep for client use if needed
                                    'count': updated_count},
                                   room=partner_room)
                    logger.info(f"Emitted 'messages_read' to room {partner_room} for conversation {conversation.id}")

            except Exception as e:
                logger.error(f"Failed to mark messages as read for user {reader_user_id} with {conversation_partner_id}: {e}")

    # --- Placeholder Handlers ---
    @sio.on('user_typing')
    async def handle_user_typing(sid, data):
        user_id = sid_user_map.get(sid)
        logger.info(f"User {user_id} typing status changed (Data: {data}) - Placeholder")

    # @sio.on('some_event') # Keep or remove the original placeholder as needed
    # async def handle_some_event(sid, data):
    #     ... 