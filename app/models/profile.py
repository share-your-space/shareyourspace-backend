from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db.base_class import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False)

    title = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    # Placeholder for detailed fields from Step 2.3
    # skills_expertise = Column(ARRAY(String), nullable=True) 
    # industry_focus = Column(String, nullable=True) 
    # ... etc.

    # Add the vector column
    profile_vector = Column(Vector(768), nullable=True)

    # Relationship back to User
    user = relationship("User", back_populates="profile")

    # Add other profile fields here as defined in Step 2.3 