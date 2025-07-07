from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import List, Optional
from datetime import datetime
from app.models.enums import UserStatus, UserRole

# Re-using User schema, potentially create a specific Admin view later
from .user import User as UserSchema
from .organization import Startup as StartupSchema, BasicCompany, BasicStartup
from .user_profile import UserProfile
from .space import BasicSpace, UserWorkstationInfo


# Schema for assigning a user to a space
class UserAssignSpace(BaseModel):
    space_id: Optional[int] = None # Allow unassigning by passing null/None

# Schema for changing user status
class UserStatusUpdate(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    space_id: Optional[int] = None

# Schema for creating a SpaceNode via API
class SpaceCreate(BaseModel):
    name: str
    address: Optional[str] = None
    company_id: Optional[int] = None # As per SpaceNode model
    total_workstations: int

# Schema for creating a simple SpaceNode (without requiring corp admin)
class SimpleSpaceCreate(BaseModel):
    name: str = Field(..., description="Name of the pilot/test space")
    address: str = Field(..., description="Address of the space")
    total_workstations: int = Field(..., gt=0, description="Number of workstations available")

# Schema for returning a SpaceNode from API
class Space(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
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

class SpaceUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    total_workstations: Optional[int] = Field(None, gt=0) # Ensure positive if provided

class SpaceAssignAdmin(BaseModel):
    corporate_admin_id: int = Field(..., description="The User ID of the new Corporate Admin for this space.")

# Schema for paginated list of users in admin view
class PaginatedUserAdminView(BaseModel):
    total: int
    users: List[UserAdminView]
    page: int
    size: int

class PlatformStats(BaseModel):
    total_users: int
    active_users: int
    users_pending_verification: int
    users_waitlisted: int
    users_pending_onboarding: int
    users_suspended: int
    users_banned: int
    total_spaces: int
    total_connections_made: int
    # Placeholder for more stats, can be expanded based on DB capabilities
    # conversion_rates: Optional[dict] = None 
    # revenue_metrics: Optional[dict] = None
    # agent_usage_metrics: Optional[dict] = None
    # referral_rates: Optional[dict] = None

    class Config:
        from_attributes = True 

class AISearchRequest(BaseModel):
    query: str

class PendingCorporateUser(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    # company_name: Optional[str] = None # This might be on UserCreate or UserProfile
    status: UserStatus # Should be PENDING_ONBOARDING
    role: UserRole # Should be the initial role they signed up with
    created_at: Optional[datetime] = None # Changed from str to datetime
    # Add updated_at for consistency with other models if desired, e.g.:
    # updated_at: Optional[datetime] = None 
    total_spaces: int
    total_connections_made: int
    # Counts for each user status
    users_pending_verification: int
    users_waitlisted: int
    users_pending_onboarding: int
    users_suspended: int
    users_banned: int

    class Config:
        from_attributes = True

class UserActivateCorporate(BaseModel):
    # No specific payload needed if activation implies fixed changes
    # If space_id needs to be passed for assignment during activation, add it here.
    space_id: int # To assign the newly activated corporate admin to this space

    class Config:
        from_attributes = True 

class StartupUpdateAdmin(BaseModel):
    status: Optional[UserStatus] = None
    space_id: Optional[int] = None
    member_slots_allocated: Optional[int] = None

class MemberSlotUpdate(BaseModel):
    member_slots_allocated: int 

class WaitlistedUser(UserSchema):
    expressed_interest: bool = False
    interest_id: Optional[int] = None

class WaitlistedStartup(StartupSchema):
    expressed_interest: bool = False
    interest_id: Optional[int] = None

class AddTenantRequest(BaseModel):
    user_id: Optional[int] = None
    startup_id: Optional[int] = None

    @model_validator(mode='before')
    def check_one_id_present(cls, values):
        if not values.get('user_id') and not values.get('startup_id'):
            raise ValueError('Either user_id or startup_id must be provided.')
        if values.get('user_id') and values.get('startup_id'):
            raise ValueError('Only one of user_id or startup_id should be provided.')
        return values 