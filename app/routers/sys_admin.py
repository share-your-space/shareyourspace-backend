from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app import schemas, models, crud, services
from app.db.session import get_db
from app.dependencies import require_sys_admin
from app.models.enums import UserRole, UserStatus
from app.schemas.admin import (
    PendingCorporateUser, 
    Space as SpaceResponseSchema,
    UserAdminView, 
    PaginatedUserAdminView,
    SpaceUpdate,
    SpaceAssignAdmin,
    UserStatusUpdate,
)

router = APIRouter(
    tags=["System Admin"],
    prefix="/sys-admin",
    dependencies=[Depends(require_sys_admin)]
)

@router.get("/pending-corporates", response_model=List[PendingCorporateUser])
async def list_pending_corporate_signups(db: AsyncSession = Depends(get_db)):
    """List all users with status PENDING_ONBOARDING."""
    pending_users = await crud.crud_user.get_users_by_status(db, status=UserStatus.PENDING_ONBOARDING)
    return pending_users

@router.get("/users", response_model=PaginatedUserAdminView)
async def list_all_users(
    skip: int = 0,
    limit: int = 100,
    user_type: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    space_id: Optional[int] = None,
    search_term: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List and filter all users in the system."""
    users, total_users = await services.sys_admin_service.get_all_users_paginated(
        db,
        skip=skip,
        limit=limit,
        user_type=user_type,
        status=status,
        space_id=space_id,
        search_term=search_term,
    )
    return PaginatedUserAdminView(
        total=total_users,
        users=[UserAdminView.from_orm(u) for u in users]
    )

@router.post("/impersonate/{user_id}", response_model=schemas.Token)
async def impersonate_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Generate an impersonation token for a user."""
    token = await services.sys_admin_service.impersonate_user(db, user_id=user_id)
    return schemas.Token(access_token=token, token_type="bearer")

@router.get("/spaces", response_model=List[SpaceResponseSchema])
async def list_all_spaces(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """List all spaces."""
    spaces = await crud.crud_space.get_spaces(db, skip=skip, limit=limit)
    return spaces

@router.put("/users/{user_id}/status", response_model=UserAdminView)
async def update_user_status_by_admin(
    user_id: int, 
    status_update: UserStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a user's role, status, or space assignment."""
    updated_user = await services.sys_admin_service.update_user_status(
        db, user_id=user_id, status_update=status_update
    )
    return UserAdminView.from_orm(updated_user)

@router.put("/spaces/{space_id}", response_model=SpaceResponseSchema)
async def update_space_by_admin(
    space_id: int, 
    space_update: SpaceUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a space's details."""
    updated_space = await services.sys_admin_service.update_space_details(
        db, space_id=space_id, space_update=space_update
    )
    return updated_space

@router.get("/stats", response_model=schemas.admin.PlatformStats)
async def get_platform_statistics(db: AsyncSession = Depends(get_db)):
    """Retrieve comprehensive platform statistics."""
    stats = await services.sys_admin_service.get_platform_stats(db)
    return stats

@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a company and all of its associated resources (spaces, employees, etc.).
    """
    await services.sys_admin_service.delete_company_and_all_resources(
        db=db, company_id=company_id
    )
    return None 