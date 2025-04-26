from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime

# Base properties shared by user models
class UserBase(BaseModel):
    email: EmailStr
    full_name: str

# Properties required for user creation via API
class UserCreate(UserBase):
    password: str
    role: str  # Renamed from role_type. Expected: 'CORP_ADMIN', 'STARTUP_ADMIN', 'FREELANCER' etc.
    company_name: Optional[str] = None
    title: Optional[str] = None

# Properties to return to client (excluding sensitive info like password)
class User(UserBase):
    id: int
    role: str
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Pydantic V2 uses model_config instead of Config
    model_config = ConfigDict(
        from_attributes=True # Allows reading data from ORM models
    )

# Schema for internal updates (e.g., changing status)
# Only include fields that can be updated internally
class UserUpdateInternal(BaseModel):
    status: Optional[str] = None
    is_active: Optional[bool] = None
    # Add other fields here if needed for internal updates

    model_config = ConfigDict(
        from_attributes=True
    )

# You can add more schemas here as needed, e.g., UserUpdate 