from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

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

    # Relationship to Users (Members + Admin)
    members = relationship("User", back_populates="startup") 