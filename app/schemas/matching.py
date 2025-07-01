from pydantic import BaseModel
from typing import List, Optional

from .user_profile import UserProfile # Import the existing UserProfile schema
 
class MatchResult(BaseModel):
    profile: Optional[UserProfile] = None
    score: Optional[float] = None
    reasons: Optional[List[str]] = None
    message: Optional[str] = None

    class Config:
        from_attributes = True 