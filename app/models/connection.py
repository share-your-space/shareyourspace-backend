from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.models.user import User # Import User for relationships

class Connection(Base):
    __tablename__ = "connections"

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Consider using an Enum for status if you prefer stricter type checking
    status = Column(String, nullable=False, default='pending', index=True) # e.g., 'pending', 'accepted', 'declined', 'blocked'
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships to User
    requester = relationship("User", foreign_keys=[requester_id]) # Add backref in User model if needed
    recipient = relationship("User", foreign_keys=[recipient_id]) # Add backref in User model if needed

    # Ensure a user can only send one request to another user
    __table_args__ = (UniqueConstraint('requester_id', 'recipient_id', name='_requester_recipient_uc'),) 