from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
from datetime import datetime, timedelta, timezone

# --- CRUD Imports ---
import app.crud.crud_user as crud_user
import app.crud.crud_verification_token as crud_verification_token
import app.crud.crud_password_reset_token as crud_password_reset_token

# --- Schema Imports ---
import app.schemas.user as user_schemas
import app.schemas.verification_token as verification_token_schemas
import app.schemas.password_reset_token as password_reset_schemas

# --- Model Imports ---
from app.models.user import User
from app.models.verification_token import VerificationToken
from app.models.password_reset_token import PasswordResetToken

# --- Other Imports ---
from app.db.session import get_db
from app.utils.email import send_email
from app.core.config import settings
from app import security

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
        # Re-fetch the user to ensure we have the latest state including role after update
        user = await crud_user.get_user_by_id(db=db, user_id=db_token.user_id)
        if not user: # Should ideally not happen, but good practice to check
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found after status update.")

    # Delete the used token
    await crud_verification_token.delete_verification_token(db=db, token_obj=db_token)

    # Return success message along with the user's role
    return {"success": True, "message": "Email verified successfully!", "role": user.role}

@router.post("/login")
async def login_for_access_token(
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Authenticate user and return JWT access token."""
    user = await crud_user.get_user_by_email(db, email=form_data.username)
    
    # Check if user exists and password is correct
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Check if the user account is active (adjust based on your status logic)
    # Example: Allow login only if ACTIVE, WAITLISTED, or PENDING_ONBOARDING?
    # Or just check `is_active` boolean if using that.
    # if user.status not in ["ACTIVE", "WAITLISTED", "PENDING_ONBOARDING"]:
    if not user.is_active: # Assuming is_active is the primary check
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user. Please verify your email or contact support.",
        )
        
    # Create the access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.email, "user_id": user.id, "role": user.role},
        expires_delta=access_token_expires
    )
    
    # Return the token in the response body (as expected by current frontend)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/request-password-reset", status_code=status.HTTP_200_OK)
async def request_password_reset(
    request_data: password_reset_schemas.RequestPasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """Send a password reset email to the user if the email exists."""
    user = await crud_user.get_user_by_email(db, email=request_data.email)
    
    # IMPORTANT: Always return success to prevent email enumeration attacks
    if user:
        try:
            # Generate and store token
            token = PasswordResetToken.generate_token()
            expires_at = PasswordResetToken.get_default_expiry()
            token_create = password_reset_schemas.PasswordResetTokenCreate(
                user_id=user.id,
                token=token,
                expires_at=expires_at
            )
            await crud_password_reset_token.create_reset_token(db=db, obj_in=token_create)
            
            # Construct reset URL
            reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
            
            # Send email
            subject = "Reset Your ShareYourSpace Password"
            html_content = f"""
            <p>Hi {user.full_name},</p>
            <p>You requested a password reset for your ShareYourSpace account.</p>
            <p>Please click the link below to set a new password:</p>
            <p><a href="{reset_url}">{reset_url}</a></p>
            <p>This link will expire in 1 hour.</p>
            <p>If you did not request a password reset, please ignore this email.</p>
            <p>Thanks,<br>The ShareYourSpace Team</p>
            """
            # Consider running email sending in background task for responsiveness
            send_email(to=user.email, subject=subject, html_content=html_content)

        except Exception as e:
            # Log the error but still return a generic success message to the client
            print(f"Error processing password reset request for {request_data.email}: {e}")

    # Return generic message regardless of whether the user was found or email sent
    return {"message": "If an account exists for this email, a password reset link has been sent."}

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    request_data: password_reset_schemas.ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reset the user's password using a valid token."""
    token = request_data.token
    new_password = request_data.new_password
    
    db_token = await crud_password_reset_token.get_reset_token_by_token(db=db, token=token)
    
    if not db_token or db_token.expires_at < datetime.now(timezone.utc):
        await crud_password_reset_token.delete_reset_token(db=db, token_obj=db_token) # Clean up
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token."
        )
        
    user = await crud_user.get_user_by_id(db=db, user_id=db_token.user_id)
    if not user:
        await crud_password_reset_token.delete_reset_token(db=db, token_obj=db_token) # Clean up
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User associated with token not found.")
        
    try:
        # Update user password
        await crud_user.update_user_password(db=db, user=user, new_password=new_password)
        
        # Delete the used token
        await crud_password_reset_token.delete_reset_token(db=db, token_obj=db_token)
        
        return {"message": "Password has been reset successfully."}
        
    except Exception as e:
        print(f"Error during password reset for user {user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting the password."
        )

# --- Add CRUD for VerificationToken --- #
# (This assumes you create app/crud/crud_verification_token.py
# and app/schemas/verification_token.py)

# Add other auth routes here later (login, verify-email, etc.) 