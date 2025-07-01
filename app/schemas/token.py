from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from .user import User

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenWithUser(Token):
    user: User

class TokenPayload(BaseModel):
    sub: Optional[str] = None # 'sub' is the standard JWT field for subject (usually user identifier)
    user_id: Optional[int] = None
    startup_id: Optional[int] = None
    company_id: Optional[int] = None
    role: Optional[str] = None
    purpose: Optional[str] = None # For special-purpose tokens like 'onboarding'

# For creating SetPasswordToken internally
class SetPasswordTokenCreateInternal(BaseModel):
    user_id: int
    token: str
    expires_at: datetime

# For the /set-initial-password endpoint request body
class SetInitialPasswordRequest(BaseModel):
    token: str
    new_password: str

class OnboardingToken(BaseModel):
    message: str
    onboarding_token: str
    token_type: str = "bearer" 