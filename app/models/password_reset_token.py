import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base_class import Base

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User") # Optional relationship back to User

    @staticmethod
    def get_default_expiry() -> datetime:
        """Returns the default expiration time for a token (e.g., 1 hour from now)."""
        return datetime.now(timezone.utc) + timedelta(hours=1)

    @staticmethod
    def generate_token() -> str:
         """Generates a secure random token."""
         return secrets.token_urlsafe(32) 