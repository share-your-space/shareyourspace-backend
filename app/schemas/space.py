from pydantic import BaseModel, EmailStr
from typing import List, Optional, Union
from enum import Enum
from pydantic import ConfigDict
from datetime import datetime

# Schemas for app.schemas.user.User, assuming it exists and has relevant fields like id, full_name, email, role
# This is a simplified placeholder. You'd import your actual User schema.
class BasicUser(BaseModel):
    id: int
    full_name: Optional[str] = None
    email: EmailStr
    role: str

    model_config = ConfigDict(
        from_attributes=True # Allows reading data from ORM models
    )

# Schemas for app.schemas.organization.Startup, assuming it exists and has relevant fields like id, name
# This is a simplified placeholder. You'd import your actual Startup schema.
class BasicStartup(BaseModel):
    id: int
    name: str
    # Add other relevant startup details to show to Corp Admin
    # e.g., mission: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True # Allows reading data from ORM models
    )

# Basic Space Information
class BasicSpace(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

class StartupTenantInfo(BaseModel):
    type: str = "startup"
    details: BasicStartup
    member_count: int # Number of members from this startup in the admin's space
    # You might want to add a list of members here too, or a link to view them

class FreelancerTenantInfo(BaseModel):
    type: str = "freelancer"
    details: BasicUser # The Freelancer user object

# Union type for the response list
TenantInfo = Union[StartupTenantInfo, FreelancerTenantInfo]

class SpaceTenantResponse(BaseModel):
    tenants: List[TenantInfo]

# Schemas for Workstation info
class WorkstationStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"

class WorkstationAssignmentRequest(BaseModel):
    user_id: int
    workstation_id: int
    # Optional: Add start_date and end_date if assignments are time-bound
    # start_date: Optional[date] = None
    # end_date: Optional[date] = None

    class Config:
        orm_mode = True

# Potentially a response schema for assignment, or just a success message
class WorkstationAssignmentResponse(BaseModel):
    assignment_id: int # Assuming an ID for the assignment itself
    user_id: int
    workstation_id: int
    space_id: int
    # start_date: Optional[date]
    # end_date: Optional[date]

    class Config:
        orm_mode = True

# Schema for detailed workstation info, including occupant
class WorkstationTenantInfo(BaseModel):
    user_id: int
    full_name: Optional[str]
    email: Optional[EmailStr]
    # Add any other relevant user details you want to show

    model_config = ConfigDict(
        from_attributes=True # Allows reading data from ORM models
    )

class WorkstationDetail(BaseModel):
    id: int
    name: str
    status: WorkstationStatus # Reuse the Enum
    space_id: int
    occupant: Optional[WorkstationTenantInfo] = None # Details of the user occupying it

    class Config:
        orm_mode = True

class SpaceWorkstationListResponse(BaseModel):
    workstations: List[WorkstationDetail]

class WorkstationUnassignRequest(BaseModel):
    workstation_id: int
    # Alternatively, could use assignment_id if that's preferred for unassignment
    # assignment_id: int

    class Config:
        orm_mode = True

# Schema for detailed information about the managed space
class ManagedSpaceDetail(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    total_workstations: int = 0
    occupied_workstations: int = 0
    available_workstations: int = 0
    maintenance_workstations: int = 0
    # Add other relevant space details like amenities, opening hours, etc.
    # amenities: List[str] = []
    company_id: Optional[int] = None # Company that owns/manages this space node

    class Config:
        orm_mode = True

class WorkstationStatusUpdateRequest(BaseModel):
    status: WorkstationStatus # Use the existing Enum

    class Config:
        orm_mode = True

# Schema for listing all users within a specific space
class SpaceUsersListResponse(BaseModel):
    users: List[BasicUser]

    model_config = ConfigDict(
        from_attributes=True # Allows reading data from ORM models
    )

# New schema for connection statistics
class SpaceConnectionStatsResponse(BaseModel):
    total_connections: int
    model_config = ConfigDict(from_attributes=True)

# Information about a user's current workstation assignment
class UserWorkstationInfo(BaseModel):
    workstation_id: int
    workstation_name: str
    assignment_start_date: datetime # from WorkstationAssignment model
    # assignment_id: Optional[int] = None # If needed from WorkstationAssignment model
    model_config = ConfigDict(from_attributes=True) 