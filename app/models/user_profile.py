from sqlalchemy import Column, Integer, String, Text, ForeignKey, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY

from app.db.base_class import Base

# Define visibility options using Python Enum for potential validation elsewhere
import enum
class ContactVisibility(str, enum.Enum):
    PRIVATE = "private"
    CONNECTIONS = "connections"
    PUBLIC = "public"

class UserProfile(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False)

    title = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    contact_info_visibility = Column(SQLEnum(ContactVisibility, name="contact_visibility_enum"), nullable=False, default=ContactVisibility.CONNECTIONS)
    skills_expertise = Column(ARRAY(String), nullable=True)
    industry_focus = Column(ARRAY(String), nullable=True)
    project_interests_goals = Column(Text, nullable=True)
    collaboration_preferences = Column(ARRAY(String), nullable=True)
    tools_technologies = Column(ARRAY(String), nullable=True)
    linkedin_profile_url = Column(String, nullable=True)
    profile_picture_url = Column(String, nullable=True)
    # profile_vector = Column(Vector(768), nullable=True) # Add later in Matching phase

    # Relationship back to User (one-to-one)
    user = relationship("User", back_populates="profile") 