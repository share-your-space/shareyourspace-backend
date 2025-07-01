from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

# Assuming a User schema exists for embedding sender/recipient info
from .user import User as UserSchema
from .common import UserSimpleInfo

# --- Conversation Schemas --- #
class ConversationParticipantBase(BaseModel):
    user_id: int

class ConversationParticipantCreate(ConversationParticipantBase):
    pass

class ConversationParticipantSchema(ConversationParticipantBase):
    user: UserSchema
    model_config = {
        'from_attributes': True
    }

class ConversationBase(BaseModel):
    pass

class ConversationCreate(ConversationBase):
    # Typically created with a list of participant user IDs
    participant_ids: List[int]

class ConversationSchema(ConversationBase):
    id: int
    is_external: bool
    created_at: datetime
    participants: List[UserSchema]

    model_config = {
        'from_attributes': True
    }

# --- Message Reaction Schemas (MOVED UP) --- #
class MessageReactionBase(BaseModel):
    emoji: str

class MessageReactionCreate(MessageReactionBase):
    pass

class MessageReactionResponse(MessageReactionBase):
    id: int
    message_id: int
    user_id: int
    created_at: datetime
    # Optionally include user info
    # user: UserSchema | None = None

    model_config = {
        'from_attributes': True
    }

class ExternalChatCreate(BaseModel):
    recipient_id: int

class MessageReactionsListResponse(BaseModel):
    reactions: list[MessageReactionResponse]

# --- Chat Message Schemas --- #

# Schema for receiving message content from client
class ChatMessageCreate(BaseModel):
    recipient_id: Optional[int] = None
    conversation_id: Optional[int] = None
    content: str
    attachment_url: Optional[str] = None
    attachment_filename: Optional[str] = None
    attachment_mimetype: Optional[str] = None

# Base schema for message properties included in responses
class ChatMessageBase(BaseModel):
    id: int
    sender_id: int
    recipient_id: Optional[int] = None
    conversation_id: Optional[int] = None
    content: str
    created_at: datetime
    read_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    attachment_url: Optional[str] = None
    attachment_filename: Optional[str] = None
    attachment_mimetype: Optional[str] = None

# Full message schema including loaded relationships
class ChatMessageSchema(ChatMessageBase):
    sender: UserSimpleInfo
    reactions: List[MessageReactionResponse] = []

    model_config = {
        'from_attributes': True
    }

# Schema for updating a message
class ChatMessageUpdate(BaseModel):
    content: str

# Schema for basic message info, used in ConversationForList
class ChatMessageBasic(BaseModel):
    id: int
    sender_id: int
    content: str
    created_at: datetime
    # Add other simple fields if needed by ContactList preview

    model_config = {
        'from_attributes': True
    }

# Schema for representing a conversation in the list view for the frontend
class ConversationForList(BaseModel):
    id: int
    is_external: bool
    other_user: UserSimpleInfo
    last_message: Optional[ChatMessageBasic] = None
    has_unread_messages: bool
    unread_count: Optional[int] = 0

    model_config = {
        'from_attributes': True
    }

# To resolve forward reference for ConversationSchema.messages if you uncomment it
# ConversationSchema.model_rebuild() 

# ConversationSchema.model_rebuild() # May not be needed if Pydantic handles it 