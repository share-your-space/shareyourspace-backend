from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base_class import Base

class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True) # Recipient
    type = Column(String, index=True, nullable=False) # e.g., 'connection_request', 'connection_accepted', 'new_chat_message'
    message = Column(String, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Optional fields for linking and grouping
    related_entity_id = Column(Integer, index=True, nullable=True) # e.g., connection.id, message.id (kept for potential legacy use)
    reference = Column(String, index=True, nullable=True) # e.g., 'connection:<id>', 'conversation:<id>'
    link = Column(String, nullable=True) # e.g., '/profile/123', '/chat?conversationId=456'

    # Relationship back to the user (optional, but can be useful)
    user = relationship("User") 