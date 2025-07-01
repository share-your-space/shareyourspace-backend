from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func, or_, not_, exists # Add or_, not_, exists
from typing import Optional, List, Tuple # Add Tuple
from pydantic import HttpUrl # Import HttpUrl
import logging # Import logging
from sqlalchemy.orm import joinedload, selectinload # Add joinedload and selectinload for eager loading user data

from app import models, schemas
from app.models.profile import UserProfile # Corrected import path
from app.models.user import User # Import User model
from app.models.connection import Connection # Removed ConnectionStatus as it's in enums
from app.models.enums import ConnectionStatus, UserStatus # Import Enums
from app.schemas.user_profile import UserProfileUpdate # Import the schema directly
from app.utils.embeddings import generate_embedding # Import the embedding function

logger = logging.getLogger(__name__) # Add logger

async def get_profile_by_user_id(db: AsyncSession, *, user_id: int) -> Optional[UserProfile]:
    """Get user profile by user ID."""
    logger.debug(f"Fetching profile for user_id: {user_id}")
    try:
        # Eager load the user relationship as it's often needed with the profile
        result = await db.execute(
            select(UserProfile)
            .options(selectinload(UserProfile.user))
            .filter(UserProfile.user_id == user_id)
        )
        profile = result.scalars().first()
        if not profile:
            logger.warning(f"Profile not found for user_id: {user_id}")
        return profile
    except Exception as e: # Catch generic exception for logging, but specific is better if known
        logger.error(f"Error fetching profile for user_id {user_id}: {e}", exc_info=True)
        return None

async def create_profile_for_user(db: AsyncSession, *, user: User) -> UserProfile:
    """Create a new default profile for a user."""
    logger.info(f"Creating new profile for user_id: {user.id}")
    # Check if profile already exists to prevent duplicates, though relationship should handle this
    existing_profile = await get_profile_by_user_id(db, user_id=user.id)
    if existing_profile:
        logger.warning(f"Profile already exists for user_id: {user.id}. Returning existing one.")
        return existing_profile
        
    db_profile = UserProfile(user_id=user.id)
    # db_profile.user = user # This can also associate if relationship is set up correctly
    try:
        db.add(db_profile)
        await db.commit()
        await db.refresh(db_profile)
        logger.info(f"Profile created successfully for user_id: {user.id}")
        return db_profile
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating profile for user_id {user.id}: {e}", exc_info=True)
        raise # Re-raise to be handled by caller

async def update_profile(
    db: AsyncSession, *, db_obj: UserProfile, obj_in: UserProfileUpdate
) -> UserProfile:
    logger.info(f"Updating profile for user_id: {db_obj.user_id} with obj_in: {obj_in.model_dump_json()}") # Log input
    
    # Directly set attributes from obj_in
    for field, value in obj_in.model_dump(exclude_none=True).items(): # use exclude_none to avoid setting None explicitly if not in schema
        if hasattr(db_obj, field):
            # Convert HttpUrl to string for assignment if needed
            value_to_assign = str(value) if isinstance(value, HttpUrl) else value
            setattr(db_obj, field, value_to_assign)
            logger.debug(f"Profile for user {db_obj.user_id}: Directly setting {field} to {value_to_assign}")

    # --- Embedding generation part ---
    # For now, let's assume fields are set and try to generate embedding
    profile_text_parts = [
        str(db_obj.title or ""), # Ensure string conversion
        str(db_obj.bio or ""),
        " ".join(db_obj.skills_expertise) if db_obj.skills_expertise else "",
        " ".join(db_obj.industry_focus) if db_obj.industry_focus else "",
        str(db_obj.project_interests_goals or ""),
        " ".join(db_obj.collaboration_preferences) if db_obj.collaboration_preferences else "",
        " ".join(db_obj.tools_technologies) if db_obj.tools_technologies else ""
    ]
    profile_text = " ".join(filter(None, profile_text_parts)).strip()
    logger.info(f"Constructed profile_text for embedding for user {db_obj.user_id}: '{profile_text[:200]}...'") # Log constructed text

    if profile_text:
        logger.info(f"Attempting to generate embedding for user_id: {db_obj.user_id}.")
        embedding = generate_embedding(profile_text)
        if embedding is not None:
            db_obj.profile_vector = embedding
            logger.info(f"Embedding updated for user_id: {db_obj.user_id}.")
        else:
            logger.warning(f"Embedding generation returned None for user_id: {db_obj.user_id}. Vector not updated.")
            db_obj.profile_vector = None # Explicitly set to None if generation fails
    else:
        logger.info(f"No text content for embedding for user_id: {db_obj.user_id}. Clearing vector.")
        db_obj.profile_vector = None
    # --- End Embedding generation part ---

    try:
        db.add(db_obj) # Add the modified object to the session (SQLAlchemy tracks changes)
        await db.commit()
        await db.refresh(db_obj)
        logger.info(f"Profile for user_id: {db_obj.user_id} committed successfully. Title after commit: '{db_obj.title}'") # Log a field
    except Exception as e:
        await db.rollback()
        logger.error(f"Database commit/refresh failed for profile update of user_id {db_obj.user_id}: {e}", exc_info=True)
        # raise # Optional: re-raise if you want seed to stop on this error
    
    return db_obj 

async def find_similar_users(
    db: AsyncSession,
    *,
    requesting_user: models.User, # Use models.User for type hint
    limit: int = 10,
    exclude_user_ids: Optional[List[int]] = None
) -> List[Tuple[UserProfile, float]]: 
    if not requesting_user.profile or requesting_user.profile.profile_vector is None:
        logger.warning(f"User {requesting_user.id} has no profile or profile vector. Cannot find similar users.")
        return []
    if requesting_user.space_id is None:
        logger.warning(f"User {requesting_user.id} is not associated with a space. Cannot find similar users.")
        return []

    embedding = requesting_user.profile.profile_vector
    space_id = requesting_user.space_id
    user_id = requesting_user.id
    company_id = requesting_user.company_id
    startup_id = requesting_user.startup_id

    logger.info(f"Finding similar users for user_id={user_id} in space_id={space_id} (DEBUGGING - WIDER FILTERS)")

    # Subquery to find user IDs with existing pending or accepted connections with the requesting user
    # Selects the ID of the other user in the connection
    # connected_user_ids_subquery = (
    #     select(Connection.recipient_id)
    #     .where(
    #         (Connection.requester_id == user_id) &
    #         (Connection.status.in_([ConnectionStatus.PENDING, ConnectionStatus.ACCEPTED]))
    #     )
    #     .union(
    #         select(Connection.requester_id)
    #         .where(
    #             (Connection.recipient_id == user_id) &
    #             (Connection.status.in_([ConnectionStatus.PENDING, ConnectionStatus.ACCEPTED]))
    #     )
    #     )
    # )

    stmt = (
        select(
            UserProfile,
            UserProfile.profile_vector.cosine_distance(embedding).label('distance')
        )
        .join(User, UserProfile.user_id == User.id)
        .options(joinedload(UserProfile.user).selectinload(User.profile)) # Eager load User and its profile
        .filter(User.space_id == space_id) 
        .filter(User.id != user_id) 
        .filter(User.status == UserStatus.ACTIVE) # Use Enum
        .filter(UserProfile.profile_vector.is_not(None)) 
        # .filter(User.id.notin_(connected_user_ids_subquery)) # DEBUG: Temporarily commented out
    )

    # ADDED: Exclude specific user IDs if provided
    if exclude_user_ids:
        stmt = stmt.filter(User.id.notin_(exclude_user_ids))
        logger.info(f"Excluding user IDs: {exclude_user_ids} from similarity search for user {user_id}")

    # DEBUG: Temporarily commenting out company/startup exclusion
    # if company_id:
    #     stmt = stmt.filter(User.company_id != company_id)
    #     logger.debug(f"Excluding users from company_id={company_id} for user_id={user_id}")
    # if startup_id: 
    #     stmt = stmt.filter(or_(User.startup_id.is_(None), User.startup_id != startup_id))
    #     logger.debug(f"Excluding users from startup_id={startup_id} (but allowing NULL startup_id) for user_id={user_id}")

    stmt = stmt.order_by(UserProfile.profile_vector.cosine_distance(embedding)).limit(limit)

    try:
        results = await db.execute(stmt)
        similar_users_with_distance = results.fetchall() # List of Tuples (UserProfile instance, distance)
        logger.info(f"Found {len(similar_users_with_distance)} similar users for user_id={user_id} (DEBUGGING - WIDER FILTERS)")
        # for profile_obj, dist in similar_users_with_distance:
        #     logger.debug(f"Candidate User ID: {profile_obj.user_id}, Distance: {dist}, Name: {profile_obj.user.full_name if profile_obj.user else 'N/A'}")
        return similar_users_with_distance
    except Exception as e:
        logger.error(f"Error executing similarity search for user_id {user_id}: {e}", exc_info=True)
        return []

async def ai_search_waitlisted_profiles(db: AsyncSession, *, query: str, limit: int = 20) -> List[Tuple[UserProfile, float]]:
    """
    Performs a vector similarity search on waitlisted user profiles based on a query string.
    """
    query_embedding = generate_embedding(query)
    if not query_embedding:
        logger.warning("Could not generate embedding for the AI search query.")
        return []

    stmt = (
        select(
            UserProfile,
            UserProfile.profile_vector.cosine_distance(query_embedding).label('distance')
        )
        .join(User, UserProfile.user_id == User.id)
        .options(joinedload(UserProfile.user).selectinload(User.profile)) # Eager load for response
        .filter(User.status == UserStatus.WAITLISTED)
        .filter(UserProfile.profile_vector.is_not(None))
        .order_by(UserProfile.profile_vector.cosine_distance(query_embedding))
        .limit(limit)
    )

    try:
        results = await db.execute(stmt)
        similar_profiles = results.fetchall()
        logger.info(f"AI search found {len(similar_profiles)} waitlisted profiles for query: '{query}'")
        return similar_profiles
    except Exception as e:
        logger.error(f"Error during AI search for waitlisted profiles: {e}", exc_info=True)
        return []