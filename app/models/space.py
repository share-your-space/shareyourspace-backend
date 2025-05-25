from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Enum as SQLAlchemyEnum, and_
from sqlalchemy.orm import relationship, foreign, remote
from sqlalchemy.ext.hybrid import hybrid_property

from app.db.base_class import Base
# Ensure User model is available for ForeignKey reference
from .user import User # Adjust import if User model is elsewhere
from .organization import Company # Assuming Company model is here

# Enum for Workstation Status
from app.schemas.space import WorkstationStatus # For status values

class SpaceNode(Base):
    __tablename__ = 'spacenodes' # Using plural table name convention

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    address = Column(String, nullable=True) # Renamed from location_description, or added
    # Allow corporate_admin_id to be NULL initially or for generic spaces
    corporate_admin_id = Column(Integer, ForeignKey('users.id'), nullable=True) 
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True) # Added company link
    # total_workstations can be a derived property or removed if workstations are counted dynamically
    # For now, let's keep it as a potential field if it's set manually, or remove if it causes sync issues.
    # total_workstations = Column(Integer, nullable=False, default=0) 
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship to the Corporate Admin (User) - One SpaceNode belongs to one Admin User
    # Explicitly state the foreign key to resolve ambiguity
    admin = relationship(
        "User", 
        foreign_keys=[corporate_admin_id], # Specify the FK column from this model
        back_populates="managed_space"
    )
    company = relationship("Company", back_populates="spaces") # Add relationship to Company

    # Relationship to Workstations - One SpaceNode has many Workstations
    workstations = relationship("Workstation", back_populates="space_node", cascade="all, delete-orphan")

    # Relationship to Users belonging to this SpaceNode
    # Corresponds to `space = relationship(...)` in User model
    users = relationship("User", back_populates="space", foreign_keys="[User.space_id]")
    assignments = relationship("WorkstationAssignment", back_populates="space_node", cascade="all, delete-orphan")

    # Relationship to Startups in this SpaceNode
    startups = relationship("Startup", back_populates="space", cascade="all, delete-orphan")

class Workstation(Base):
    __tablename__ = 'workstations'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True, default="Workstation") # Added name
    space_id = Column(Integer, ForeignKey('spacenodes.id'), nullable=False)
    # Status field now uses the Enum from schemas for consistency in values
    status = Column(SQLAlchemyEnum(WorkstationStatus, name="workstation_status_enum"), 
                    default=WorkstationStatus.AVAILABLE, 
                    nullable=False, 
                    index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship to SpaceNode - Many Workstations belong to one SpaceNode
    space_node = relationship("SpaceNode", back_populates="workstations")

    # All assignments for this workstation (history)
    assignments = relationship("WorkstationAssignment", back_populates="workstation", cascade="all, delete-orphan", lazy="selectin")

    # Relationship for the current, active assignment (if any)
    # This is what `selectinload(models.Workstation.active_assignment)` will use.
    active_assignment = relationship(
        "WorkstationAssignment",
        primaryjoin=lambda: and_(
            Workstation.id == remote(WorkstationAssignment.workstation_id),
            remote(WorkstationAssignment.end_date).is_(None)
        ),
        uselist=False, # one-to-one nature for an *active* assignment
        viewonly=True, # This relationship is for reading the current state
        lazy='selectin' # Efficient loading
    )

class WorkstationAssignment(Base):
    __tablename__ = 'workstation_assignments'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    workstation_id = Column(Integer, ForeignKey('workstations.id'), nullable=False)
    space_id = Column(Integer, ForeignKey('spacenodes.id'), nullable=False) # Denormalized for easier queries
    
    start_date = Column(DateTime, default=func.now(), nullable=False)
    end_date = Column(DateTime, nullable=True) # Null if currently active

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Who created the assignment (optional, e.g. a Corp Admin user)
    # created_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    user = relationship("User", back_populates="assignments") # Changed from assigned_workstations
    workstation = relationship("Workstation", back_populates="assignments", foreign_keys=[workstation_id])
    space_node = relationship("SpaceNode", back_populates="assignments")
    # created_by = relationship("User", foreign_keys=[created_by_id])


# Need to update User model to have:
# managed_space = relationship("SpaceNode", back_populates="admin", foreign_keys="[SpaceNode.corporate_admin_id]", uselist=False)
# space = relationship("SpaceNode", back_populates="users", foreign_keys="[User.space_id]")
# assignments = relationship("WorkstationAssignment", back_populates="user")
# (and remove assigned_workstation if it was there) 