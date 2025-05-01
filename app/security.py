from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.schemas.token import TokenPayload as TokenPayloadSchema
from app import crud, models # Removed schemas from here

# Define the OAuth2 scheme
# Use the URL of your token endpoint (login endpoint)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login") # Ensure correct path


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Default token expiry: Consider making this configurable
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES) # Use config if available
    to_encode.update({"exp": expire})
    # Use .get_secret_value() to get the actual string key
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)
    return encoded_jwt

async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Use .get_secret_value() for decoding as well
        payload = jwt.decode(
            token, settings.SECRET_KEY.get_secret_value(), algorithms=[settings.ALGORITHM]
        )
        username: str = payload.get("sub")
        user_id: int | None = payload.get("user_id") # Assuming user_id is in token
        if username is None or user_id is None:
            raise credentials_exception
        token_data = TokenPayloadSchema(sub=username, user_id=user_id)
    except JWTError:
        raise credentials_exception

    # Use the user_id from the token for lookup and load profile eagerly
    user = await crud.crud_user.get_user_by_id(
        db,
        user_id=token_data.user_id, 
        options=[selectinload(models.User.profile)] # Eager load profile
    )
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    # Check if user is active (consider using the status field as well)
    if not current_user.is_active or current_user.status != 'ACTIVE':
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user 