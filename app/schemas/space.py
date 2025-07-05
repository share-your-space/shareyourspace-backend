from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from typing import List, Optional, Union, TYPE_CHECKING, Any
from enum import Enum
from pydantic import ConfigDict
from datetime import datetime

from app.models.enums import UserRole, WorkstationStatus as WorkstationStatusEnum, UserStatus
if TYPE_CHECKING:
    from .user import User, BasicUser
from .organization import Startup, BasicStartup, Company

class Space(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    company_id: Optional[int] = None
    total_workstations: int = 0
    headline: Optional[str] = None
    amenities: Optional[List[str]] = None
    house_rules: Optional[str] = None
    vibe: Optional[str] = None
    opening_hours: Optional[dict] = None
    key_highlights: Optional[List[str]] = None
    neighborhood_description: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True
    )

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
    details: Startup
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
        from_attributes = True

# Potentially a response schema for assignment, or just a success message
class WorkstationAssignmentResponse(BaseModel):
    id: int # Changed from assignment_id to match the ORM model's PK
    user_id: int
    workstation_id: int
    space_id: int
    start_date: datetime

    class Config:
        from_attributes = True

# Schema for detailed workstation info, including occupant
class WorkstationTenantInfo(BaseModel):
    user_id: int = Field(validation_alias='id')
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
        from_attributes = True

class SpaceWorkstationListResponse(BaseModel):
    workstations: List[WorkstationDetail]

class WorkstationUnassignRequest(BaseModel):
    workstation_id: int
    # Alternatively, could use assignment_id if that's preferred for unassignment
    # assignment_id: int

    class Config:
        from_attributes = True

# New Schemas for Workstation CRUD by Corp Admin
class WorkstationCreate(BaseModel):
    name: str
    status: Optional[WorkstationStatus] = WorkstationStatus.AVAILABLE

class WorkstationUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[WorkstationStatus] = None
# End New Schemas

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
        from_attributes = True

class WorkstationStatusUpdateRequest(BaseModel):
    status: WorkstationStatusEnum

    class Config:
        from_attributes = True

# Schema for listing all users within a specific space
class SpaceUsersListResponse(BaseModel):
    users: List[BasicUser]

    model_config = ConfigDict(
        from_attributes=True # Allows reading data from ORM models
    )

# New schema for connection statistics
class SpaceConnectionStatsResponse(BaseModel):
    total_tenants: int
    total_workstations: int
    occupied_workstations: int
    connections_this_month: int

# Information about a user's current workstation assignment
class UserWorkstationInfo(BaseModel):
    workstation_id: int
    workstation_name: str
    assignment_start_date: datetime # from WorkstationAssignment model
    # assignment_id: Optional[int] = None # If needed from WorkstationAssignment model
    model_config = ConfigDict(from_attributes=True)

class AddUserToSpaceRequest(BaseModel):
    user_id: int
    role: UserRole
    startup_id: Optional[int] = None

class BrowseableSpace(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    headline: Optional[str] = None
    cover_image_url: Optional[str] = None
    total_workstations: int = 0
    company_name: str
    company_id: Optional[int] = None
    interest_status: str # 'interested' | 'not_interested' | 'unavailable'

    class Config:
        from_attributes = True

class BrowseableSpaceListResponse(BaseModel):
    spaces: List[BrowseableSpace]

# Schemas for the response when a Corp Admin creates their first space
class SpaceCreationUserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    status: UserStatus
    company_id: Optional[int] = None
    space_id: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)

class SpaceCreationResponse(BaseModel):
    space: BasicSpace
    user: SpaceCreationUserResponse

class SpaceImageCreate(BaseModel):
    space_id: int
    image_url: str
    description: Optional[str] = None

class SpaceImageSchema(BaseModel):
    id: int
    image_url: str
    created_at: datetime
    description: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True
    )

class SpaceProfile(BaseModel):
    id: int
    name: str
    headline: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    amenities: Optional[List[str]] = None
    house_rules: Optional[str] = None
    images: List[SpaceImageSchema] = []
    vibe: Optional[str] = None
    opening_hours: Optional[dict] = None
    key_highlights: Optional[List[str]] = None
    neighborhood_description: Optional[str] = None
    company: Optional[BasicCompany] = None

    model_config = ConfigDict(
        from_attributes=True
    )

class SpaceProfileUpdate(BaseModel):
    name: Optional[str] = None
    headline: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    amenities: Optional[List[str]] = None
    house_rules: Optional[str] = None
    vibe: Optional[str] = None
    opening_hours: Optional[dict] = None
    key_highlights: Optional[List[str]] = None
    neighborhood_description: Optional[str] = None