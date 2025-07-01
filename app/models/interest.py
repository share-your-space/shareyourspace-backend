import enum
from sqlalchemy import Column, Integer, ForeignKey, Enum as SQLEnum, DateTime, func
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.base_class import Base
from typing import TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from .user import User
    from .space import SpaceNode

class InterestStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class Interest(Base):
    __tablename__ = "interests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    space_id: Mapped[int] = mapped_column(ForeignKey("spacenodes.id"), nullable=False)
    
    status: Mapped[InterestStatus] = mapped_column(
        SQLEnum(InterestStatus, name='intereststatus', create_type=False),
        default=InterestStatus.PENDING,
        nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="interests")
    space: Mapped["SpaceNode"] = relationship(back_populates="interests") 