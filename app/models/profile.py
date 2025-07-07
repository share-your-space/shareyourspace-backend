from sqlalchemy import Column, Integer, String, Text, ForeignKey, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector
from typing import Optional, List

from app.db.base_class import Base
# Import the enum from the new location
from .enums import ContactVisibility

# REMOVED Enum definition from here
# import enum
# class ContactVisibility(str, enum.Enum):
#     PRIVATE = "private"
#     CONNECTIONS = "connections"
#     PUBLIC = "public"

class UserProfile(Base):
    __tablename__ = "user_profiles"
    # Add extend_existing=True to handle potential double registration
    __table_args__ = {'extend_existing': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)

    # Professional Info
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Use the imported enum
    contact_info_visibility = Column(SQLEnum(ContactVisibility, name="contact_visibility_enum", create_type=False), nullable=False, default=ContactVisibility.CONNECTIONS)
    # Add other fields back based on schema and embedding logic (ensure ARRAY is imported)
    skills_expertise: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    industry_focus: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    project_interests_goals = Column(Text, nullable=True)
    collaboration_preferences = Column(ARRAY(String), nullable=True)
    tools_technologies = Column(ARRAY(String), nullable=True)
    linkedin_profile_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Visuals
    profile_picture_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cover_photo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Status
    is_profile_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="profile")

    # Add other profile fields here as defined in Step 2.3