from sqlalchemy import Boolean, Column, Integer, String, DateTime, func

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, index=True)
    # e.g., 'SYS_ADMIN', 'CORP_ADMIN', 'CORP_EMPLOYEE', 'STARTUP_ADMIN', 'STARTUP_MEMBER', 'FREELANCER'
    role = Column(String, nullable=False)
    # e.g., 'PENDING_VERIFICATION', 'WAITLISTED', 'PENDING_ONBOARDING', 'ACTIVE', 'SUSPENDED', 'BANNED'
    status = Column(String, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()) 