from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# Shared properties
class NotificationBase(BaseModel):
    type: str
    message: str
    related_entity_id: Optional[int] = None
    reference: Optional[str] = None
    link: Optional[str] = None

# Properties stored in DB
class NotificationInDBBase(NotificationBase):
    id: int
    user_id: int # Recipient ID
    is_read: bool
    created_at: datetime

    model_config = {
        "from_attributes": True
    }

# Properties to return to client
class Notification(NotificationInDBBase):
    pass # Return all DB fields for now 

class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None 