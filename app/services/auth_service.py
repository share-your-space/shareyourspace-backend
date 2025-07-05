import secrets
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app import crud, models, schemas
from app.models.enums import UserRole, UserStatus
from app.utils.email import send_email
from app.core.config import settings

logger = logging.getLogger(__name__)

async def register_user_and_send_verification(
    db: AsyncSession,
    user_in: schemas.user.UserCreate,
    role: UserRole,
    user_status: UserStatus,
    company_id: int = None,
    startup_id: int = None,
) -> models.User:
    """
    Creates a user, sends a verification email, and handles potential errors.
    """
    existing_user = await crud.crud_user.get_user_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    try:
        user_create_data = user_in.model_copy(
            update={
                "role": role,
                "status": user_status,
                "company_id": company_id,
                "startup_id": startup_id,
            }
        )
        db_user = await crud.crud_user.create_user(db=db, obj_in=user_create_data)

        # Create a profile for the new user
        await crud.crud_user_profile.create_profile_for_user(db=db, user=db_user)

        token_str = secrets.token_urlsafe(32)
        expires_at = models.verification_token.VerificationToken.get_default_expiry()
        token_create_schema = schemas.verification_token.VerificationTokenCreate(
            user_id=db_user.id, token=token_str, expires_at=expires_at
        )
        await crud.crud_verification_token.create_verification_token(
            db=db, obj_in=token_create_schema
        )

        verification_url = f"{settings.FRONTEND_URL}/auth/verify?token={token_str}"
        subject = "Verify Your ShareYourSpace Account"
        html_content = f"""
        <p>Hi {user_in.full_name},</p>
        <p>Thanks for registering for ShareYourSpace!</p>
        <p>Please click the link below to verify your email address:</p>
        <p><a href="{verification_url}">{verification_url}</a></p>
        <p>This link will expire in 1 hour.</p>
        <p>If you did not register for an account, please ignore this email.</p>
        <p>Thanks,<br>The ShareYourSpace Team</p>
        """
        send_email(to=db_user.email, subject=subject, html_content=html_content)
        logger.info(f"Verification email sending process initiated for {db_user.email}.")
        
        return db_user
    except Exception as e:
        logger.error(f"Error during user registration for {user_in.email}: {e}", exc_info=True)
        # It's good practice to rollback the session if user creation succeeded but email failed.
        # However, the transaction is managed by the dependency injection, so we just re-raise.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration.",
        ) 