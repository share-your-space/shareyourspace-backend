from pydantic import BaseModel, ConfigDict
from typing import Optional

from app.models.enums import UserRole

# This schema is used in multiple other schemas, so it's in a common file
# to avoid circular imports.
class UserSimpleInfo(BaseModel):
    """A simplified user schema for nested representations to avoid circular imports."""
    id: int
    full_name: Optional[str] = None
    email: str
    role: Optional[UserRole] = None
    
    model_config = ConfigDict(from_attributes=True) 