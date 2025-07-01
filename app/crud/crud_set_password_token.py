import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.set_password_token import SetPasswordToken
from app.schemas.token import SetPasswordTokenCreateInternal # Will define this schema later

async def create_set_password_token(db: AsyncSession, *, user_id: int) -> SetPasswordToken:
    token_str = secrets.token_urlsafe(32)
    expires_at = SetPasswordToken.get_default_expiry()
    
    # Check if a token already exists for this user and delete it
    existing_token = await get_set_password_token_by_user_id(db, user_id=user_id)
    if existing_token:
        await db.delete(existing_token)
        # await db.commit() # Commit deletion if necessary, or let it be part of the larger transaction

    token_obj_in = SetPasswordTokenCreateInternal(
        user_id=user_id, 
        token=token_str, 
        expires_at=expires_at
    )
    db_token = SetPasswordToken(**token_obj_in.model_dump())
    db.add(db_token)
    # await db.commit() # Usually commit is handled by the caller/router
    # await db.refresh(db_token)
    return db_token

async def get_set_password_token_by_token_string(
    db: AsyncSession, *, token_string: str
) -> Optional[SetPasswordToken]:
    stmt = select(SetPasswordToken).where(SetPasswordToken.token == token_string)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_set_password_token_by_user_id(
    db: AsyncSession, *, user_id: int
) -> Optional[SetPasswordToken]:
    stmt = select(SetPasswordToken).where(SetPasswordToken.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def use_set_password_token(db: AsyncSession, *, db_token: SetPasswordToken) -> SetPasswordToken:
    """Marks a token as used by deleting it."""
    await db.delete(db_token)
    # await db.commit() # Caller should commit
    return db_token # The object is still in memory, but marked for deletion in session

async def is_set_password_token_expired(token: SetPasswordToken) -> bool:
    return datetime.now(timezone.utc) > token.expires_at 