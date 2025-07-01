import asyncio
import logging

from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.user_profile import UserProfile
from app.utils.embeddings import generate_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def backfill_embeddings():
    logger.info("Starting embedding backfill process...")
    db: AsyncSessionLocal = AsyncSessionLocal()
    try:
        # Fetch users who have a profile but no profile_vector
        result = await db.execute(
            select(User)
            .options(selectinload(User.profile))
            .join(User.profile)
            .filter(UserProfile.profile_vector == None) # noqa
        )
        users_to_update = result.scalars().all()

        if not users_to_update:
            logger.info("No users found needing embedding backfill.")
            return

        logger.info(f"Found {len(users_to_update)} users to update.")

        updated_count = 0
        failed_count = 0
        for user in users_to_update:
            profile = user.profile
            if not profile:
                logger.warning(f"User {user.id} has no profile, skipping.")
                continue

            logger.info(f"Processing user {user.id}...")

            # Combine text fields (ensure consistency with update_profile)
            profile_text_parts = [
                profile.title or "",
                profile.bio or "",
                " ".join(profile.skills_expertise or []),
                " ".join(profile.industry_focus or []),
                profile.project_interests_goals or "",
                " ".join(profile.collaboration_preferences or []),
                " ".join(profile.tools_technologies or [])
            ]
            profile_text = " ".join(filter(None, profile_text_parts)).strip()

            if profile_text:
                embedding = generate_embedding(profile_text)
                if embedding:
                    profile.profile_vector = embedding
                    db.add(profile)
                    updated_count += 1
                    logger.info(f"Generated embedding for user {user.id}.")
                else:
                    failed_count += 1
                    logger.error(f"Failed to generate embedding for user {user.id}.")
            else:
                logger.info(f"User {user.id} has no text content in profile, skipping embedding.")
                # Optionally set profile_vector to None explicitly if desired
                # profile.profile_vector = None
                # db.add(profile)

            # Commit periodically to avoid large transactions (e.g., every 10 users)
            if (updated_count + failed_count) % 10 == 0:
                logger.info("Committing batch...")
                await db.commit()

        # Commit any remaining changes
        await db.commit()
        logger.info(f"Backfill complete. Updated: {updated_count}, Failed: {failed_count}")

    except Exception as e:
        logger.error(f"An error occurred during backfill: {e}", exc_info=True)
        await db.rollback() # Rollback on error
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(backfill_embeddings()) 