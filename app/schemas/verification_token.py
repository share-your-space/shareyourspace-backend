from pydantic import BaseModel
from datetime import datetime

# Schema for creating a VerificationToken
class VerificationTokenCreate(BaseModel):
    user_id: int
    token: str
    expires_at: datetime

# Schema for reading a VerificationToken (if needed)
class VerificationToken(VerificationTokenCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True # Pydantic v2 uses this instead of orm_mode 