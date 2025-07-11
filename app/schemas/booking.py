from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from app.schemas.user import UserSimpleInfo
from app.schemas.workstation import Workstation

class Booking(BaseModel):
    id: int
    start_date: datetime
    end_date: Optional[datetime] = None
    user: UserSimpleInfo
    workstation: Workstation

    class Config:
        orm_mode = True
