from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base_class import Base

class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True) # Recipient
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True) # The user who triggered the notification
    type = Column(String(50), index=True, nullable=False)
    message = Column(String, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    is_actioned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # The user who initiated the action that created the notification
    # For a join request, this is the user asking to join.
    related_entity_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)

    reference = Column(String, index=True, nullable=True) # e.g., 'connection:<id>', 'conversation:<id>'
    link = Column(String, nullable=True) # e.g., '/profile/123', '/chat?conversationId=456'

    # Relationship to the recipient of the notification
    user = relationship("User", foreign_keys=[user_id]) 
    
    # Relationship to the sender of the notification
    sender = relationship("User", foreign_keys=[sender_id], lazy="joined")

    # Relationship to the user who is the subject of the notification
    requesting_user = relationship("User", foreign_keys=[related_entity_id]) 