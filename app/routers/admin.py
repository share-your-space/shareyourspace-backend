from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

# Import schemas using submodule path
from app import schemas, models 
# Import specific CRUD functions needed
from app.crud import crud_user, crud_space 
from app.db.session import get_db
from app.dependencies import require_sys_admin

router = APIRouter()


@router.get("/pending-corporates", response_model=List[schemas.admin.UserAdminView], dependencies=[Depends(require_sys_admin)])
async def list_pending_corporate_users(
    db: AsyncSession = Depends(get_db)
):
    """List users with status PENDING_ONBOARDING."""
    # Use direct import path
    users = await crud_user.get_users_by_status(db, status='PENDING_ONBOARDING')
    return users

@router.post("/spaces", response_model=schemas.admin.Space, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_sys_admin)])
async def create_new_space(
    *, # Force keyword arguments
    db: AsyncSession = Depends(get_db),
    space_in: schemas.admin.SpaceCreate
):
    """Create a new SpaceNode. Typically done when approving a corporate user."""
    # Use direct import path and correct function name
    corp_admin = await crud_user.get_user_by_id(db, user_id=space_in.corporate_admin_id)
    if not corp_admin:
        raise HTTPException(
            status_code=400,
            detail=f"Corporate admin user with ID {space_in.corporate_admin_id} not found."
        )

    # Use direct import path
    space = await crud_space.create_space(db=db, obj_in=space_in)
    return space

@router.put("/users/{user_id}/activate-corporate", response_model=schemas.admin.UserAdminView, dependencies=[Depends(require_sys_admin)])
async def activate_corporate_admin_user(
    user_id: int,
    space_id: Optional[int] = None, # Optional query param to assign space upon activation
    db: AsyncSession = Depends(get_db)
):
    """Update user status from PENDING_ONBOARDING to ACTIVE and role to CORP_ADMIN."""
    if space_id:
        # Use direct import path
        space = await crud_space.get_space(db, space_id=space_id)
        if not space:
             raise HTTPException(
                status_code=404,
                detail=f"Space with ID {space_id} not found."
            )

    # Use direct import path
    updated_user = await crud_user.activate_corporate_user(db=db, user_id=user_id, space_id=space_id)
    if not updated_user:
        raise HTTPException(
            status_code=404,
            detail=f"User with ID {user_id} not found or not in PENDING_ONBOARDING status."
        )
    return updated_user

# Optional Basic Management Endpoints
@router.get("/users", response_model=List[schemas.admin.UserAdminView], dependencies=[Depends(require_sys_admin)])
async def list_all_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all users (paginated)."""
    # Use direct import path
    users = await crud_user.get_users(db, skip=skip, limit=limit)
    return users

@router.get("/spaces", response_model=List[schemas.admin.Space], dependencies=[Depends(require_sys_admin)])
async def list_all_spaces(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all spaces (paginated)."""
    # Use direct import path
    spaces = await crud_space.get_spaces(db, skip=skip, limit=limit)
    return spaces 