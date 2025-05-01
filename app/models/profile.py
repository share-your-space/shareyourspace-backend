from sqlalchemy import Column, Integer, String, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector

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

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False)

    title = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    # Use the imported enum
    contact_info_visibility = Column(SQLEnum(ContactVisibility, name="contact_visibility_enum", create_type=False), nullable=False, default=ContactVisibility.CONNECTIONS)
    # Add other fields back based on schema and embedding logic (ensure ARRAY is imported)
    skills_expertise = Column(ARRAY(String), nullable=True)
    industry_focus = Column(ARRAY(String), nullable=True)
    project_interests_goals = Column(Text, nullable=True)
    collaboration_preferences = Column(ARRAY(String), nullable=True)
    tools_technologies = Column(ARRAY(String), nullable=True)
    linkedin_profile_url = Column(String, nullable=True)
    profile_picture_url = Column(String, nullable=True)
    profile_vector = Column(Vector(768), nullable=True)

    # Relationship back to User (one-to-one)
    # Add explicit foreign_keys based on the FK defined in this model
    user = relationship(
        "app.models.user.User", 
        foreign_keys=[user_id], # Specify FK column from this model
        back_populates="profile"
    )

    # Add other profile fields here as defined in Step 2.3