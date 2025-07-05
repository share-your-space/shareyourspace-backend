from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from app.models.enums import UserRole, UserStatus
from .user_profile import UserProfile
from .workstation import Workstation

if TYPE_CHECKING:
    from .organization import Startup, Company

class UserBase(BaseModel):
    """
    Common user attributes.
    """
    email: EmailStr = Field(..., example="user@example.com")
    full_name: Optional[str] = Field(None, min_length=2, max_length=100, example="John Doe")
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    company_id: Optional[int] = None
    startup_id: Optional[int] = None
    space_id: Optional[int] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = UserStatus.PENDING_VERIFICATION
    company_id: Optional[int] = None
    startup_id: Optional[int] = None
    space_id: Optional[int] = None
    is_active: bool = False

class UserUpdate(UserBase):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    model_config = ConfigDict(
        from_attributes=True,
    )
    password: Optional[str] = None

class UserCreateAcceptInvitation(BaseModel):
    full_name: str
    password: str

class UserUpdateInternal(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    status: Optional[UserStatus] = None
    role: Optional[UserRole] = None
    company_id: Optional[int] = None
    startup_id: Optional[int] = None
    space_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class User(UserBase):
    id: int
    is_active: bool
    status: UserStatus
    role: Optional[UserRole]
    company: Optional["Company"] = None
    startup: Optional["Startup"] = None
    space_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    profile: Optional[UserProfile] = None
    managed_space: Optional["BasicSpace"] = None
    current_workstation: Optional["UserWorkstationInfo"] = None
    space_corporate_admin_id: Optional[int] = None
    referral_code: Optional[str] = None
    community_badge: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class UserStatusUpdate(BaseModel):
    status: Optional[UserStatus] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    space_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class UserDetail(User):
    profile: Optional[UserProfile] = None
    company: Optional["Company"] = None
    startup: Optional["Startup"] = None
    space: Optional["BasicSpace"] = None
    model_config = ConfigDict(from_attributes=True)

class UserInDB(User):
    hashed_password: str
    model_config = ConfigDict(from_attributes=True)

class BasicUser(UserBase):
    id: int
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    startup_id: Optional[int] = None

    class Config:
        from_attributes = True

class BasicUserInfo(BaseModel):
    id: int
    full_name: Optional[str] = None

class SpaceUserDetail(User):
    """User details for the space management view."""
    profile: Optional[UserProfile] = None
    assigned_workstation: Optional[Workstation] = None

class SpaceUsersListResponse(BaseModel):
    users: List[SpaceUserDetail]

class UserAuth(BaseModel):
    email: EmailStr
    password: str

class UserRegister(UserBase):
    password: str = Field(..., min_length=8)

class UserCreateCorporateAdmin(UserRegister):
    company_name: str
    company_website: Optional[str] = None
    
class UserCreateStartupAdmin(UserRegister):
    startup_name: str
    startup_website: Optional[str] = None

class UserCreateFreelancer(UserRegister):
    pass

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    token: str
    new_password: str

# You can add more schemas here as needed, e.g., UserUpdate 