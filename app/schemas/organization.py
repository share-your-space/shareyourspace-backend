from pydantic import BaseModel, HttpUrl, ConfigDict
from typing import Optional
from datetime import datetime

# Shared properties
class OrganizationBase(BaseModel):
    name: str
    logo_url: Optional[HttpUrl] = None
    industry_focus: Optional[str] = None
    description: Optional[str] = None
    website: Optional[HttpUrl] = None

# Properties to receive on creation (if needed later)
class CompanyCreate(OrganizationBase):
    pass

class StartupCreate(OrganizationBase):
    mission: Optional[str] = None

# Properties to receive on update (if needed later)
class CompanyUpdate(OrganizationBase):
    pass

class StartupUpdate(OrganizationBase):
    mission: Optional[str] = None

# Properties shared by models stored in DB
class OrganizationInDBBase(OrganizationBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True
    )

# Properties to return to client
class Company(OrganizationInDBBase):
    pass

class Startup(OrganizationInDBBase):
    mission: Optional[str] = None

# Properties stored in DB
class CompanyInDB(OrganizationInDBBase):
    pass

class StartupInDB(OrganizationInDBBase):
    mission: Optional[str] = None

# Basic Company Information
class BasicCompany(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

# Basic Startup Information (e.g., for dropdowns or lists)
class BasicStartup(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

# Schema for requesting to add a new member
class MemberRequestCreate(BaseModel):
    email: str # For now, just email. Could expand to full_name, etc.
    # Add any other details you want the Startup Admin to provide
    # e.g., proposed_role: Optional[str] = None

# Schema for the response after requesting a member
class MemberRequestResponse(BaseModel):
    message: str
    notification_sent_to_admin_id: Optional[int] = None
    requested_email: str 