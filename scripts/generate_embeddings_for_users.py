import asyncio
import logging
import argparse
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker, joinedload
from typing import List

# Adjust imports based on your project structure
from app.core.config import settings
from app.models.user import User
from app.models.profile import UserProfile
from app.utils.embeddings import generate_embedding

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def update_and_embed_profile(db: AsyncSession, user_id: int, profile_data: dict):
    """Fetches user, updates profile text, generates embedding, and saves."""
    logger.info(f"Processing user_id: {user_id}")
    
    # Fetch user with profile eagerly loaded
    result = await db.execute(
        select(User).options(joinedload(User.profile)).filter(User.id == user_id)
    )
    user = result.scalars().first()

    if not user:
        logger.error(f"User with id {user_id} not found.")
        return
        
    if not user.profile:
        logger.warning(f"User {user_id} has no profile object. Creating one.")
        # Simplified profile creation for script context
        user.profile = UserProfile(user_id=user_id, contact_info_visibility='CONNECTIONS') 
        db.add(user.profile)
        # Need to flush to get the profile object associated before updating fields
        try:
            await db.flush() 
            logger.info(f"Created profile for user {user_id}")
        except Exception as e:
             logger.error(f"Error flushing new profile for user {user_id}: {e}", exc_info=True)
             await db.rollback()
             return # Stop processing this user if profile creation fails

    profile = user.profile

    # Update profile text fields
    logger.info(f"Updating profile fields for user_id: {user_id}")
    for field, value in profile_data.items():
        if hasattr(profile, field):
            setattr(profile, field, value)
        else:
            logger.warning(f"Profile object does not have field: {field}")

    # Combine text fields for embedding generation
    profile_text_parts = [
        profile.title or "",
        profile.bio or "",
        " ".join(profile.skills_expertise) if profile.skills_expertise else "",
        " ".join(profile.industry_focus) if profile.industry_focus else "",
        profile.project_interests_goals or "",
        " ".join(profile.collaboration_preferences) if profile.collaboration_preferences else "",
        " ".join(profile.tools_technologies) if profile.tools_technologies else ""
    ]
    profile_text = " ".join(filter(None, profile_text_parts)).strip()

    if profile_text:
        logger.info(f"Generating embedding for user_id: {user_id} with text: '{profile_text[:100]}...' ")
        embedding = generate_embedding(profile_text)
        if embedding:
            logger.info(f"Generated embedding length: {len(embedding)} for user_id: {user_id}")
            profile.profile_vector = embedding
        else:
            logger.warning(f"Embedding generation failed for user_id: {user_id}. Vector not updated.")
            profile.profile_vector = None # Explicitly set to None if failed
    else:
        logger.info(f"No text content for embedding for user_id: {user_id}. Vector not updated.")
        profile.profile_vector = None # Explicitly set to None if no text

    # Add the updated profile object to the session
    db.add(profile)
    logger.info(f"Profile for user {user_id} added to session. Attempting commit.")


async def main(user_ids: List[int]):
    DATABASE_URL = settings.DATABASE_URL
    engine = create_async_engine(DATABASE_URL, echo=False) # Set echo=True for SQL debugging
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Define profile data for specific users
    # User 7 (Original - For Reference) - Assume already has 'AI', 'Python', 'Cloud' profile
    
    # User 6 (Different Profile)
    profile_data_user_6 = {
        "title": "Freelance Writer",
        "bio": "Experienced content writer specializing in tech and marketing.",
        "skills_expertise": ["Content Writing", "SEO", "Copywriting", "Marketing Strategy"],
        "industry_focus": ["Technology", "Marketing"],
        "project_interests_goals": "Looking for freelance writing projects for SaaS companies.",
        "collaboration_preferences": ["asynchronous", "clear briefs"],
        "tools_technologies": ["Google Docs", "WordPress", "Ahrefs"]
    }

    # User 8 (Similar Profile to User 7's potential profile)
    profile_data_user_8 = {
        "title": "AI Engineer",
        "bio": "Developing machine learning models and cloud solutions. Proficient in Python.",
        "skills_expertise": ["Machine Learning", "Python", "Cloud Computing", "Data Analysis", "AWS"],
        "industry_focus": ["Technology", "Artificial Intelligence"],
        "project_interests_goals": "Seeking collaboration on AI projects, particularly in NLP or computer vision.",
        "collaboration_preferences": ["brainstorming", "pair programming"],
        "tools_technologies": ["Python", "TensorFlow", "PyTorch", "Docker", "AWS"]
    }
    
    # User 9 (Different Space, Different Profile)
    profile_data_user_9 = {
        "title": "Graphic Designer",
        "bio": "Creative graphic designer focused on branding and UI design.",
        "skills_expertise": ["Graphic Design", "UI Design", "Branding", "Adobe Creative Suite"],
        "industry_focus": ["Design", "Marketing"],
        "project_interests_goals": "Interested in branding projects for startups.",
        "collaboration_preferences": ["visual feedback", "creative workshops"],
        "tools_technologies": ["Figma", "Adobe Illustrator", "Adobe Photoshop"]
    }
    
    user_profile_map = {
        6: profile_data_user_6,
        8: profile_data_user_8,
        9: profile_data_user_9,
        # Add user 11 here if you want to generate an embedding for them too
    }

    async with AsyncSessionLocal() as session:
        async with session.begin(): # Use a transaction
            for user_id in user_ids:
                if user_id in user_profile_map:
                    logger.info(f"Starting sequential processing for user_id: {user_id}")
                    await update_and_embed_profile(session, user_id, user_profile_map[user_id])
                    logger.info(f"Finished sequential processing for user_id: {user_id}")
                else:
                    logger.warning(f"No specific profile data defined for user_id: {user_id}. Skipping text update, attempting embedding if text exists.")
                    # Optionally, add logic here to still generate embedding based on whatever text might already be in the profile
            
            # Removed asyncio.gather
            logger.info("Committing changes for all processed users.")

    logger.info("Script finished.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate embeddings for specified user profiles.")
    parser.add_argument("user_ids", type=int, nargs='+', help="List of user IDs to process.")
    args = parser.parse_args()
    
    asyncio.run(main(args.user_ids))
