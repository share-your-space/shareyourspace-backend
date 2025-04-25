from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional

from app import models, schemas
from app.models.user_profile import UserProfile # Import the model directly
from app.schemas.user_profile import UserProfileUpdate # Import the schema directly


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
    """Update user profile."""
    update_data = obj_in.model_dump(exclude_unset=True) # Use model_dump in Pydantic v2

    for field, value in update_data.items():
        setattr(db_obj, field, value)

    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj 