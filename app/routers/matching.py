from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging

from app import models, schemas, crud
from app.crud import crud_user_profile
from app.db.session import get_db
from app.security import get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/discover", response_model=List[schemas.UserProfile]) # Adjust response model if needed
async def discover_similar_users(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> List[models.UserProfile]:
    """
    Discover users with similar profiles within the same space.
    Leverages vector similarity search on user profile embeddings.
    Excludes the user themselves and members of their own company/startup.
    """
    logger.info(f"Discover endpoint called by user_id={current_user.id}")

    # Eager load profile and potentially space if needed elsewhere
    # await db.refresh(current_user, attribute_names=['profile', 'space']) 

    if not current_user.profile:
        # Attempt to fetch profile if not loaded, or create if it truly doesn't exist
        profile = await crud_user_profile.get_profile_by_user_id(db, user_id=current_user.id)
        if not profile:
             # Handle case where profile setup might have failed earlier
             logger.error(f"User {current_user.id} has no profile object. Cannot perform discovery.")
             raise HTTPException(status_code=404, detail="User profile not found. Please complete your profile.")
        current_user.profile = profile # Attach fetched profile
        
    if current_user.profile.profile_vector is None:
        logger.warning(f"User {current_user.id} profile has no embedding vector.")
        raise HTTPException(status_code=400, detail="Profile embedding not generated yet. Try updating your profile.")
        
    if current_user.space_id is None:
        logger.warning(f"User {current_user.id} is not assigned to a space.")
        raise HTTPException(status_code=400, detail="User not assigned to a space. Cannot discover connections.")

    similar_profiles = await crud_user_profile.find_similar_users(
        db=db, requesting_user=current_user, limit=10 # Default limit or make configurable
    )
    
    logger.info(f"Returning {len(similar_profiles)} similar profiles for user_id={current_user.id}")
    
    # Ensure the response matches the response_model structure
    # If find_similar_users returns UserProfile model objects, ensure schemas.UserProfile can handle them
    return similar_profiles
