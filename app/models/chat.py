from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime, func, String, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship

from app.db.base_class import Base
# Assuming User model is in app.models.user
# Adjust import if needed
from app.models.user import User


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=func.now())
    # participants relationship (many-to-many via ConversationParticipant)
    participants = relationship("User", secondary="conversation_participants", back_populates="conversations")
    messages = relationship("ChatMessage", back_populates="conversation", order_by="ChatMessage.created_at")

class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    # New field to track when the user last read messages in this conversation
    last_read_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", overlaps="conversations,participants")
    conversation = relationship("Conversation", overlaps="conversations,participants")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    
    # Option 1: Direct message fields (simpler for 1-on-1, might be removed if Conversation model is primary)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Nullable if using conversation_id primarily
    
    # Option 2: Link to a conversation (better for group chats and cleaner for 1-on-1 too)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True) # Made nullable for now, can be false if we enforce conversations for all messages

    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    read_at = Column(DateTime, nullable=True)

    # New fields for edit/delete
    updated_at = Column(DateTime(timezone=True), nullable=True) # Stores timestamp of last edit
    is_deleted = Column(Boolean, default=False, nullable=False) # Flag for soft deletion

    # Attachment fields
    attachment_url = Column(String, nullable=True)
    attachment_filename = Column(String, nullable=True)
    attachment_mimetype = Column(String, nullable=True) # e.g., 'image/jpeg', 'application/pdf'

    sender = relationship("User", foreign_keys=[sender_id], backref="sent_messages")
    recipient = relationship("User", foreign_keys=[recipient_id], backref="received_messages") # This backref might need adjustment if using conversations primarily
    
    conversation = relationship("Conversation", back_populates="messages", foreign_keys=[conversation_id])
    reactions = relationship(
        "MessageReaction",
        back_populates="message",
        cascade="all, delete-orphan"
    )

class MessageReaction(Base):
    __tablename__ = "message_reactions"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    emoji = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())

    # Ensure a user can only react with a given emoji once per message
    __table_args__ = (UniqueConstraint('message_id', 'user_id', 'emoji', name='_message_user_emoji_uc'),)

    message = relationship("ChatMessage", back_populates="reactions")
    user = relationship("User") 