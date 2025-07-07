from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func, or_, not_, exists
from typing import Optional, List, Tuple
from pydantic import HttpUrl
import logging
from sqlalchemy.orm import joinedload, selectinload

from app import models, schemas
from app.crud.base import CRUDBase
from app.models.profile import UserProfile
from app.models.user import User
from app.models.connection import Connection
from app.models.enums import ConnectionStatus, UserStatus
from app.schemas.user_profile import UserProfileUpdate, UserProfileCreate
from app.utils.embeddings import generate_embedding

logger = logging.getLogger(__name__)


class CRUDUserProfile(CRUDBase[UserProfile, UserProfileCreate, UserProfileUpdate]):
    async def get_profile_by_user_id(self, db: AsyncSession, *, user_id: int) -> Optional[UserProfile]:
        """Get user profile by user ID."""
        logger.debug(f"Fetching profile for user_id: {user_id}")
        try:
            result = await db.execute(
                select(UserProfile)
                .options(selectinload(UserProfile.user))
                .filter(UserProfile.user_id == user_id)
            )
            profile = result.scalars().first()
            if not profile:
                logger.warning(f"Profile not found for user_id: {user_id}")
            return profile
        except Exception as e:
            logger.error(f"Error fetching profile for user_id {user_id}: {e}", exc_info=True)
            return None

    async def create_profile_for_user(self, db: AsyncSession, *, user: User) -> UserProfile:
        """Create a new default profile for a user."""
        logger.info(f"Creating new profile for user_id: {user.id}")
        existing_profile = await self.get_profile_by_user_id(db, user_id=user.id)
        if existing_profile:
            logger.warning(f"Profile already exists for user_id: {user.id}. Returning existing one.")
            return existing_profile

        db_profile = UserProfile(user_id=user.id)
        try:
            db.add(db_profile)
            await db.commit()
            await db.refresh(db_profile)
            logger.info(f"Profile created successfully for user_id: {user.id}")
            return db_profile
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating profile for user_id {user.id}: {e}", exc_info=True)
            raise

    async def update_profile_with_embedding_generation(
        self, db: AsyncSession, *, db_obj: UserProfile, obj_in: UserProfileUpdate
    ) -> UserProfile:
        logger.info(f"Updating profile for user_id: {db_obj.user_id} with obj_in: {obj_in.model_dump_json()}")

        for field, value in obj_in.model_dump(exclude_none=True).items():
            if hasattr(db_obj, field):
                value_to_assign = str(value) if isinstance(value, HttpUrl) else value
                setattr(db_obj, field, value_to_assign)
                logger.debug(f"Profile for user {db_obj.user_id}: Directly setting {field} to {value_to_assign}")

        profile_text_parts = [
            str(db_obj.title or ""),
            str(db_obj.bio or ""),
            " ".join(db_obj.skills_expertise) if db_obj.skills_expertise else "",
            " ".join(db_obj.industry_focus) if db_obj.industry_focus else "",
            str(db_obj.project_interests_goals or ""),
            " ".join(db_obj.collaboration_preferences) if db_obj.collaboration_preferences else "",
            " ".join(db_obj.tools_technologies) if db_obj.tools_technologies else ""
        ]
        profile_text = " ".join(filter(None, profile_text_parts)).strip()
        logger.info(f"Constructed profile_text for embedding for user {db_obj.user_id}: '{profile_text[:200]}...'")

        if profile_text:
            logger.info(f"Attempting to generate embedding for user_id: {db_obj.user_id}.")
            embedding = generate_embedding(profile_text)
            if embedding is not None:
                db_obj.profile_vector = embedding
                logger.info(f"Embedding updated for user_id: {db_obj.user_id}.")
            else:
                logger.warning(f"Embedding generation returned None for user_id: {db_obj.user_id}. Vector not updated.")
                db_obj.profile_vector = None
        else:
            logger.info(f"No text content for embedding for user_id: {db_obj.user_id}. Clearing vector.")
            db_obj.profile_vector = None

        try:
            db.add(db_obj)
            await db.commit()
            await db.refresh(db_obj)
            logger.info(f"Profile for user_id: {db_obj.user_id} committed successfully. Title after commit: '{db_obj.title}'")
        except Exception as e:
            await db.rollback()
            logger.error(f"Database commit/refresh failed for profile update of user_id {db_obj.user_id}: {e}", exc_info=True)

        return db_obj

    async def find_similar_users(
        self,
        db: AsyncSession,
        *,
        requesting_user: models.User,
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

        stmt = (
            select(
                UserProfile,
                UserProfile.profile_vector.cosine_distance(embedding).label('distance')
            )
            .join(User, UserProfile.user_id == User.id)
            .options(joinedload(UserProfile.user).selectinload(User.profile))
            .filter(User.space_id == space_id)
            .filter(User.id != user_id)
            .filter(User.status == UserStatus.ACTIVE)
            .filter(UserProfile.profile_vector.is_not(None))
        )

        if exclude_user_ids:
            stmt = stmt.filter(User.id.notin_(exclude_user_ids))
            logger.info(f"Excluding user IDs: {exclude_user_ids} from similarity search for user {user_id}")

        stmt = stmt.order_by(UserProfile.profile_vector.cosine_distance(embedding)).limit(limit)

        try:
            results = await db.execute(stmt)
            similar_users_with_distance = results.fetchall()
            logger.info(f"Found {len(similar_users_with_distance)} similar users for user_id={user_id} (DEBUGGING - WIDER FILTERS)")
            return similar_users_with_distance
        except Exception as e:
            logger.error(f"Error executing similarity search for user_id {user_id}: {e}", exc_info=True)
            return []

    async def ai_search_waitlisted_profiles(self, db: AsyncSession, *, query: str, limit: int = 20) -> List[Tuple[UserProfile, float]]:
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
            .options(joinedload(UserProfile.user).selectinload(User.profile))
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

crud_user_profile = CRUDUserProfile(UserProfile)