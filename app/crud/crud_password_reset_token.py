from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

from app.models.password_reset_token import PasswordResetToken
from app.schemas.password_reset_token import PasswordResetTokenCreate

async def create_reset_token(db: AsyncSession, *, obj_in: PasswordResetTokenCreate) -> PasswordResetToken:
    """Create a new password reset token."""
    db_token = PasswordResetToken(
        user_id=obj_in.user_id,
        token=obj_in.token,
        expires_at=obj_in.expires_at
    )
    try:
        db.add(db_token)
        await db.commit()
        await db.refresh(db_token)
        return db_token
    except SQLAlchemyError as e:
        await db.rollback()
        print(f"Database error creating password reset token: {e}")
        raise

async def get_reset_token_by_token(db: AsyncSession, *, token: str) -> PasswordResetToken | None:
    """Fetch a password reset token by the token string."""
    try:
        result = await db.execute(select(PasswordResetToken).filter(PasswordResetToken.token == token))
        return result.scalars().first()
    except SQLAlchemyError as e:
        print(f"Database error fetching password reset token: {e}")
        return None

async def delete_reset_token(db: AsyncSession, *, token_obj: PasswordResetToken | None):
    """Delete a password reset token object."""
    if token_obj:
        try:
            await db.delete(token_obj)
            await db.commit()
        except SQLAlchemyError as e:
            await db.rollback()
            print(f"Database error deleting password reset token: {e}")
            # Decide if deletion failure should raise an error or just be logged 