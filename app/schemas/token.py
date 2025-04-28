from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None # 'sub' is the standard JWT field for subject (usually user identifier)
    user_id: Optional[int] = None # Add user_id field 