from pydantic import BaseModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.user import User # Assuming your user schema is named User

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: str | None = None # Subject (usually email)
    user_id: int | None = None
    role: str | None = None 

class TokenWithUser(Token):
    user: "User" 

# Resolve forward references
# TokenWithUser.model_rebuild() 