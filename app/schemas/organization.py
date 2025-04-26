from pydantic import BaseModel, HttpUrl
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

    class Config:
        orm_mode = True # Changed from from_attributes = True for Pydantic v1 compatibility

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