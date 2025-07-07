from pydantic import BaseModel, HttpUrl, ConfigDict, Field
from typing import Optional, List
from app.models.enums import UserRole, UserStatus, ContactVisibility

# Base properties shared by profile models
class UserProfileBase(BaseModel):
    title: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = None
    contact_info_visibility: Optional[ContactVisibility] = ContactVisibility.PRIVATE
    skills_expertise: Optional[List[str]] = None
    industry_focus: Optional[List[str]] = None
    project_interests_goals: Optional[str] = None
    collaboration_preferences: Optional[List[str]] = None
    tools_technologies: Optional[List[str]] = None
    profile_picture_url: Optional[str] = None
    cover_photo_url: Optional[str] = None

# Properties to receive on creation
class UserProfileCreate(UserProfileBase):
    pass

# Properties to receive via API on update
class UserProfileUpdate(UserProfileBase):
    linkedin_profile_url: Optional[HttpUrl] = None

# Properties to return to client
class UserProfile(UserProfileBase):
    id: int
    user_id: int
    is_profile_complete: bool
    full_name: Optional[str] = None
    email: Optional[str] = None
    linkedin_profile_url: Optional[str] = None
    profile_picture_signed_url: Optional[str] = None
    cover_photo_signed_url: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None

    model_config = ConfigDict(
        from_attributes=True
    )