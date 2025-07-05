from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.enums import InterestStatus
from .user import User

class InterestBase(BaseModel):
    space_id: int

class InterestCreate(InterestBase):
    pass

class InterestUpdate(BaseModel):
    status: InterestStatus

class InterestInDBBase(InterestBase):
    id: int
    user_id: int
    status: InterestStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class Interest(InterestInDBBase):
    user: User

class InterestStatusResponse(BaseModel):
    has_expressed_interest: bool 