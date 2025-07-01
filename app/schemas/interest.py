from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.models.interest import InterestStatus
from app.schemas.user import UserDetail as UserDetailSchema
from app.schemas.organization import Startup as StartupSchema

class InterestBase(BaseModel):
    space_id: int
    user_id: int
    status: Optional[InterestStatus] = InterestStatus.PENDING

class InterestCreate(BaseModel):
    space_id: int

class InterestUpdate(BaseModel):
    status: Optional[InterestStatus] = None

class InterestInDBBase(InterestBase):
    id: int
    status: InterestStatus
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

class Interest(InterestInDBBase):
    pass

# For returning detailed interest info to Corp Admins
class InterestDetail(BaseModel):
    id: int
    status: InterestStatus
    user: UserDetailSchema
    startup: Optional[StartupSchema] = None

class InterestResponse(BaseModel):
    interests: List[InterestDetail] 