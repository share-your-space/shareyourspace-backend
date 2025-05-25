import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.base_class import Base
from datetime import datetime, timedelta
import uuid
from typing import TYPE_CHECKING, Optional
from app.models.user import User # Ensure User is imported for relationships

if TYPE_CHECKING: # Add this for type hinting if not already present
    from .organization import Startup # For relationship type hint

class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"
    DECLINED = "declined" # New status
    # Consider DECLINED if users can explicitly decline

class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, index=True, nullable=False)
    
    # Foreign key to the startup (Startup table) that is inviting the user
    startup_id: Mapped[int] = mapped_column(ForeignKey("startups.id"), nullable=False)
    startup: Mapped["Startup"] = relationship(back_populates="invitations")

    invitation_token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    status: Mapped[InvitationStatus] = mapped_column(SQLEnum(InvitationStatus, name='invitationstatus', create_type=False), default=InvitationStatus.PENDING, nullable=False)
    
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(days=7)) # Default 7 days expiry
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # New fields for tracking approval and acceptance
    approved_by_admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_admin: Mapped[Optional["User"]] = relationship(foreign_keys=[approved_by_admin_id])

    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    accepted_by_user: Mapped[Optional["User"]] = relationship(foreign_keys=[accepted_by_user_id])

    # Admin who revoked this invitation
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_by_admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_by_admin: Mapped[Optional["User"]] = relationship(foreign_keys=[revoked_by_admin_id])

    # New fields for declining
    declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decline_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Using Text for potentially longer reasons

    def __repr__(self):
        return f"<Invitation(id={self.id}, email='{self.email}', status='{self.status}')>" 