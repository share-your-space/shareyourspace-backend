from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import Optional

# Import User schema for nesting
# from .user import User
from app.models.enums import ConnectionStatus # Import the enum

# NEW: UserReference schema for concise user details in connection lists
class UserReference(BaseModel):
    id: int # Renamed from user_id to id to match ORM model
    full_name: Optional[str] = None
    title: Optional[str] = None
    profile_picture_signed_url: Optional[str] = None # Expecting a signed URL or public URL

    model_config = {
        "from_attributes": True # Allow ORM mode
    }

# Shared properties
class ConnectionBase(BaseModel):
    recipient_id: int

# Properties to receive via API on creation
class ConnectionCreate(ConnectionBase):
    pass # Only recipient_id is needed from the user

# Properties to receive via API on update (e.g., changing status)
class ConnectionUpdate(BaseModel):
    status: ConnectionStatus # Use the ConnectionStatus enum

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
    requester: UserReference # UPDATED to UserReference
    recipient: UserReference # UPDATED to UserReference

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