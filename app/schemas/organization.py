from __future__ import annotations
from typing import Optional, List, Any, Literal, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict, Field, computed_field
from datetime import datetime

from app.models.enums import TeamSize, StartupStage, UserStatus, UserRole
from .common import UserSimpleInfo

if TYPE_CHECKING:
    from .user import User

# --- Base Schemas ---
class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    logo_url: Optional[str] = None
    industry_focus: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=5000)
    website: Optional[str] = None
    team_size: Optional[str] = None
    looking_for: Optional[List[str]] = []
    social_media_links: Optional[dict[str, str]] = {}

# --- Company Schemas ---
class CompanyCreate(OrganizationBase):
    pass

class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    logo_url: Optional[str] = None
    industry_focus: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=5000)
    website: Optional[str] = None
    team_size: Optional[TeamSize] = None
    looking_for: Optional[List[str]] = None
    social_media_links: Optional[dict[str, str]] = None

class Company(OrganizationBase):
    id: int
    created_at: datetime
    updated_at: datetime
    admin: Optional[UserSimpleInfo] = None

    model_config = ConfigDict(from_attributes=True)


# --- Startup Schemas ---
class StartupCreate(OrganizationBase):
    mission: Optional[str] = Field(None, max_length=1000)
    stage: Optional[str] = None
    pitch_deck_url: Optional[str] = None

class StartupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    logo_url: Optional[str] = None
    industry_focus: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=5000)
    website: Optional[str] = None
    team_size: Optional[TeamSize] = None
    looking_for: Optional[List[str]] = None
    social_media_links: Optional[dict[str, str]] = None
    mission: Optional[str] = Field(None, max_length=1000)
    stage: Optional[str] = None
    pitch_deck_url: Optional[str] = None
    member_slots_allocated: Optional[int] = None

class Startup(OrganizationBase):
    id: int
    mission: Optional[str] = None
    stage: Optional[str] = None
    pitch_deck_url: Optional[str] = None
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    member_slots_allocated: Optional[int] = 0
    member_slots_used: int = 0
    direct_members: List[UserSimpleInfo] = []

    @computed_field
    @property
    def admin(self) -> Optional[UserSimpleInfo]:
        for member in self.direct_members:
            if member.role == UserRole.STARTUP_ADMIN:
                return member
        return None

    model_config = ConfigDict(from_attributes=True)

# --- Other Schemas ---
class BasicCompany(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class BasicStartup(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class MemberRequestCreate(BaseModel):
    email: str

class MemberRequestResponse(BaseModel):
    message: str
    notification_sent_to_admin_id: Optional[int] = None
    requested_email: str

class OrganizationSearchResult(BaseModel):
    id: int
    name: str
    type: str

class InvitationRequest(BaseModel):
    organization_id: int
    organization_type: str # 'company' or 'startup' 