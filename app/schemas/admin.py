from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# Re-using User schema, potentially create a specific Admin view later
from .user import User as UserSchema


# Schema for assigning a user to a space
class UserAssignSpace(BaseModel):
    space_id: Optional[int] = None # Allow unassigning by passing null/None

# Schema for changing user status
class UserStatusUpdate(BaseModel):
    # Add validation? Should only allow valid status strings?
    status: str = Field(..., description="The new status for the user.") 

# Schema for creating a SpaceNode via API
class SpaceCreate(BaseModel):
    name: str
    location_description: Optional[str] = None
    corporate_admin_id: Optional[int] = None
    total_workstations: int

# Schema for creating a simple SpaceNode (without requiring corp admin)
class SimpleSpaceCreate(BaseModel):
    name: str = Field(..., description="Name of the pilot/test space")
    total_workstations: int = Field(..., gt=0, description="Number of workstations available")

# Schema for returning a SpaceNode from API
class Space(BaseModel):
    id: int
    name: str
    location_description: Optional[str] = None
    corporate_admin_id: Optional[int] = None
    total_workstations: int
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
    space_id: Optional[int] = None # Include space_id

    class Config:
        from_attributes = True 