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
    linkedin_profile_url: Optional[HttpUrl] = None
    profile_picture_url: Optional[str] = None # Stores blob name
    cover_photo_url: Optional[str] = None # Stores blob name for cover photo

# Properties to receive via API on update
class UserProfileUpdate(UserProfileBase):
    pass # Inherits all fields from Base, all are optional

# Properties to return to client
class UserProfile(UserProfileBase):
    id: int
    user_id: int
    full_name: Optional[str] = None # Add full_name field
    email: Optional[str] = None # Add this back
    profile_picture_signed_url: Optional[HttpUrl] = None # Added for temporary signed URL
    cover_photo_signed_url: Optional[HttpUrl] = None # For the cover photo
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None

    # Pydantic V2 uses model_config instead of Config
    model_config = ConfigDict(
        from_attributes=True # Allows reading data from ORM models
    ) 