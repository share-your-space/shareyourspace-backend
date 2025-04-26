from sqlalchemy import Boolean, Column, Integer, String, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .space import SpaceNode, Workstation # noqa: F401
    from .organization import Company, Startup # noqa: F401

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, index=True, nullable=True)
    # e.g., 'SYS_ADMIN', 'CORP_ADMIN', 'CORP_EMPLOYEE', 'STARTUP_ADMIN', 'STARTUP_MEMBER', 'FREELANCER'
    role = Column(String, nullable=False)
    # e.g., 'PENDING_VERIFICATION', 'WAITLISTED', 'PENDING_ONBOARDING', 'ACTIVE', 'SUSPENDED', 'BANNED'
    status = Column(String, nullable=False, index=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Added ForeignKeys and Relationships
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    startup_id = Column(Integer, ForeignKey("startups.id"), nullable=True)

    company = relationship("Company", back_populates="members")
    startup = relationship("Startup", back_populates="members")

    # One-to-one relationship to UserProfile
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")

    # Relationships for tokens (if they exist)
    verification_tokens = relationship("VerificationToken", back_populates="user")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user")

    space_id = Column(Integer, ForeignKey('spacenodes.id'), nullable=True, index=True)
    # Temporarily removed until PromoCode model exists
    # applied_promo_code_id = Column(Integer, ForeignKey('promocodes.id'), nullable=True)

    # Relationships
    # Relationship to the SpaceNode this user manages (if they are a Corp Admin)
    # Corresponds to `admin = relationship("User", back_populates="managed_space")` in SpaceNode
    # Explicitly state the foreign key to resolve ambiguity
    managed_space = relationship(
        "SpaceNode", 
        foreign_keys="[SpaceNode.corporate_admin_id]", 
        back_populates="admin", 
        uselist=False
    )

    # Relationship to the SpaceNode this user BELONGS TO
    # Uses the space_id foreign key on this User model
    space = relationship(
        "SpaceNode", 
        foreign_keys=[space_id],
        back_populates="users"
    )

    # Relationship to the Workstation this user is assigned to
    # Corresponds to `assigned_user = relationship("User", back_populates="assigned_workstation")` in Workstation
    assigned_workstation = relationship("Workstation", back_populates="assigned_user", uselist=False)

    # Define relationships for Company/Startup Admins/Members if needed
    # company = relationship("Company", back_populates="admin")
    # startup = relationship("Startup", back_populates="admin")
    # member_of_company = relationship("Company", secondary="user_company_association", back_populates="members")
    # member_of_startup = relationship("Startup", secondary="user_startup_association", back_populates="members")

    # Placeholder for Verification/Reset Tokens relationships if needed for cascade delete etc.
    # verification_tokens = relationship("VerificationToken", back_populates="user", cascade="all, delete-orphan")
    # password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

    # Relationships for Referrals
    # referrals_made = relationship("Referral", foreign_keys="[Referral.referrer_id]", back_populates="referrer", cascade="all, delete-orphan")
    # referral_received = relationship("Referral", foreign_keys="[Referral.referred_user_id]", back_populates="referred_user", uselist=False)

    # Relationships for Blocks/Reports
    # blocks_made = relationship("Block", foreign_keys="[Block.blocker_id]", back_populates="blocker", cascade="all, delete-orphan")
    # blocks_received = relationship("Block", foreign_keys="[Block.blocked_user_id]", back_populates="blocked_user", cascade="all, delete-orphan")
    # reports_made = relationship("Report", foreign_keys="[Report.reporter_id]", back_populates="reporter", cascade="all, delete-orphan")
    # reports_received = relationship("Report", foreign_keys="[Report.reported_user_id]", back_populates="reported_user") 