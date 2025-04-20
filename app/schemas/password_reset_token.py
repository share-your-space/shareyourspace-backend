from pydantic import BaseModel
from datetime import datetime

class PasswordResetTokenBase(BaseModel):
    token: str
    user_id: int
    expires_at: datetime

class PasswordResetTokenCreate(PasswordResetTokenBase):
    pass

class PasswordResetTokenRead(PasswordResetTokenBase):
    id: int

    class Config:
        from_attributes = True

# Schema for the request body of /request-password-reset
class RequestPasswordResetRequest(BaseModel):
    email: str

# Schema for the request body of /reset-password
class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str 