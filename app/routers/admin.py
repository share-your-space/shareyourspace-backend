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

@router.post("/simple-spaces", response_model=schemas.admin.Space, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_sys_admin)])
async def create_simple_space(
    *, # Force keyword arguments
    db: AsyncSession = Depends(get_db),
    space_in: schemas.admin.SimpleSpaceCreate
):
    """Create a simple SpaceNode without requiring a corporate admin ID."""
    # Adapt this to call a potentially simplified CRUD function or handle optional admin ID
    try:
        # Assuming crud_space.create_space can handle missing corporate_admin_id 
        # or we create a specific simple_create_space function.
        # For now, let's construct the full object with None admin_id
        # We need to use the SpaceCreate schema from admin for the input object
        full_space_data = schemas.admin.SpaceCreate(
            name=space_in.name,
            total_workstations=space_in.total_workstations,
            corporate_admin_id=None # Set admin ID to None
        )
        space = await crud_space.create_space(db=db, obj_in=full_space_data)
        # The response should match the response_model, which is schemas.admin.Space
        return space
    except Exception as e: # Catch potential errors if crud_space expects admin_id
        # Log the error properly
        print(f"Error creating simple space: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create simple space: Check logs for details."
        )

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

@router.put("/users/{user_id}/assign-space", response_model=schemas.admin.UserAdminView, dependencies=[Depends(require_sys_admin)])
async def assign_user_space(
    user_id: int,
    assignment: schemas.admin.UserAssignSpace,
    db: AsyncSession = Depends(get_db)
):
    """Assigns or unassigns a user to a specific space node."""
    try:
        updated_user = await crud_user.assign_user_to_space(
            db=db, user_id=user_id, space_id=assignment.space_id
        )
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found."
            )
        return updated_user
    except ValueError as e:
         # Handle case where space_id is provided but doesn't exist
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Catch unexpected errors from CRUD
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while assigning the user to the space."
        )

@router.put("/users/{user_id}/status", response_model=schemas.admin.UserAdminView, dependencies=[Depends(require_sys_admin)])
async def update_user_status(
    user_id: int,
    status_update: schemas.admin.UserStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update the status of a specific user."""
    user = await crud_user.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found."
        )

    # Basic validation (can enhance later)
    allowed_statuses = ["PENDING_VERIFICATION", "WAITLISTED", "PENDING_ONBOARDING", "ACTIVE", "SUSPENDED", "BANNED"]
    if status_update.status not in allowed_statuses:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status value: '{status_update.status}'. Allowed: {allowed_statuses}"
        )

    # Use the internal update function
    update_data = schemas.user.UserUpdateInternal(status=status_update.status)
    try:
        updated_user = await crud_user.update_user_internal(db=db, db_obj=user, obj_in=update_data)
        return updated_user
    except Exception as e:
        # Log error properly
        print(f"Error updating user status for {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the user status."
        ) 