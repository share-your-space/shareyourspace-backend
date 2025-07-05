from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import AsyncGenerator, List
from jose import JWTError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.db.session import get_db, AsyncSessionLocal
from app import models, schemas, crud, security
from app.core.config import settings
from app.models.enums import UserRole
from app.models import User, SpaceNode, Workstation, WorkstationAssignment, Company, Startup, UserProfile


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"/api/v1/auth/login"
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as db:
        yield db

async def get_current_user(
    db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        token_data = schemas.token.TokenPayload(**payload)
        if token_data.user_id is None:
            raise credentials_exception
    except (JWTError, ValidationError):
        raise credentials_exception
    
    user_stmt = (
        select(User)
        .where(User.id == token_data.user_id)
        .options(
            selectinload(User.profile),
            selectinload(User.company).selectinload(Company.spaces),
            selectinload(User.startup).selectinload(Startup.direct_members).selectinload(User.profile),
            selectinload(User.space).selectinload(SpaceNode.company),
            selectinload(User.assignments).selectinload(WorkstationAssignment.workstation),
        )
    )
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    return user

async def get_current_user_with_onboarding_token(
    db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> models.User:
    """
    Dependency to get the current user from a token that is specifically for onboarding.
    It checks for the 'onboarding' purpose in the token claims.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials for onboarding",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_access_token(token)
        token_data = schemas.token.TokenPayload(**payload)
        
        if token_data.purpose != "onboarding":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid token for this operation. Onboarding token required.",
            )
            
        if token_data.user_id is None:
            raise credentials_exception
            
    except (JWTError, ValidationError):
        raise credentials_exception
        
    user = await crud.crud_user.get_user_by_id(db, user_id=token_data.user_id)
    if not user:
        raise credentials_exception
        
    return user

async def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def require_sys_admin(current_user: models.User = Depends(get_current_active_user)):
    if current_user.role != UserRole.SYS_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges. System administrator required.",
        )
    return current_user

def require_corp_admin(current_user: models.User = Depends(get_current_active_user)):
    if current_user.role != UserRole.CORP_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges. Corporate administrator required.",
        )
    return current_user

def get_current_user_with_roles(required_roles: List[UserRole]):
    async def role_checker(current_user: models.User = Depends(get_current_active_user)):
        if not current_user.role or current_user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The user doesn't have the required privileges. Requires one of: {', '.join(role.value for role in required_roles)}",
            )
        return current_user
    return role_checker 