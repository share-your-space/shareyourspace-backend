from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

from app.models.invitation import InvitationStatus
from .organization import Startup
from .user import User

class InvitationBase(BaseModel):
    email: EmailStr

class InvitationCreate(InvitationBase):
    startup_id: Optional[int] = None
    company_id: Optional[int] = None
    space_id: Optional[int] = None
    invited_by_user_id: Optional[int] = None
    approved_by_admin_id: Optional[int] = None

class InvitationUpdate(InvitationBase):
    pass

class InvitationInDBBase(InvitationBase):
    id: int
    invitation_token: str
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    startup_id: Optional[int] = None
    company_id: Optional[int] = None
    space_id: Optional[int] = None
    invited_by_user_id: Optional[int] = None
    approved_by_admin_id: Optional[int] = None
    accepted_by_user_id: Optional[int] = None
    revoked_by_admin_id: Optional[int] = None

    class Config:
        from_attributes = True

class Invitation(InvitationInDBBase):
    startup: Optional[Startup] = None
    approved_by_admin: Optional[User] = None
    accepted_by_user: Optional[User] = None
    revoked_by_admin: Optional[User] = None

class InvitationListResponse(BaseModel):
    invitations: list[Invitation]

class InvitationDetails(BaseModel):
    email: EmailStr
    organization_name: str
    organization_type: str

class EmployeeInviteCreate(BaseModel):
    email: EmailStr

class InvitationDecline(BaseModel):
    reason: Optional[str] = None

class CorpAdminDirectInviteCreate(BaseModel):
    email: EmailStr
    startup_id: int

class UnifiedInvitationCreate(BaseModel):
    email: EmailStr
    startup_id: int 

Invitation.model_rebuild()
InvitationListResponse.model_rebuild() 