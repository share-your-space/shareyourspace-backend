from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
from datetime import datetime, timedelta, timezone

# --- CRUD Imports ---
import app.crud.crud_user as crud_user
import app.crud.crud_verification_token as crud_verification_token

# --- Schema Imports ---
import app.schemas.user as user_schemas
import app.schemas.verification_token as verification_token_schemas # Assuming you create this

# --- Model Imports ---
from app.models.user import User
from app.models.verification_token import VerificationToken

# --- Other Imports ---
from app.db.session import get_db
from app.utils.email import send_email
from app.core.config import settings

router = APIRouter()

@router.post("/register", response_model=user_schemas.User, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: user_schemas.UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user and send verification email."""
    existing_user = await crud_user.get_user_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    try:
        # Create the user first
        db_user = await crud_user.create_user(db=db, obj_in=user_in)

        # Generate verification token
        token = secrets.token_urlsafe(32)
        expires_at = VerificationToken.get_default_expiry()
        token_create = verification_token_schemas.VerificationTokenCreate(
            user_id=db_user.id,
            token=token,
            expires_at=expires_at
        )
        await crud_verification_token.create_verification_token(db=db, obj_in=token_create)

        # Construct verification URL
        verification_url = f"{settings.FRONTEND_URL}/auth/verify?token={token}"

        # Send verification email
        subject = "Verify Your ShareYourSpace Account"
        html_content = f"""
        <p>Hi {db_user.full_name},</p>
        <p>Thanks for registering for ShareYourSpace!</p>
        <p>Please click the link below to verify your email address:</p>
        <p><a href="{verification_url}">{verification_url}</a></p>
        <p>This link will expire in 1 hour.</p>
        <p>If you did not register for an account, please ignore this email.</p>
        <p>Thanks,<br>The ShareYourSpace Team</p>
        """
        send_email(to=db_user.email, subject=subject, html_content=html_content)

        # Return the created user, but status is still PENDING_VERIFICATION
        return db_user

    except Exception as e:
        # Log the detailed error internally
        print(f"Error during user registration or email sending: {e}") # Improve logging
        # Consider rolling back user creation if email fails critically?
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration or sending the verification email."
        )

@router.get("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Verify user's email using the provided token."""
    db_token = await crud_verification_token.get_verification_token(db=db, token=token)

    if not db_token or db_token.expires_at < datetime.now(timezone.utc):
        await crud_verification_token.delete_verification_token(db=db, token_obj=db_token) # Clean up expired/invalid token
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token."
        )

    user: User | None = await crud_user.get_user_by_id(db=db, user_id=db_token.user_id)
    if not user:
        # This case should ideally not happen if DB integrity is maintained
        await crud_verification_token.delete_verification_token(db=db, token_obj=db_token)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Determine the next status based on role
    next_status = ""
    if user.role in ["STARTUP_ADMIN", "STARTUP_MEMBER", "FREELANCER"]:
        next_status = "WAITLISTED"
    elif user.role in ["CORP_ADMIN", "CORP_EMPLOYEE"]:
        next_status = "PENDING_ONBOARDING"
    else:
        next_status = "ACTIVE" # Default or for SYS_ADMIN if applicable

    # Update user status if they are still pending verification
    if user.status == "PENDING_VERIFICATION":
        updated_user_data = user_schemas.UserUpdateInternal(status=next_status)
        await crud_user.update_user_internal(db=db, db_obj=user, obj_in=updated_user_data)

    # Delete the used token
    await crud_verification_token.delete_verification_token(db=db, token_obj=db_token)

    return {"message": "Email verified successfully."}

# --- Add CRUD for VerificationToken --- #
# (This assumes you create app/crud/crud_verification_token.py
# and app/schemas/verification_token.py)

# Add other auth routes here later (login, verify-email, etc.) 