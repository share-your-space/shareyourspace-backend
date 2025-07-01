from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, 
    Enum as SQLAlchemyEnum, Text, and_
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, remote
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy.sql import func
from datetime import datetime
from app.db.base_class import Base
from app.models.enums import WorkstationStatus

if TYPE_CHECKING:
    from .user import User
    from .organization import Company, Startup
    from .invitation import Invitation
    from .interest import Interest

class SpaceNode(Base):
    __tablename__ = 'spacenodes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    total_workstations: Mapped[int] = mapped_column(Integer, default=0)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id"))
    corporate_admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    
    company: Mapped[Optional["Company"]] = relationship(back_populates="spaces")
    corporate_admin: Mapped[Optional["User"]] = relationship(foreign_keys=[corporate_admin_id], back_populates="managed_space")
    users: Mapped[List["User"]] = relationship("User", foreign_keys="[User.space_id]", back_populates="space")
    startups: Mapped[List["Startup"]] = relationship(back_populates="space")
    workstations: Mapped[List["Workstation"]] = relationship(back_populates="space", cascade="all, delete-orphan")
    invitations: Mapped[List["Invitation"]] = relationship(back_populates="space")
    interests: Mapped[List["Interest"]] = relationship(back_populates="space", cascade="all, delete-orphan")
    assignments: Mapped[List["WorkstationAssignment"]] = relationship("WorkstationAssignment", back_populates="space")

    def __repr__(self) -> str:
        return f"<SpaceNode(id={self.id}, name='{self.name}')>"

class Workstation(Base):
    __tablename__ = 'workstations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String)
    space_id: Mapped[int] = mapped_column(ForeignKey('spacenodes.id'))
    status: Mapped[WorkstationStatus] = mapped_column(SQLAlchemyEnum(WorkstationStatus, name="workstation_status_enum"), default=WorkstationStatus.AVAILABLE)
    
    space: Mapped["SpaceNode"] = relationship(back_populates="workstations")
    assignments: Mapped[List["WorkstationAssignment"]] = relationship(back_populates="workstation", cascade="all, delete-orphan")
    active_assignment: Mapped[Optional["WorkstationAssignment"]] = relationship(
        "WorkstationAssignment",
        primaryjoin=lambda: and_(
            Workstation.id == remote(WorkstationAssignment.workstation_id),
            remote(WorkstationAssignment.end_date).is_(None)
        ),
        uselist=False,
        viewonly=True
    )

    def __repr__(self) -> str:
        return f"<Workstation(id={self.id}, name='{self.name}')>"

class WorkstationAssignment(Base):
    __tablename__ = 'workstation_assignments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    workstation_id: Mapped[int] = mapped_column(ForeignKey('workstations.id'))
    space_id: Mapped[int] = mapped_column(ForeignKey('spacenodes.id'))
    start_date: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="assignments")
    workstation: Mapped["Workstation"] = relationship(back_populates="assignments")
    space: Mapped["SpaceNode"] = relationship("SpaceNode", back_populates="assignments")

    def __repr__(self) -> str:
        return f"<WorkstationAssignment(id={self.id}, user_id={self.user_id}, workstation_id={self.workstation_id})>" 