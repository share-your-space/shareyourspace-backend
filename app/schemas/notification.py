from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from app.models.enums import NotificationType # Import enum
from app.schemas.common import UserSimpleInfo

# Shared properties
class NotificationBase(BaseModel):
    type: NotificationType # Changed to NotificationType
    message: str
    related_entity_id: Optional[int] = None
    reference: Optional[str] = None
    link: Optional[str] = None

class NotificationCreate(NotificationBase):
    user_id: int

# Properties stored in DB
class NotificationInDBBase(NotificationBase):
    id: int
    user_id: int # Recipient ID
    is_read: bool
    created_at: datetime
    sender: Optional[UserSimpleInfo] = None # Add sender info

    model_config = {
        "from_attributes": True
    }

# Properties to return to client
class Notification(NotificationInDBBase):
    pass # Return all DB fields for now 

class NotificationWithUser(Notification):
    requesting_user: Optional[UserSimpleInfo] = None

class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None

class NotificationActionResponse(BaseModel):
    message: str
    success: Optional[bool] = None # Made optional as some old aliases didn't use it
    details: Optional[str] = None
    request_id: Optional[int] = None
    status: Optional[str] = None 