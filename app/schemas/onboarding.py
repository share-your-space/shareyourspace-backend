from pydantic import BaseModel, Field
from typing import Optional
from app.models.enums import UserRole
from .organization import StartupCreate, CompanyCreate

class OnboardingData(BaseModel):
    role: UserRole = Field(..., description="The role the user is selecting.")
    startup_data: Optional[StartupCreate] = None
    company_data: Optional[CompanyCreate] = None 