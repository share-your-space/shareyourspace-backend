from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

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
    pass # Return all DB fields for now

# Additional schema for representing a connection with user details (optional)
# from .user import User as UserSchema # Import User schema
# class ConnectionWithUsers(Connection):
#     requester: UserSchema
#     recipient: UserSchema 