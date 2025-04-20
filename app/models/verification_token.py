import sqlalchemy as sa
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone

from app.db.base_class import Base

class VerificationToken(Base):
    __tablename__ = 'verification_tokens'

    id: int = sa.Column(sa.Integer, primary_key=True, index=True)
    user_id: int = sa.Column(sa.Integer, sa.ForeignKey('users.id'), nullable=False)
    token: str = sa.Column(sa.String, unique=True, index=True, nullable=False)
    expires_at: datetime = sa.Column(sa.DateTime(timezone=True), nullable=False)
    created_at: datetime = sa.Column(sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User")

    @staticmethod
    def get_default_expiry() -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=1) # Token valid for 1 hour 