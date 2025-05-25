from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped
from sqlalchemy.sql import func
from typing import TYPE_CHECKING, List

from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User # noqa F401
    from .space import SpaceNode # Add this import for type hinting
    from .invitation import Invitation # Import Invitation for relationship

class Company(Base):
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    logo_url = Column(String, nullable=True)
    industry_focus = Column(String, nullable=True) # Consider ARRAY(String) later if multiple needed
    description = Column(Text, nullable=True)
    website = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to Users (Employees + Admin)
    members = relationship("User", back_populates="company")

    # Relationship to SpaceNodes managed/owned by this company
    spaces = relationship("SpaceNode", back_populates="company")

class Startup(Base):
    __tablename__ = 'startups'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    logo_url = Column(String, nullable=True)
    industry_focus = Column(String, nullable=True) # Consider ARRAY(String) later if multiple needed
    description = Column(Text, nullable=True)
    mission = Column(Text, nullable=True)
    website = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Foreign Key to SpaceNode
    space_id = Column(Integer, ForeignKey("spacenodes.id"), nullable=False, index=True)

    # Relationship to SpaceNode
    space = relationship("SpaceNode", back_populates="startups")

    # Relationship to Users (Members + Admin)
    members = relationship("User", back_populates="startup")

    # Relationship to Invitations sent by this startup
    invitations: Mapped[List["Invitation"]] = relationship("Invitation", back_populates="startup", cascade="all, delete-orphan") 