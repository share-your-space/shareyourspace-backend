from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func, Boolean, Enum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from typing import TYPE_CHECKING, List, Optional
from datetime import datetime

from app.db.base_class import Base
from app.models.enums import UserStatus, TeamSize, StartupStage, UserRole

if TYPE_CHECKING:
    from .user import User
    from .space import SpaceNode
    from .invitation import Invitation

class Company(Base):
    __tablename__ = 'companies'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    industry_focus: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    team_size: Mapped[Optional[TeamSize]] = mapped_column(Enum(TeamSize), nullable=True)
    looking_for: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    social_media_links: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    verified_domains: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    allow_domain_auto_join: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    direct_employees: Mapped[List["User"]] = relationship(back_populates="company")
    spaces: Mapped[List["SpaceNode"]] = relationship(back_populates="company")
    invitations: Mapped[List["Invitation"]] = relationship(back_populates="company", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Company(id={self.id}, name='{self.name}')>"

class Startup(Base):
    __tablename__ = 'startups'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    industry_focus: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mission: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stage: Mapped[Optional[StartupStage]] = mapped_column(Enum(StartupStage), nullable=True)
    team_size: Mapped[Optional[TeamSize]] = mapped_column(Enum(TeamSize), nullable=True)
    looking_for: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    social_media_links: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    pitch_deck_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.WAITLISTED, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    member_slots_allocated: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    member_slots_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    space_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("spacenodes.id"), nullable=True, index=True)

    direct_members: Mapped[List["User"]] = relationship(back_populates="startup")
    space: Mapped[Optional["SpaceNode"]] = relationship(back_populates="startups")
    invitations: Mapped[List["Invitation"]] = relationship(back_populates="startup", cascade="all, delete-orphan")

# Association tables for many-to-many relationships
# These will be defined when we fully implement employee/member association logic.
# For now, we'll link users to companies/startups via their profile or a direct FK.

# Placeholder for User updates needed for these relationships
# In app/models/user.py, you would add:
# managed_company = relationship("Company", back_populates="corp_admin", uselist=False) # If one admin per company
# companies = relationship("Company", secondary="user_company_association", back_populates="employees")
# managed_startup = relationship("Startup", back_populates="startup_admin", uselist=False) # If one admin per startup
# startups = relationship("Startup", secondary="user_startup_association", back_populates="members") 