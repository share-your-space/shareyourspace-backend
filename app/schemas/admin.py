from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# Re-using User schema, potentially create a specific Admin view later
from .user import User as UserSchema


# Schema for creating a SpaceNode via API
class SpaceCreate(BaseModel):
    name: str
    location_description: Optional[str] = None
    corporate_admin_id: int
    total_workstations: int

# Schema for returning a SpaceNode from API
class Space(SpaceCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # Replaces orm_mode = True

# Schema for the response when listing users (simplified view)
class UserAdminView(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    status: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True 