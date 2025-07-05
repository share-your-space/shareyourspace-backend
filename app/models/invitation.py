from __future__ import annotations
import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.base_class import Base
from datetime import datetime, timedelta
import uuid
from typing import TYPE_CHECKING, Optional
from app.models.enums import UserRole

if TYPE_CHECKING:
    from .organization import Startup, Company
    from .space import SpaceNode
    from .user import User

class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"
    DECLINED = "declined"

class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, index=True, nullable=False)
    role: Mapped[Optional[UserRole]] = mapped_column(SQLEnum(UserRole), nullable=True)
    
    startup_id: Mapped[Optional[int]] = mapped_column(ForeignKey("startups.id"), nullable=True)
    startup: Mapped[Optional["Startup"]] = relationship(back_populates="invitations")

    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id"), nullable=True)
    company: Mapped[Optional["Company"]] = relationship(back_populates="invitations")

    space_id: Mapped[Optional[int]] = mapped_column(ForeignKey("spacenodes.id"), nullable=True)
    space: Mapped[Optional["SpaceNode"]] = relationship(back_populates="invitations")

    invitation_token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    status: Mapped[InvitationStatus] = mapped_column(SQLEnum(InvitationStatus, name='invitationstatus'), default=InvitationStatus.PENDING, nullable=False)
    
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(days=7))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    accepted_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    
    # New fields for tracking who did what
    invited_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    approved_by_admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_by_admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Relationships for user actions
    invited_by: Mapped[Optional["User"]] = relationship(foreign_keys=[invited_by_user_id])
    approved_by: Mapped[Optional["User"]] = relationship(foreign_keys=[approved_by_admin_id])
    revoked_by: Mapped[Optional["User"]] = relationship(foreign_keys=[revoked_by_admin_id])
    accepted_by_user: Mapped[Optional["User"]] = relationship(foreign_keys=[accepted_by_user_id])

    declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decline_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self):
        return f"<Invitation(id={self.id}, email='{self.email}', status='{self.status}')>" 