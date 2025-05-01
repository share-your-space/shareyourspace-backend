from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

# Import User schema for nesting
from .user import User

# Shared properties
class ConnectionBase(BaseModel):
    recipient_id: int

# Properties to receive via API on creation
class ConnectionCreate(ConnectionBase):
    pass # Only recipient_id is needed from the user

# Properties to receive via API on update (e.g., changing status)
class ConnectionUpdate(BaseModel):
    status: str # Expecting 'accepted', 'declined', 'blocked'?

# Properties stored in DB
class ConnectionInDBBase(ConnectionBase):
    id: int
    requester_id: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }

# Properties to return to client
class Connection(ConnectionInDBBase):
    requester: User # Add nested User object for the requester
    recipient: User # Add nested User object for the recipient

# Additional schema for representing a connection with user details (optional)
# from .user import User as UserSchema # Import User schema
# class ConnectionWithUsers(Connection):
#     requester: UserSchema
#     recipient: UserSchema

# Shared properties
class NotificationBase(BaseModel):
    type: str
    message: str
    related_entity_id: Optional[int] = None

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

# Schema for checking connection status between two users
class ConnectionStatusCheck(BaseModel):
    status: Optional[str] = None # e.g., 'pending_from_me', 'pending_from_them', 'connected', 'not_connected'
    connection_id: Optional[int] = None # ID if pending or connected 