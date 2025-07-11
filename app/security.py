from datetime import datetime, timedelta, timezone
from typing import Any
import logging
import sys # Import sys for stderr

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.schemas.token import TokenPayload as TokenPayloadSchema
from app import crud, models
from app.models.enums import UserStatus, UserRole

logger = logging.getLogger(__name__)

# --- Password Hashing Setup ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Define the OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

# --- Password Verification --- 
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# --- Token Creation --- 
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    
    # DEBUG: Print secret key before encoding
    try:
        key_for_encoding = settings.SECRET_KEY.get_secret_value()
        logger.debug(f"DEBUG_SECURITY_CREATE_TOKEN: SECRET_KEY for encoding: '{key_for_encoding}'")
    except Exception as e:
        logger.debug(f"DEBUG_SECURITY_CREATE_TOKEN: Error getting SECRET_KEY for encoding: {e}")
        key_for_encoding = "fallback_error_key" # Should not happen

    encoded_jwt = jwt.encode(
        to_encode, key_for_encoding, algorithm=settings.ALGORITHM
    )
    logger.debug(f"DEBUG_SECURITY_CREATE_TOKEN: ENCODED JWT: '{encoded_jwt}'")
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """Decodes the access token and returns the payload."""
    try:
        key_for_decoding = settings.SECRET_KEY.get_secret_value()
        payload = jwt.decode(
            token, key_for_decoding, algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.error(f"JWTError during token decoding: {e}", exc_info=True)
        raise

# --- Current User Dependencies --- 
async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> models.User:
    # logger.warning(f"GET_CURRENT_USER RECEIVED TOKEN: {token}") # Keep this or use print
    logger.debug(f"DEBUG_SECURITY_GET_USER: Received token: {token}")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # DEBUG: Print secret key before decoding
        key_for_decoding = "error_getting_key_for_decoding" # Default in case of error
        try:
            key_for_decoding = settings.SECRET_KEY.get_secret_value()
            logger.debug(f"DEBUG_SECURITY_GET_USER: SECRET_KEY for decoding: '{key_for_decoding}'")
        except Exception as e:
            logger.debug(f"DEBUG_SECURITY_GET_USER: Error getting SECRET_KEY for decoding: {e}")

        payload = jwt.decode(
            token, key_for_decoding, algorithms=[settings.ALGORITHM]
        )
        # logger.warning(f"DECODED PAYLOAD: {payload}")
        logger.debug(f"DEBUG_SECURITY_GET_USER: Decoded payload: {payload}")
        username: str | None = payload.get("sub") 
        user_id: int | None = payload.get("user_id")
        startup_id: int | None = payload.get("startup_id")
        company_id: int | None = payload.get("company_id")

        logger.debug(f"DEBUG_SECURITY_GET_USER: Extracted username (sub): {username}, user_id: {user_id}")
        if username is None or user_id is None:
            logger.debug("DEBUG_SECURITY_GET_USER: CRITICAL - Username (sub) or user_id missing in token payload.")
            raise credentials_exception
        token_data = TokenPayloadSchema(
            sub=username, 
            user_id=user_id,
            startup_id=startup_id,
            company_id=company_id
        )
    except JWTError as e:
        logger.debug(f"DEBUG_SECURITY_GET_USER: CRITICAL - JWTError: {e}")
        raise credentials_exception
    except Exception as e: 
        logger.debug(f"DEBUG_SECURITY_GET_USER: CRITICAL - Unexpected error: {e}")
        raise credentials_exception

    user = await crud.crud_user.get_user_by_id(
        db,
        user_id=int(token_data.user_id),
        options=[
            selectinload(models.User.profile),
            selectinload(models.User.startup),
            selectinload(models.User.company),
            selectinload(models.User.space),
            selectinload(models.User.assignments).selectinload(models.WorkstationAssignment.workstation)
            ]
    )
    logger.debug(f"DEBUG_SECURITY_GET_USER: User fetched from DB: ID={user.id if user else 'None'}")

    if user is None:
        logger.debug(f"DEBUG_SECURITY_GET_USER: CRITICAL - User with id {token_data.user_id} not found in DB.")
        raise credentials_exception
    
    # Override with token data to ensure freshness after onboarding
    if token_data.startup_id is not None:
        user.startup_id = token_data.startup_id
    if token_data.company_id is not None:
        user.company_id = token_data.company_id

    return user

async def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user account.")
    if current_user.status != UserStatus.ACTIVE:
         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"User status is {current_user.status.value}, not {UserStatus.ACTIVE.value}.")
    return current_user 

async def get_current_user_for_chat(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """
    Dependency for chat-related endpoints.
    Allows users with status 'ACTIVE' or 'WAITLISTED' to proceed.
    Raises a 403 Forbidden error for any other status.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user account.")
    if current_user.status not in [UserStatus.ACTIVE, UserStatus.WAITLISTED]:
         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"User status '{current_user.status.value}' is not authorized for chat.")
    return current_user

async def get_current_email_verified_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """Ensures the user is fetched and their email is effectively verified (is_active = True). Does not check for UserStatus.ACTIVE."""
    if not current_user.is_active:
        # This implies email is not verified or account is manually deactivated by admin
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active. Please verify your email or contact support.")
    return current_user

# --- Role-Based Access Control (RBAC) --- 
def get_current_verified_user_with_roles(required_roles: list[UserRole]):
    """
    Dependency that checks if a user has one of the required roles,
    but does NOT require the user to have an ACTIVE status.
    It only requires the user's email to be verified (is_active = True).
    """
    async def role_checker(current_user: models.User = Depends(get_current_email_verified_user)) -> models.User:
        if not current_user.role or current_user.role not in required_roles:
            required_roles_str = ", ".join([role.value for role in required_roles])
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{current_user.role.value}' is not authorized. Required roles: {required_roles_str}."
            )
        return current_user
    return role_checker

def get_current_user_with_roles(
    required_roles: list[UserRole],
    allow_self: bool = False
):
    """
    Dependency to get the current user and check if they have the required roles.
    Can also be configured to allow a user to access a resource if they are
    the owner (their startup_id or company_id matches).
    """
    async def role_checker(
        request: Request,
        current_user: models.User = Depends(get_current_active_user)
    ) -> models.User:
        # Check for role authorization
        if current_user.role and current_user.role in required_roles:
            return current_user

        # If role check fails, check for self-ownership if allow_self is True
        if allow_self:
            # Extract ID from URL path, e.g., /organizations/startups/{startup_id}
            path_id_str = request.path_params.get("startup_id") or request.path_params.get("company_id")
            if path_id_str:
                try:
                    path_id = int(path_id_str)
                    is_own_startup = current_user.startup_id is not None and current_user.startup_id == path_id
                    is_own_company = current_user.company_id is not None and current_user.company_id == path_id
                    
                    if is_own_startup or is_own_company:
                        return current_user
                except (ValueError, TypeError):
                    pass  # path_id is not a valid integer, proceed to fail

        # If all checks fail, raise forbidden error
        required_roles_str = ", ".join([role.value for role in required_roles])
        detail = (
            f"User role '{current_user.role.value if current_user.role else 'None'}' is not authorized. "
            f"Required roles: {required_roles_str}."
        )
        if allow_self:
            detail += " Or you must be the owner of the resource."

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )
    return role_checker 

def get_current_active_user_with_permissions(required_roles: list[UserRole]):
    """
    This is a dependency that checks if the current user is active and has one of the required roles.
    It's a common pattern for protecting endpoints.
    """
    async def role_checker(current_user: models.User = Depends(get_current_active_user)) -> models.User:
        if not current_user.role or current_user.role not in required_roles:
            required_roles_str = ", ".join([role.value for role in required_roles])
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{current_user.role.value}' is not authorized. Required roles: {required_roles_str}."
            )
        return current_user
    return role_checker