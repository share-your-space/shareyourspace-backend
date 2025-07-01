from __future__ import annotations
from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from app.models.enums import UserRole, UserStatus

if TYPE_CHECKING:
    from .organization import Company, Startup, BasicCompany, BasicStartup
    from .space import BasicSpace, UserWorkstationInfo
    from .user_profile import UserProfile

class UserBase(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")
    full_name: Optional[str] = Field(None, min_length=2, max_length=100, example="John Doe")

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = UserStatus.PENDING_VERIFICATION
    company_id: Optional[int] = None
    startup_id: Optional[int] = None
    space_id: Optional[int] = None
    is_active: bool = False

class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)

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
    company: Optional["BasicCompany"] = None
    startup: Optional["BasicStartup"] = None
    space_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    profile: Optional["UserProfile"] = None
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

# You can add more schemas here as needed, e.g., UserUpdate 