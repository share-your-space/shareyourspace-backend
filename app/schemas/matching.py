from pydantic import BaseModel
from typing import List, Optional

from .user_profile import UserProfile # Import the existing UserProfile schema
 
class MatchResult(BaseModel):
    profile: UserProfile
    score: float # Combined ranking score (higher is better)
    reasons: List[str] # List of reasons for the match 