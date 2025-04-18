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
    role_type: str  # Expected: 'CORP_REP', 'STARTUP_REP', 'FREELANCER' from frontend
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

# You can add more schemas here as needed, e.g., UserUpdate 