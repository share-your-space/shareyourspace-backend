from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime
# from app.models.user import UserStatus # Assuming UserStatus enum exists in models

# Forward references for nested schemas
from app.schemas.user_profile import UserProfile as UserProfileSchema
from app.schemas.organization import BasicCompany as BasicCompanySchema, BasicStartup as BasicStartupSchema
from app.schemas.space import BasicSpace as BasicSpaceSchema, UserWorkstationInfo as UserWorkstationInfoSchema

# Base properties shared by user models
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None # full_name can be optional in base if some flows set it later

# Properties required for user creation via API (e.g. direct registration)
class UserCreate(UserBase):
    email: EmailStr # Make email explicit here if not optional in UserBase
    full_name: str  # Make full_name required for direct creation
    password: str
    role: str 
    company_name: Optional[str] = None
    title: Optional[str] = None

# Properties for user self-update 
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None # For changing password
    # Add other fields a user can update themselves

# Schema for user creation via invitation acceptance
class UserCreateAcceptInvitation(BaseModel):
    full_name: str
    password: str

# Schema for internal updates (e.g., system changing status, role, linking to entities)
class UserUpdateInternal(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None # Replace str with UserStatus if enum is available
    is_active: Optional[bool] = None
    hashed_password: Optional[str] = None # If system needs to update hashed_password directly
    corporate_admin_id: Optional[int] = None
    startup_id: Optional[int] = None
    space_id: Optional[int] = None
    company_id: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True
    )

# Properties to return to client (excluding sensitive info like password)
class User(UserBase):
    id: int
    email: EmailStr # Ensure email is non-optional in output
    full_name: str  # Ensure full_name is non-optional in output
    role: str
    status: str # Replace str with UserStatus if enum is available
    is_active: bool
    created_at: datetime
    updated_at: datetime
    corporate_admin_id: Optional[int] = None
    startup_id: Optional[int] = None
    space_id: Optional[int] = None
    company_id: Optional[int] = None # Added company_id for completeness

    model_config = ConfigDict(
        from_attributes=True # Allows reading data from ORM models
    )

# Detailed User Schema for Profile Page
class UserDetail(User): # Inherits fields from User schema
    profile: Optional[UserProfileSchema] = None
    company: Optional[BasicCompanySchema] = None
    startup: Optional[BasicStartupSchema] = None
    space: Optional[BasicSpaceSchema] = None # The space they BELONG to
    managed_space: Optional[BasicSpaceSchema] = None # The space they MANAGE (if CORP_ADMIN)
    current_workstation: Optional[UserWorkstationInfoSchema] = None
    
    model_config = ConfigDict(from_attributes=True)

# You can add more schemas here as needed, e.g., UserUpdate 