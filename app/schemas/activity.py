from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class Activity(BaseModel):
    id: str
    type: str
    timestamp: datetime
    description: str
    user_avatar_url: Optional[str] = None
    link: Optional[str] = None

class PaginatedActivityResponse(BaseModel):
    activities: List[Activity]
    total: int
