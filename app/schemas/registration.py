from pydantic import BaseModel, EmailStr
from typing import Optional

from .organization import CompanyCreate, StartupCreate
from .user import UserCreate

# Pydantic models for the new registration flows

class FreelancerCreate(UserCreate):
    """Schema for creating a user with the FREELANCER role."""
    pass

class StartupAdminCreate(BaseModel):
    """Schema for creating a STARTUP_ADMIN and their startup."""
    user_data: UserCreate
    startup_data: StartupCreate

class CorporateAdminCreate(BaseModel):
    """Schema for creating a CORP_ADMIN and their company."""
    user_data: UserCreate
    company_data: CompanyCreate 