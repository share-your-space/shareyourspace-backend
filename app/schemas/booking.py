from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from .user import BasicUser

class Booking(BaseModel):
    id: int
    user_id: int
    workstation_id: int
    start_time: datetime
    end_time: datetime
    status: str
    user: BasicUser

    class Config:
        from_attributes = True
