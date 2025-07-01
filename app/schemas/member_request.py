from pydantic import BaseModel, EmailStr
from typing import List, Optional, Literal
from datetime import datetime
from enum import Enum

# Simplified info about the startup making the request
class RequestingStartupInfo(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

# Simplified info about the user being requested (if they exist)
# or details provided in the request for a new user.
class RequestedUserInfo(BaseModel):
    id: Optional[int] = None # Present if the user already exists in the system
    full_name: Optional[str] = None # Can be pre-filled if user exists, or from request
    email: EmailStr # Always present, from the original request

    class Config:
        from_attributes = True

class MemberRequestStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class MemberRequestDetail(BaseModel):
    id: int # This will likely be the ID of the NotificationNode
    requested_at: datetime
    status: MemberRequestStatus
    requesting_startup: RequestingStartupInfo
    # If the request is for an existing user, their details can be included.
    # If it's for a new user, only the email might be available initially.
    requested_user_details: Optional[RequestedUserInfo] = None # Populated if the email matches an existing user
    requested_email: EmailStr # The email as entered in the request

    class Config:
        from_attributes = True

class MemberRequestListResponse(BaseModel):
    requests: List[MemberRequestDetail]

    class Config:
        from_attributes = True

class MemberRequestActionResponse(BaseModel):
    message: str
    request_id: int
    status: str
    # Optionally, include details of the created/activated user if approved
    # activated_user: Optional[BasicUser] = None # BasicUser from app.schemas.space 

# Schema for Startup Admin to request a new member
class StartupMemberRequestCreate(BaseModel):
    email: EmailStr
    # Optional: Startup Admin can provide a full name if known
    full_name: Optional[str] = None 
    # startup_id will be derived from the authenticated Startup Admin 

# Schema for details when a Corp Admin approves a member request
class MemberRequestApprovalDetails(BaseModel):
    workstation_id: Optional[int] = None
    start_date: Optional[datetime] = None 