from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional
from pydantic import HttpUrl # Import HttpUrl
import logging # Import logging

from app import models, schemas
from app.models.profile import UserProfile # Corrected import path
from app.schemas.user_profile import UserProfileUpdate # Import the schema directly
from app.utils.embeddings import generate_embedding # Import the embedding function

logger = logging.getLogger(__name__) # Add logger

async def get_profile_by_user_id(db: AsyncSession, *, user_id: int) -> Optional[UserProfile]:
    """Get user profile by user ID."""
    result = await db.execute(select(UserProfile).filter(UserProfile.user_id == user_id))
    return result.scalars().first()

async def create_profile_for_user(db: AsyncSession, *, user_id: int) -> UserProfile:
    """Create a new default profile for a user."""
    db_profile = UserProfile(user_id=user_id)
    db.add(db_profile)
    await db.commit()
    await db.refresh(db_profile)
    return db_profile

async def update_profile(
    db: AsyncSession, *, db_obj: UserProfile, obj_in: UserProfileUpdate
) -> UserProfile:
    """Update user profile and generate embedding."""
    logger.info(f"Updating profile for user_id: {db_obj.user_id}")
    update_data = obj_in.model_dump(exclude_unset=True)

    # Update standard fields
    for field, value in update_data.items():
        # Convert HttpUrl to string before setting attribute for DB
        if field == 'linkedin_profile_url' and isinstance(value, HttpUrl):
            setattr(db_obj, field, str(value))
        else:
            setattr(db_obj, field, value)

    # Combine text fields for embedding generation
    # Join list fields into single strings first
    profile_text_parts = [
        db_obj.title or "",
        db_obj.bio or "",
        " ".join(db_obj.skills_expertise) if db_obj.skills_expertise else "",
        " ".join(db_obj.industry_focus) if db_obj.industry_focus else "", # Assuming industry_focus is also ARRAY(String)
        db_obj.project_interests_goals or "",
        " ".join(db_obj.collaboration_preferences) if db_obj.collaboration_preferences else "",
        " ".join(db_obj.tools_technologies) if db_obj.tools_technologies else ""
    ]
    # Filter out empty strings before joining
    profile_text = " ".join(filter(None, profile_text_parts)).strip()

    if profile_text:
        logger.info(f"Generating embedding for user_id: {db_obj.user_id}")
        embedding = generate_embedding(profile_text)
        if embedding:
            # Log the type and length (or first few elements) of the embedding
            logger.info(f"Generated embedding type: {type(embedding)}, length: {len(embedding)} for user_id: {db_obj.user_id}")
            # logger.info(f"Generated embedding sample: {embedding[:5]} for user_id: {db_obj.user_id}") # Uncomment to log sample values
            db_obj.profile_vector = embedding
            logger.info(f"Embedding assigned successfully for user_id: {db_obj.user_id}") # Changed log message slightly
        else:
            logger.warning(f"Embedding generation failed for user_id: {db_obj.user_id}. Setting profile_vector to None.")
            db_obj.profile_vector = None
    else:
        logger.info(f"No text content for embedding for user_id: {db_obj.user_id}. Setting profile_vector to None.")
        db_obj.profile_vector = None

    try:
        db.add(db_obj)
        # Log the value right before commit
        logger.info(f"Value of db_obj.profile_vector before commit: {db_obj.profile_vector is not None} (Type: {type(db_obj.profile_vector)}) for user_id: {db_obj.user_id}")
        logger.info(f"Attempting to commit profile changes for user_id: {db_obj.user_id}")
        await db.commit()
        logger.info(f"Commit successful for user_id: {db_obj.user_id}")
        await db.refresh(db_obj)
        logger.info(f"Refresh successful for user_id: {db_obj.user_id}")
    except Exception as e:
        logger.error(f"DATABASE COMMIT/REFRESH FAILED for user_id {db_obj.user_id}: {e}", exc_info=True)
        await db.rollback()
        logger.info(f"Rolled back transaction for user_id: {db_obj.user_id}")
        # Re-raise the exception so the endpoint handler knows about it
        raise e 
    
    return db_obj 