from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import models, schemas, services
from app.db.session import get_db
from app.dependencies import get_current_active_user

router = APIRouter()

@router.get("/discover", response_model=List[schemas.matching.MatchResult])
async def discover_similar_users(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Discover users with similar profiles.
    """
    return await services.matching_service.discover_users(db=db, current_user=current_user)
