from pydantic import BaseModel, HttpUrl, ConfigDict
from typing import Optional, List
from app.models.enums import ContactVisibility

# Base properties shared by profile models
class UserProfileBase(BaseModel):
    title: Optional[str] = None
    bio: Optional[str] = None
    contact_info_visibility: Optional[ContactVisibility] = ContactVisibility.CONNECTIONS
    skills_expertise: Optional[List[str]] = None
    industry_focus: Optional[List[str]] = None
    project_interests_goals: Optional[str] = None
    collaboration_preferences: Optional[List[str]] = None
    tools_technologies: Optional[List[str]] = None
    linkedin_profile_url: Optional[HttpUrl] = None
    profile_picture_url: Optional[str] = None # Stores blob name

# Properties to receive via API on update
class UserProfileUpdate(UserProfileBase):
    pass # Inherits all fields from Base, all are optional

# Properties to return to client
class UserProfile(UserProfileBase):
    id: int
    user_id: int
    full_name: Optional[str] = None # Add full_name field
    profile_picture_signed_url: Optional[str] = None # Added for temporary signed URL

    # Pydantic V2 uses model_config instead of Config
    model_config = ConfigDict(
        from_attributes=True # Allows reading data from ORM models
    ) 