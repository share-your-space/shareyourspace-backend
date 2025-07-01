from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from typing import List, Optional, Union

from app import schemas, models, crud
from app.crud import crud_user, crud_space, crud_organization, crud_user_profile, crud_notification
from app.db.session import get_db
from app.dependencies import require_sys_admin, require_corp_admin, get_current_active_user, get_current_user_with_roles
from app.models.enums import UserRole, UserStatus, NotificationType
from app import security as app_security
from app.core.config import settings
from app.schemas.admin import (
    PendingCorporateUser, 
    Space as SpaceResponseSchema, 
    UserActivateCorporate, 
    UserAssignSpace, 
    UserAdminView, 
    PaginatedUserAdminView,
    SpaceUpdate,
    SpaceAssignAdmin,
    UserStatusUpdate,
    AISearchRequest,
    StartupUpdateAdmin,
    MemberSlotUpdate
)
from app.schemas.user import UserUpdateInternal, User as UserSchema
from app.schemas.organization import Startup as StartupSchema

router = APIRouter(
    tags=["Admin"],
)

@router.post("/ai-search-waitlist", response_model=List[UserSchema])
async def ai_search_waitlist(
    search_request: AISearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(require_corp_admin)
):
    """
    Performs an AI-powered vector search on waitlisted user profiles.
    """
    if not search_request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    similar_profiles_with_distance = await crud_user_profile.ai_search_waitlisted_profiles(
        db, query=search_request.query
    )
    
    # Extract the User object from each tuple in the results
    users = [profile.user for profile, distance in similar_profiles_with_distance]
    
    return users

@router.get("/browse-waitlist", response_model=List[Union[UserSchema, StartupSchema]])
async def browse_waitlist(
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = None,
    type: Optional[str] = None, # startup or freelancer
    skip: int = 0,
    limit: int = 20,
    current_user: models.User = Depends(require_corp_admin)
):
    """
    Allows Corporate Admins to browse waitlisted users and startups.
    """
    results = []
    if type == 'freelancer' or not type:
        freelancers = await crud_user.get_users(
            db, 
            skip=skip, 
            limit=limit, 
            user_type=UserRole.FREELANCER, 
            status=UserStatus.WAITLISTED,
            search_term=search
        )
        results.extend(freelancers)

    if type == 'startup' or not type:
        startups = await crud_organization.get_startups_by_status(
            db, 
            status=UserStatus.WAITLISTED,
            skip=skip,
            limit=limit,
            search_term=search
        )
        results.extend(startups)

    # This will just combine the lists. A more sophisticated pagination would be needed for large datasets.
    return results[:limit]

@router.get("/pending-corporates", response_model=List[PendingCorporateUser], dependencies=[Depends(require_sys_admin)])
async def list_pending_corporate_signups(db: AsyncSession = Depends(get_db)):
    """List all users with status PENDING_ONBOARDING."""
    pending_users = await crud_user.get_users_by_status(db, status=UserStatus.PENDING_ONBOARDING)
    return pending_users

@router.get("/users", response_model=PaginatedUserAdminView, dependencies=[Depends(require_sys_admin)])
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
    users = await crud_user.get_users(
        db, skip=skip, limit=limit, user_type=user_type, status=status, space_id=space_id, search_term=search_term
    )
    total_users = await crud_user.get_total_users_count(
        db, user_type=user_type, status=status, space_id=space_id, search_term=search_term
    )
    return PaginatedUserAdminView(
        total=total_users,
        users=[UserAdminView.from_orm(u) for u in users]
    )

@router.post("/impersonate/{user_id}", response_model=schemas.auth.Token, dependencies=[Depends(require_sys_admin)])
async def impersonate_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Generate an impersonation token for a user."""
    user = await crud_user.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    token = app_security.create_access_token(
        data={"sub": user.email, "user_id": user.id, "role": user.role.value, "impersonated": True},
        expires_delta=settings.ACCESS_TOKEN_EXPIRE_MINUTES_IMPERSONATE
    )
    return schemas.auth.Token(access_token=token, token_type="bearer")

@router.get("/spaces", response_model=List[SpaceResponseSchema], dependencies=[Depends(require_sys_admin)])
async def list_all_spaces(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """List all spaces."""
    spaces = await crud_space.get_spaces(db, skip=skip, limit=limit)
    return spaces

@router.put("/users/{user_id}/status", response_model=UserAdminView, dependencies=[Depends(require_sys_admin)])
async def update_user_status_by_admin(
    user_id: int, 
    status_update: UserStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a user's role, status, or space assignment."""
    user = await crud_user.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = UserUpdateInternal(**status_update.model_dump(exclude_unset=True))
    updated_user = await crud_user.update_user_internal(db=db, db_obj=user, obj_in=update_data)
    return UserAdminView.from_orm(updated_user)

@router.put("/spaces/{space_id}", response_model=SpaceResponseSchema, dependencies=[Depends(require_sys_admin)])
async def update_space_by_admin(
    space_id: int, 
    space_update: SpaceUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a space's details."""
    space = await crud_space.get_space_by_id(db, space_id=space_id)
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    
    updated_space = await crud_space.update_space(db=db, db_obj=space, obj_in=space_update)
    return updated_space

@router.put("/spaces/{space_id}/assign-admin", response_model=SpaceResponseSchema, dependencies=[Depends(require_sys_admin)])
async def assign_space_admin(
    space_id: int,
    admin_assignment: SpaceAssignAdmin,
    db: AsyncSession = Depends(get_db)
):
    """Assign a corporate admin to a space."""
    space = await crud_space.get_space_by_id(db, space_id=space_id)
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")

    new_admin = await crud_user.get_user_by_id(db, user_id=admin_assignment.corporate_admin_id)
    if not new_admin or new_admin.role != UserRole.CORP_ADMIN:
        raise HTTPException(status_code=400, detail="Invalid user or user is not a Corporate Admin.")

    space.corporate_admin_id = new_admin.id
    db.add(space)
    await db.commit()
    await db.refresh(space)
    return space

@router.get("/stats", response_model=schemas.admin.PlatformStats, dependencies=[Depends(require_sys_admin)])
async def get_platform_statistics(db: AsyncSession = Depends(get_db)):
    """Retrieve comprehensive platform statistics."""
    # This assumes a CRUD function get_platform_stats exists.
    # If not, the logic to calculate stats needs to be implemented here.
    # stats = await crud_user.get_platform_stats(db)
    # return stats
    # Placeholder implementation:
    return schemas.admin.PlatformStats(total_users=0, active_users=0, total_spaces=0, total_connections_made=0, users_pending_verification=0, users_waitlisted=0, users_pending_onboarding=0, users_suspended=0, users_banned=0)

async def get_managed_space(
    db: AsyncSession, current_user: models.User
) -> Optional[models.SpaceNode]:
    """
    Helper function to get the space managed by the current Corp Admin.
    Returns None if no space is managed.
    """
    stmt = select(models.SpaceNode).where(models.SpaceNode.corporate_admin_id == current_user.id)
    result = await db.execute(stmt)
    managed_space = result.scalar_one_or_none()
    return managed_space

@router.put("/startups/{startup_id}", response_model=StartupSchema, dependencies=[Depends(require_corp_admin)])
async def update_startup_by_corp_admin(
    startup_id: int,
    startup_update: StartupUpdateAdmin,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Allows a Corporate Admin to update a startup in their managed space.
    """
    managed_space = await get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=404, detail="No managed space found.")

    startup = await crud.crud_organization.get_startup(db, startup_id=startup_id)
    if not startup or startup.space_id != managed_space.id:
        raise HTTPException(status_code=404, detail="Startup not found in your managed space.")

    update_data = startup_update.model_dump(exclude_unset=True)
    
    # This is a simplified update. A more robust version would use a specific schema.
    if 'approved_member_slots' in update_data:
        startup.approved_member_slots = update_data['approved_member_slots']

    db.add(startup)
    await db.commit()
    await db.refresh(startup)

    return startup 

@router.put("/startups/{startup_id}/slots", response_model=schemas.organization.Startup)
async def update_startup_member_slots(
    startup_id: int,
    slot_data: MemberSlotUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_user_with_roles(["CORP_ADMIN"])),
):
    """
    Allows a Corp Admin to update the allocated member slots for a startup in their space.
    """
    managed_space = await get_managed_space(db, current_user)
    if not managed_space:
        raise HTTPException(status_code=403, detail="User does not manage a space.")

    startup = await crud.crud_organization.get_startup(db, startup_id=startup_id)
    if not startup or startup.space_id != managed_space.id:
        raise HTTPException(status_code=404, detail="Startup not found in the managed space.")

    update_data = {"member_slots_allocated": slot_data.member_slots_allocated}
    updated_startup = await crud.crud_organization.update_startup(
        db, db_obj=startup, obj_in=schemas.organization.StartupUpdate(**update_data)
    )

    # Notify the startup admin
    startup_admin = next((member for member in startup.direct_members if member.role == UserRole.STARTUP_ADMIN), None)
    if startup_admin:
        await crud_notification.create_notification(
            db=db,
            user_id=startup_admin.id,
            type=NotificationType.SLOT_ALLOCATION_UPDATED,
            message=f"Your allocated member slots have been updated to {slot_data.member_slots_allocated} by {managed_space.name}.",
            link="/dashboard/startup-admin/profile/edit" # Or a more specific link
        )

    return updated_startup 