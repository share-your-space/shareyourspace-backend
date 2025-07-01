from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy.orm import selectinload

from app import crud, models, schemas
from app.db.session import get_db
from app.utils.email import send_email
from app.core.config import settings
from app.security import verify_password, create_access_token
from app.models.enums import UserRole, UserStatus
from app.schemas.token import Token, SetInitialPasswordRequest
from app.schemas.registration import FreelancerCreate, StartupAdminCreate, CorporateAdminCreate
from app.crud import crud_set_password_token, crud_user, crud_verification_token
from app.security import get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter()

async def _register_user_and_send_verification(
    db: AsyncSession,
    user_in: schemas.user.UserCreate,
    role: UserRole,
    user_status: UserStatus,
    company_id: int = None,
    startup_id: int = None,
) -> None:
    """Helper function to create a user, send verification email, and handle errors."""
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

        token_str = secrets.token_urlsafe(32)
        expires_at = models.verification_token.VerificationToken.get_default_expiry() 
        token_create_schema = schemas.verification_token.VerificationTokenCreate(
            user_id=db_user.id, token=token_str, expires_at=expires_at
        )
        await crud_verification_token.create_verification_token(
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
        
        return
    except Exception as e:
        logger.error(f"Error during user registration for {user_in.email}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration.",
        )

@router.post("/register/freelancer", response_model=schemas.Message, status_code=status.HTTP_201_CREATED)
async def register_freelancer(
    user_in: FreelancerCreate, db: AsyncSession = Depends(get_db)
):
    await _register_user_and_send_verification(
        db=db,
        user_in=user_in,
        role=UserRole.FREELANCER,
        user_status=UserStatus.PENDING_VERIFICATION,
    )
    return schemas.Message(message="Registration successful. Please check your email to verify your account.")

@router.post("/register/corporate-admin", response_model=schemas.Message, status_code=status.HTTP_201_CREATED)
async def register_corporate_admin(
    admin_in: CorporateAdminCreate, db: AsyncSession = Depends(get_db)
):
    company = await crud.crud_organization.create_company(db=db, obj_in=admin_in.company_data)
    await _register_user_and_send_verification(
        db=db,
        user_in=admin_in.user_data,
        role=UserRole.CORP_ADMIN,
        user_status=UserStatus.PENDING_VERIFICATION,
        company_id=company.id,
    )
    return schemas.Message(message="Registration successful. Please check your email to verify your account.")

@router.post("/register/startup-admin", response_model=schemas.Message, status_code=status.HTTP_201_CREATED)
async def register_startup_admin(
    admin_in: StartupAdminCreate, db: AsyncSession = Depends(get_db)
):
    startup = await crud.crud_organization.create_startup(db=db, obj_in=admin_in.startup_data)
    await _register_user_and_send_verification(
        db=db,
        user_in=admin_in.user_data,
        role=UserRole.STARTUP_ADMIN,
        user_status=UserStatus.PENDING_VERIFICATION,
        startup_id=startup.id,
    )
    return schemas.Message(message="Registration successful. Please check your email to verify your account.")

@router.get("/verify-email", response_model=schemas.Message)
async def verify_email_route(
    token: str = Query(...), db: AsyncSession = Depends(get_db)
):
    db_verification_token = await crud_verification_token.get_verification_token(
        db=db, token=token
    )
    if not db_verification_token or db_verification_token.expires_at < datetime.now(timezone.utc):
        if db_verification_token:
            await crud_verification_token.delete_verification_token(
                db=db, token_obj=db_verification_token
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )
    user_to_verify = await crud_user.get_user_by_id(
        db=db, user_id=db_verification_token.user_id
    )
    if not user_to_verify:
        await crud_verification_token.delete_verification_token(
            db=db, token_obj=db_verification_token
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User associated with token not found.",
        )
    if not user_to_verify.is_active:
        update_data = {"is_active": True}
        
        if user_to_verify.status == UserStatus.PENDING_VERIFICATION:
            if user_to_verify.role == UserRole.CORP_ADMIN:
                update_data["status"] = UserStatus.ACTIVE
            else:
                update_data["status"] = UserStatus.WAITLISTED

        update_payload = schemas.user.UserUpdateInternal(**update_data)
        await crud_user.update_user_internal(
            db=db, db_obj=user_to_verify, obj_in=update_payload
        )
    await crud_verification_token.delete_verification_token(
        db=db, token_obj=db_verification_token
    )
    return schemas.Message(message="Email verified successfully. You can now log in.")

@router.post("/login", response_model=Token)
async def login_for_access_token_route(
    db: AsyncSession = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
):
    user = await crud_user.get_user_by_email(db, email=form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user. Please verify your email or contact support.",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {"sub": user.email, "user_id": user.id, "role": user.role.value if user.role else None}
    access_token = create_access_token(
        data=token_data, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/request-password-reset", status_code=status.HTTP_200_OK)
async def request_password_reset_route(
    request_data: schemas.password_reset_token.RequestPasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    user = await crud.crud_user.get_user_by_email(db, email=request_data.email)
    if user:
        try:
            token_str = models.password_reset_token.PasswordResetToken.generate_token()
            expires_at = models.password_reset_token.PasswordResetToken.get_default_expiry()
            token_create_schema = schemas.password_reset_token.PasswordResetTokenCreate(
                user_id=user.id,
                token=token_str,
                expires_at=expires_at
            )
            await crud.crud_password_reset_token.create_reset_token(db=db, obj_in=token_create_schema)
            
            reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token_str}"
            subject = "Reset Your ShareYourSpace Password"
            html_content = f"""
            <p>Hi {user.full_name},</p>
            <p>You requested a password reset. Click the link below to set a new password:</p>
            <p><a href="{reset_url}">{reset_url}</a></p>
            <p>This link will expire in 1 hour.</p>
            <p>If you did not request a password reset, please ignore this email.</p>
            <p>Thanks,<br>The ShareYourSpace Team</p>
            """
            send_email(to=user.email, subject=subject, html_content=html_content)
        except Exception as e:
            logger.error(f"Error processing password reset for {request_data.email}: {e}", exc_info=True)
    return {"message": "If an account with that email exists, a password reset link has been sent."}

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password_route(
    request_data: schemas.password_reset_token.ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    db_reset_token = await crud.crud_password_reset_token.get_reset_token_by_token(db=db, token=request_data.token)
    if not db_reset_token or db_reset_token.expires_at < datetime.now(timezone.utc):
        if db_reset_token:
            await crud.crud_password_reset_token.delete_reset_token(db=db, token_obj=db_reset_token)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token."
        )
    user_to_reset = await crud.crud_user.get_user_by_id(db=db, user_id=db_reset_token.user_id)
    if not user_to_reset:
        await crud.crud_password_reset_token.delete_reset_token(db=db, token_obj=db_reset_token) 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User associated with token not found.")
    await crud.crud_user.update_user_password(db=db, user=user_to_reset, new_password=request_data.new_password)
    await crud.crud_password_reset_token.delete_reset_token(db=db, token_obj=db_reset_token)
    return {"message": "Password has been reset successfully."}

@router.post("/set-initial-password", response_model=schemas.Message)
async def set_initial_password(
    *, 
    db: AsyncSession = Depends(get_db),
    password_data: SetInitialPasswordRequest = Depends()
):
    token_str = password_data.token
    new_password = password_data.new_password
    db_token = await crud_set_password_token.get_set_password_token_by_token_string(db, token_string=token_str)
    if not db_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token.")
    if await crud_set_password_token.is_set_password_token_expired(db_token):
        await crud_set_password_token.use_set_password_token(db, db_token=db_token)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token has expired.")
    user = await crud.user.get_user(db, user_id=db_token.user_id)
    if not user:
        await crud_set_password_token.use_set_password_token(db, db_token=db_token)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for this token.")
    user.hashed_password = get_password_hash(new_password)
    db.add(user)
    await crud_set_password_token.use_set_password_token(db, db_token=db_token)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        logger = logging.getLogger(__name__)
        logger.error(f"Error committing set initial password for user {user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not set password due to a server error.")
    return schemas.Message(message="Password has been set successfully. You can now log in.")

# --- Add CRUD for VerificationToken --- #
# (This assumes you create app/crud/crud_verification_token.py
# and app/schemas/verification_token.py)

# Add other auth routes here later (login, verify-email, etc.) 