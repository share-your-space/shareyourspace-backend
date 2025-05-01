from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base
# Ensure User model is available for ForeignKey reference
from .user import User # Adjust import if User model is elsewhere

class SpaceNode(Base):
    __tablename__ = 'spacenodes' # Using plural table name convention

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    location_description = Column(String, nullable=True)
    # Allow corporate_admin_id to be NULL initially or for generic spaces
    corporate_admin_id = Column(Integer, ForeignKey('users.id'), nullable=True) 
    total_workstations = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship to the Corporate Admin (User) - One SpaceNode belongs to one Admin User
    # Explicitly state the foreign key to resolve ambiguity
    admin = relationship(
        "User", 
        foreign_keys=[corporate_admin_id], # Specify the FK column from this model
        back_populates="managed_space"
    )

    # Relationship to Workstations - One SpaceNode has many Workstations
    workstations = relationship("Workstation", back_populates="space_node", cascade="all, delete-orphan")

    # Relationship to Users belonging to this SpaceNode
    # Corresponds to `space = relationship(...)` in User model
    users = relationship("User", back_populates="space", foreign_keys="[User.space_id]")

class Workstation(Base):
    __tablename__ = 'workstations'

    id = Column(Integer, primary_key=True, index=True)
    space_id = Column(Integer, ForeignKey('spacenodes.id'), nullable=False)
    status = Column(String, default='Available', nullable=False, index=True) # e.g., 'Available', 'Occupied', 'Reserved'
    assigned_user_id = Column(Integer, ForeignKey('users.id'), nullable=True) # FK to User, nullable
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship to SpaceNode - Many Workstations belong to one SpaceNode
    space_node = relationship("SpaceNode", back_populates="workstations")

    # Relationship to assigned User - One Workstation can be assigned to one User
    assigned_user = relationship("User", back_populates="assigned_workstation") # Define "assigned_workstation" on User model 