import enum
from sqlalchemy import Column, Integer, ForeignKey, DateTime, func, Enum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import TYPE_CHECKING, Optional
from app.db.base_class import Base
from app.models.enums import InterestStatus
from datetime import datetime

if TYPE_CHECKING:
    from .user import User
    from .space import SpaceNode

class Interest(Base):
    __tablename__ = 'interests'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    space_id: Mapped[int] = mapped_column(ForeignKey('spacenodes.id'))
    startup_id: Mapped[Optional[int]] = mapped_column(ForeignKey('startups.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    status: Mapped[InterestStatus] = mapped_column(Enum(InterestStatus), default=InterestStatus.PENDING, nullable=False)

    user: Mapped["User"] = relationship(back_populates="interests")
    space: Mapped["SpaceNode"] = relationship(back_populates="interests") 