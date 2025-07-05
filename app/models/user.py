from sqlalchemy import Boolean, Column, Integer, String, DateTime, func, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .space import SpaceNode, Workstation, WorkstationAssignment
    from .organization import Company, Startup
    from .chat import Conversation
    from .invitation import Invitation
    from .referral import Referral
    from .notification import Notification
    from .interest import Interest
    from .connection import Connection
    from .verification_token import VerificationToken
    from .password_reset_token import PasswordResetToken
    from .profile import UserProfile

from app.db.base_class import Base
from .enums import UserRole, UserStatus

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, index=True, nullable=True)
    role = Column(SQLEnum(UserRole), nullable=True)
    status = Column(SQLEnum(UserStatus), nullable=False, index=True, default=UserStatus.PENDING_VERIFICATION)
    is_active = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    startup_id = Column(Integer, ForeignKey("startups.id"), nullable=True)
    space_id = Column(Integer, ForeignKey('spacenodes.id'), nullable=True, index=True)
    referral_code = Column(String, unique=True, index=True, nullable=True)
    community_badge = Column(String, nullable=True)

    company = relationship("Company", back_populates="direct_employees")
    startup = relationship("Startup", back_populates="direct_members")

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")

    verification_tokens = relationship("VerificationToken", back_populates="user", cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

    space = relationship(
        "SpaceNode", 
        foreign_keys=[space_id],
        back_populates="users"
    )

    assignments = relationship("WorkstationAssignment", back_populates="user", cascade="all, delete-orphan")
    sent_connections = relationship("Connection", foreign_keys="app.models.connection.Connection.requester_id", back_populates="requester", cascade="all, delete-orphan")
    received_connections = relationship("Connection", foreign_keys="app.models.connection.Connection.recipient_id", back_populates="recipient", cascade="all, delete-orphan")
    conversations = relationship("Conversation", secondary="conversation_participants", back_populates="participants")
    referrals_made = relationship("Referral", foreign_keys="app.models.referral.Referral.referrer_id", back_populates="referrer", cascade="all, delete-orphan")
    referral_received = relationship("Referral", foreign_keys="app.models.referral.Referral.referred_user_id", back_populates="referred_user", uselist=False, cascade="all, delete-orphan")
    notifications = relationship("Notification", foreign_keys="app.models.notification.Notification.user_id", back_populates="user", cascade="all, delete-orphan")
    interests = relationship("Interest", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>" 