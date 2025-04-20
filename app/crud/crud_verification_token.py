from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload # For potential future use if relationships needed

from app.models.verification_token import VerificationToken
from app.schemas.verification_token import VerificationTokenCreate

async def create_verification_token(db: AsyncSession, *, obj_in: VerificationTokenCreate) -> VerificationToken:
    """Create a new verification token."""
    db_obj = VerificationToken(**obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

async def get_verification_token(db: AsyncSession, *, token: str) -> VerificationToken | None:
    """Get a verification token by its token string."""
    statement = select(VerificationToken).where(VerificationToken.token == token)
    result = await db.execute(statement)
    return result.scalar_one_or_none()

async def delete_verification_token(db: AsyncSession, *, token_obj: VerificationToken | None) -> None:
    """Delete a verification token object."""
    if token_obj:
        await db.delete(token_obj)
        await db.commit()

async def delete_verification_token_by_token(db: AsyncSession, *, token: str) -> None:
    """Delete a verification token by its token string."""
    statement = delete(VerificationToken).where(VerificationToken.token == token)
    await db.execute(statement)
    await db.commit() 