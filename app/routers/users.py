from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, security
from app.schemas.user import User as UserSchema
from app.db.session import get_db

router = APIRouter()


@router.get("/me", response_model=UserSchema)
async def read_users_me(
    current_user: models.User = Depends(security.get_current_active_user),
):
    """
    Fetch the details of the currently authenticated user.
    """
    # The dependency already fetches and validates the user
    return current_user

# Add other user-related endpoints here later (e.g., update profile) 